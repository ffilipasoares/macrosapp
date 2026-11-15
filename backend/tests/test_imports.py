"""Recipe imports: several screenshots, videos and links (TikTok captions and recipe pages)."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from google.genai import errors as genai_errors

from app import links
from app.ai.fake import FakeRecipeAI
from app.ai.gemini import GeminiRecipeAI
from app.config import Config
from app.links import LinkContent, LinkError
from app.main import create_app
from app.notify import LogNotifier
from app.repo.memory import MemoryRepo


def fake_verify(token: str) -> dict:
    return {"uid": token, "email": f"{token}@example.com", "email_verified": True}


AUTH = {"Authorization": "Bearer ana"}


def fake_reader(url: str) -> LinkContent:
    if "broken" in url:
        raise LinkError("The link could not be opened. Check it and try again.")
    if "tiktok" in url:
        caption = (
            "no recipe here, just vibes"
            if "vibes" in url
            else "Creamy tuscan salmon\n2 salmon fillets"
        )
        return LinkContent(url="https://www.tiktok.com/@cook/video/1", text=caption, kind="tiktok")
    return LinkContent(url=url, text="Bacalhau a Bras\n400 g cod", kind="recipe-data")


@pytest.fixture
def ctx():
    ai = FakeRecipeAI()
    app = create_app(
        config=Config(push_enabled=False),
        repo=MemoryRepo(),
        ai=ai,
        notifier=LogNotifier(),
        verify_token=fake_verify,
        read_link=fake_reader,
    )
    return TestClient(app), ai


def png(name: str = "a.png") -> tuple[str, tuple[str, bytes, str]]:
    return ("files", (name, b"\x89PNG data " + name.encode(), "image/png"))


def test_several_screenshots_make_one_recipe(ctx):
    client, ai = ctx
    reply = client.post(
        "/api/recipes/import/image", files=[png("1.png"), png("2.png"), png("3.png")], headers=AUTH
    )
    assert reply.status_code == 200
    assert ai.calls[-1] == ("images", 3)
    assert reply.json()["steps"][-1] == "Step from image 3."


def test_single_file_field_still_works(ctx):
    client, ai = ctx
    reply = client.post(
        "/api/recipes/import/image", files={"file": ("a.jpg", b"jpg", "image/jpeg")}, headers=AUTH
    )
    assert reply.status_code == 200 and ai.calls[-1] == ("images", 1)


def test_image_limits(ctx):
    client, _ = ctx
    too_many = [png(f"{i}.png") for i in range(11)]
    assert client.post("/api/recipes/import/image", files=too_many, headers=AUTH).status_code == 413
    pdf = [("files", ("a.pdf", b"%PDF", "application/pdf"))]
    assert client.post("/api/recipes/import/image", files=pdf, headers=AUTH).status_code == 415
    assert client.post("/api/recipes/import/image", headers=AUTH).status_code == 422


def test_video_import_passes_the_caption(ctx):
    client, ai = ctx
    reply = client.post(
        "/api/recipes/import/video",
        files={"file": ("clip.mp4", b"video bytes", "video/mp4")},
        data={"caption": "salmon bowl"},
        headers=AUTH,
    )
    assert reply.status_code == 200 and reply.json()["title"] == "Recipe from a video"
    assert ai.calls[-1] == ("video", "salmon bowl")
    gif = {"file": ("clip.gif", b"gif", "image/gif")}
    assert client.post("/api/recipes/import/video", files=gif, headers=AUTH).status_code == 415


def test_link_import(ctx):
    client, _ = ctx
    page = client.post(
        "/api/recipes/import/link", json={"url": "https://recipes.example/bacalhau"}, headers=AUTH
    )
    assert page.status_code == 200
    assert page.json()["title"] == "Bacalhau a Bras"
    assert page.json()["source_url"] == "https://recipes.example/bacalhau"

    tiktok = client.post(
        "/api/recipes/import/link", json={"url": "https://vm.tiktok.com/abc"}, headers=AUTH
    )
    assert tiktok.json()["title"] == "Creamy tuscan salmon"
    assert tiktok.json()["source_url"] == "https://www.tiktok.com/@cook/video/1"

    no_recipe = client.post(
        "/api/recipes/import/link", json={"url": "https://vm.tiktok.com/vibes"}, headers=AUTH
    )
    assert no_recipe.status_code == 422 and "send the video instead" in no_recipe.json()["detail"]

    broken = client.post(
        "/api/recipes/import/link", json={"url": "https://broken.example/x"}, headers=AUTH
    )
    assert broken.status_code == 422 and "could not be opened" in broken.json()["detail"]


def test_shortcuts_save_links_videos_and_several_images_for_review(ctx):
    client, _ = ctx
    key = {
        "Authorization": "Bearer " + client.get("/api/me", headers=AUTH).json()["shortcut_token"]
    }
    assert (
        client.post(
            "/api/shortcuts/recipe-link", json={"url": "https://vm.tiktok.com/abc"}, headers=key
        ).status_code
        == 200
    )
    video = {"file": ("clip.mov", b"mov", "video/quicktime")}
    assert client.post("/api/shortcuts/recipe-video", files=video, headers=key).status_code == 200
    assert (
        client.post(
            "/api/shortcuts/recipe-image", files=[png("1.png"), png("2.png")], headers=key
        ).status_code
        == 200
    )
    saved = client.get("/api/recipes", headers=AUTH).json()
    assert len(saved) == 3 and all(recipe["needs_review"] for recipe in saved)


def test_api_docs_page_is_not_published(ctx):
    client, _ = ctx
    assert client.get("/docs").status_code == 404


# Link reading ------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://169.254.169.254/computeMetadata/v1/",
        "http://localhost:8080/",
        "http://10.0.0.5/",
        "http://[::1]/",
        "file:///etc/passwd",
        "ftp://example.com/x",
        "https://8.8.8.8:22/",
        "not a link",
    ],
)
def test_private_and_odd_addresses_are_refused(url):
    with pytest.raises(LinkError):
        links.check_url(url)


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def public_hosts(monkeypatch):
    """Treat test hostnames as public without a DNS lookup; IP literals are still checked."""
    real = links._is_public_host
    monkeypatch.setattr(
        links, "_is_public_host", lambda host: real(host) if host[0].isdigit() else True
    )


def test_redirect_to_a_private_address_is_refused(public_hosts):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302, headers={"location": "http://169.254.169.254/computeMetadata/v1/"}
        )

    with pytest.raises(LinkError):
        links.read_link("https://evil.example/recipe", client=_client(handler))


RECIPE_PAGE = """<html><head><script type="application/ld+json">
{"@context": "https://schema.org", "@graph": [
  {"@type": "WebPage", "name": "Page"},
  {"@type": ["Recipe"], "name": "Caldo verde", "recipeYield": ["4"], "totalTime": "PT40M",
   "recipeIngredient": ["500 g potatoes", "200 g kale", "1 chouri&ccedil;o"],
   "recipeInstructions": [
     {"@type": "HowToSection", "name": "Soup", "itemListElement": [
        {"@type": "HowToStep", "text": "Boil the potatoes."},
        {"@type": "HowToStep", "text": "Blend."}]},
     {"@type": "HowToStep", "text": "Add the kale and sausage."}]}
]}</script></head><body>ads ads ads</body></html>"""


def test_recipe_pages_use_their_structured_recipe(public_hosts):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=RECIPE_PAGE, headers={"content-type": "text/html"})

    content = links.read_link("https://recipes.example/caldo-verde", client=_client(handler))
    assert content.kind == "recipe-data"
    assert content.text.splitlines()[0] == "Caldo verde"
    assert "- 500 g potatoes" in content.text and "- 1 chouriço" in content.text
    assert (
        "1. Boil the potatoes." in content.text and "3. Add the kale and sausage." in content.text
    )


def test_tiktok_links_use_the_official_caption(public_hosts):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.host == "vm.tiktok.com":
            return httpx.Response(
                301, headers={"location": "https://www.tiktok.com/@cook/video/123?lang=en"}
            )
        if request.url.path == "/oembed":
            assert request.url.params["url"] == "https://www.tiktok.com/@cook/video/123?lang=en"
            return httpx.Response(
                200,
                text=json.dumps({"title": "Salmon bowl: 2 fillets, rice", "author_name": "cook"}),
            )
        return httpx.Response(200, text="<html>tiktok</html>")

    content = links.read_link("https://vm.tiktok.com/ZMabc/", client=_client(handler))
    assert content.kind == "tiktok"
    assert content.url == "https://www.tiktok.com/@cook/video/123?lang=en"
    assert content.text == "TikTok video by cook\n\nSalmon bowl: 2 fillets, rice"
    assert any("/oembed" in url for url in seen)


def test_tiktok_without_caption_asks_for_the_video(public_hosts):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oembed":
            return httpx.Response(200, text=json.dumps({"title": ""}))
        return httpx.Response(200, text="<html></html>")

    with pytest.raises(LinkError, match="send the video instead"):
        links.read_link("https://www.tiktok.com/@cook/video/1", client=_client(handler))


# Gemini error messages ---------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (404, 'model "gemini-x" was not found in "global"'),
        (403, "Vertex AI User role"),
        (429, "quota"),
        (400, "rejected the request: bad schema"),
        (500, "having problems"),
    ],
)
def test_gemini_errors_say_what_to_fix(code, expected):
    ai = GeminiRecipeAI.__new__(GeminiRecipeAI)
    ai.model, ai.location = "gemini-x", "global"
    error = genai_errors.APIError(
        code, {"error": {"code": code, "message": "bad schema", "status": "X"}}
    )
    message = str(ai._explain(error))
    assert expected in message and f"(error {code})" in message
    assert "could not be reached" in str(ai._explain(ConnectionError()))
