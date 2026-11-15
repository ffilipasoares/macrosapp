"""New recipes from the web: only working pages with a photo, and photos kept as our own copy."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from google.genai import types

from app import links
from app.ai.fake import FakeRecipeAI
from app.ai.gemini import GeminiRecipeAI
from app.config import Config
from app.images import MemoryImageStore, keep_own_copy
from app.links import LinkContent, LinkError
from app.main import create_app
from app.models import Recipe
from app.notify import LogNotifier
from app.repo.memory import MemoryRepo
from app.web_recipes import find_web_recipes


class ListedLinks(FakeRecipeAI):
    """A search that returns exactly these addresses."""

    def __init__(self, urls: list[str]) -> None:
        super().__init__()
        self.urls = urls

    def find_recipe_links(self, query: str, count: int, avoid_titles: list[str]) -> list[str]:
        return self.urls


PAGES = {
    "https://good.example/fish-1": LinkContent(
        "https://good.example/fish-1",
        "Fish tacos\n- 2 cod",
        "recipe-data",
        "https://img.example/1.jpg",
    ),
    "https://good.example/fish-2": LinkContent(
        "https://good.example/fish-2",
        "Fish pie\n- 1 haddock",
        "recipe-data",
        "https://img.example/2.jpg",
    ),
    "https://good.example/fish-3": LinkContent(
        "https://good.example/fish-3",
        "Grilled fish\n- 1 bream",
        "recipe-data",
        "https://img.example/3.jpg",
    ),
    "https://good.example/no-photo": LinkContent(
        "https://good.example/no-photo", "Fish soup\n- 1 cod", "recipe-data", None
    ),
    "https://good.example/listicle": LinkContent(
        "https://good.example/listicle",
        "25 fish dinners " * 20,
        "page",
        "https://img.example/l.jpg",
    ),
    "https://good.example/fish-1-copy": LinkContent(
        "https://good.example/fish-1",
        "Fish tacos\n- 2 cod",
        "recipe-data",
        "https://img.example/1.jpg",
    ),
    "https://good.example/known": LinkContent(
        "https://good.example/known",
        "Salmon bowl\n- 1 salmon fish",
        "recipe-data",
        "https://img.example/k.jpg",
    ),
}


def reader(url: str) -> LinkContent:
    if url not in PAGES:
        raise LinkError("The page answered with an error (404).")
    return PAGES[url]


def test_only_working_pages_with_a_photo_are_kept():
    ai = ListedLinks(
        [
            "https://broken.example/404",
            "https://good.example/no-photo",
            "https://good.example/listicle",
            "https://good.example/known",
            "https://good.example/fish-1",
            "https://good.example/fish-1-copy",
            "https://good.example/fish-2",
            "https://good.example/fish-3",
        ]
    )
    found = find_web_recipes(ai, reader, "healthy fish dinner", 2, ["Salmon bowl"])
    assert [draft.title for draft in found] == ["Fish tacos", "Fish pie"]
    assert [draft.source_url for draft in found] == [
        "https://good.example/fish-1",
        "https://good.example/fish-2",
    ]
    assert all(draft.image_url and draft.ingredients for draft in found)


def test_no_working_pages_means_no_suggestions():
    ai = ListedLinks(["https://broken.example/1", "https://good.example/no-photo"])
    assert find_web_recipes(ai, reader, "dinner", 3, []) == []


def test_plan_notes_when_the_web_has_nothing_usable():
    app = create_app(
        config=Config(push_enabled=False),
        repo=MemoryRepo(),
        ai=ListedLinks(["https://broken.example/1"]),
        notifier=LogNotifier(),
        verify_token=lambda token: {"uid": token, "email": "a@example.com", "email_verified": True},
        read_link=reader,
    )
    client = TestClient(app)
    plan = client.post(
        "/api/plans/2026-11-16/generate", headers={"Authorization": "Bearer ana"}
    ).json()
    assert plan["meals"] == {}
    assert any("Only 0 of 9 meals" in note for note in plan["notes"])


# Our own copies of photos --------------------------------------------------------


def test_web_photo_is_copied_and_failures_keep_the_original():
    store = MemoryImageStore()
    recipe = Recipe(title="Fish tacos", image_url="https://img.example/1.jpg")
    keep_own_copy(store, lambda url: (b"jpg", "image/jpeg"), "h1", recipe)
    assert store.owns(recipe.image_url) and store.saved[recipe.image_url] == b"jpg"

    copied = recipe.image_url
    keep_own_copy(store, lambda url: pytest.fail("already ours"), "h1", recipe)
    assert recipe.image_url == copied

    broken = Recipe(title="Pie", image_url="https://img.example/gone.jpg")

    def gone(url: str) -> tuple[bytes, str]:
        raise LinkError("The photo could not be downloaded.")

    keep_own_copy(store, gone, "h1", broken)
    assert broken.image_url == "https://img.example/gone.jpg"
    keep_own_copy(None, gone, "h1", broken)  # no storage configured: nothing happens


def test_saving_a_recipe_from_a_link_keeps_a_copy_of_its_photo():
    store = MemoryImageStore()
    app = create_app(
        config=Config(push_enabled=False),
        repo=MemoryRepo(),
        ai=FakeRecipeAI(),
        notifier=LogNotifier(),
        verify_token=lambda token: {"uid": token, "email": "a@example.com", "email_verified": True},
        read_link=reader,
        read_image=lambda url: (b"photo", "image/jpeg"),
        image_store=store,
    )
    client = TestClient(app)
    auth = {"Authorization": "Bearer ana"}
    draft = client.post(
        "/api/recipes/import/link", json={"url": "https://good.example/fish-1"}, headers=auth
    ).json()
    assert draft["image_url"] == "https://img.example/1.jpg"  # shown from the page while reviewing
    saved = client.post("/api/recipes", json=draft, headers=auth).json()
    assert store.owns(saved["image_url"])

    # Changing the photo to another web address copies that one too; unrelated edits copy nothing.
    again = client.put(
        f"/api/recipes/{saved['id']}", json={**saved, "servings": 6}, headers=auth
    ).json()
    assert again["image_url"] == saved["image_url"] and len(store.saved) == 1
    changed = client.put(
        f"/api/recipes/{saved['id']}",
        json={**saved, "image_url": "https://img.example/2.jpg"},
        headers=auth,
    ).json()
    assert store.owns(changed["image_url"]) and len(store.saved) == 2


# Downloading photos ---------------------------------------------------------------


@pytest.fixture
def public_hosts(monkeypatch):
    real = links._is_public_host
    monkeypatch.setattr(
        links, "_is_public_host", lambda host: real(host) if host[0].isdigit() else True
    )


def test_photo_download_only_accepts_images(public_hosts):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(".jpg"):
            return httpx.Response(
                200, content=b"\xff\xd8jpeg", headers={"content-type": "image/jpeg"}
            )
        if request.url.path.endswith(".svg"):
            return httpx.Response(200, content=b"<svg/>", headers={"content-type": "image/svg+xml"})
        return httpx.Response(200, content=b"<html>", headers={"content-type": "text/html"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert links.read_image("https://img.example/a.jpg", client=client) == (
        b"\xff\xd8jpeg",
        "image/jpeg",
    )
    with pytest.raises(LinkError):
        links.read_image("https://img.example/a.svg", client=client)
    with pytest.raises(LinkError):
        links.read_image("https://img.example/page", client=client)
    with pytest.raises(LinkError):
        links.read_image("http://169.254.169.254/latest", client=client)


def test_tiktok_links_bring_the_video_cover(public_hosts):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oembed":
            body = {
                "title": "Salmon bowl: 2 fillets",
                "author_name": "cook",
                "thumbnail_url": "https://p16.tiktokcdn.example/cover.jpeg",
            }
            return httpx.Response(200, text=json.dumps(body))
        return httpx.Response(200, text="<html></html>")

    content = links.read_link(
        "https://www.tiktok.com/@cook/video/1",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert content.image_url == "https://p16.tiktokcdn.example/cover.jpeg"


# The search itself -------------------------------------------------------------------


def test_search_uses_the_pages_google_returned_not_the_written_answer():
    ai = GeminiRecipeAI.__new__(GeminiRecipeAI)
    ai.model, ai.location = "gemini-x", "global"
    chunks = [
        types.GroundingChunk(
            web=types.GroundingChunkWeb(
                uri="https://vertexaisearch.cloud.google.com/grounding-api-redirect/a",
                title="a.com",
            )
        ),
        types.GroundingChunk(
            web=types.GroundingChunkWeb(
                uri="https://vertexaisearch.cloud.google.com/grounding-api-redirect/b",
                title="b.com",
            )
        ),
        types.GroundingChunk(
            web=types.GroundingChunkWeb(
                uri="https://vertexaisearch.cloud.google.com/grounding-api-redirect/a",
                title="a.com",
            )
        ),
    ]
    response = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(
                    parts=[types.Part(text="Try https://made-up.example/recipe")]
                ),
                grounding_metadata=types.GroundingMetadata(grounding_chunks=chunks),
            )
        ]
    )
    ai._call = lambda contents, config, what: response
    assert ai.find_recipe_links("fish", 2, []) == [
        "https://vertexaisearch.cloud.google.com/grounding-api-redirect/a",
        "https://vertexaisearch.cloud.google.com/grounding-api-redirect/b",
    ]


def test_the_web_search_stops_when_time_is_up():
    import time

    ai = ListedLinks(["https://good.example/fish-1", "https://good.example/fish-2"])
    assert find_web_recipes(ai, reader, "fish", 2, [], deadline=time.monotonic() - 1) == []
    assert len(find_web_recipes(ai, reader, "fish", 2, [], deadline=time.monotonic() + 30)) == 2


def test_plan_says_when_the_search_ran_out_of_time(monkeypatch):
    from app import services

    monkeypatch.setattr(services, "WEB_SEARCH_SECONDS", -1)
    app = create_app(
        config=Config(push_enabled=False),
        repo=MemoryRepo(),
        ai=ListedLinks(["https://good.example/fish-1"]),
        notifier=LogNotifier(),
        verify_token=lambda token: {"uid": token, "email": "a@example.com", "email_verified": True},
        read_link=reader,
    )
    plan = (
        TestClient(app)
        .post("/api/plans/2026-11-16/generate", headers={"Authorization": "Bearer ana"})
        .json()
    )
    assert any("after -1 seconds" in note for note in plan["notes"])


def test_unexpected_errors_explain_themselves():
    def broken(url: str) -> LinkContent:
        raise RuntimeError("boom")

    app = create_app(
        config=Config(push_enabled=False),
        repo=MemoryRepo(),
        ai=FakeRecipeAI(),
        notifier=LogNotifier(),
        verify_token=lambda token: {"uid": token, "email": "a@example.com", "email_verified": True},
        read_link=broken,
    )
    reply = TestClient(app, raise_server_exceptions=False).post(
        "/api/recipes/import/link",
        json={"url": "https://x.example/r"},
        headers={"Authorization": "Bearer ana"},
    )
    assert reply.status_code == 500
    assert "unexpected problem (RuntimeError)" in reply.json()["detail"]
