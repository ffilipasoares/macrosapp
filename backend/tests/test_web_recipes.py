"""New recipes from the web: only working pages with a photo, and photos kept as our own copy."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from google.genai import types

from app import links, web_recipes
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
        "25 fish dinners, no recipe here",
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


def test_only_working_pages_with_a_recipe_are_kept():
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
    found = find_web_recipes(ai, reader, "healthy fish dinner", 3, ["Salmon bowl"])
    # Broken page, list page, a recipe you already have and a duplicate are skipped,
    # and recipes with a photo come before the one without.
    assert [draft.title for draft in found] == ["Fish tacos", "Fish pie", "Grilled fish"]
    assert all(draft.ingredients for draft in found)
    assert all(draft.image_url for draft in found)
    # With room for more, the page without a photo is still used, last.
    more = find_web_recipes(ai, reader, "healthy fish dinner", 4, ["Salmon bowl"])
    assert [draft.title for draft in more][-1] == "Fish soup"
    assert more[-1].image_url is None


def test_no_working_pages_means_no_suggestions():
    ai = ListedLinks(["https://broken.example/1", "https://good.example/listicle"])
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


def test_plan_says_when_the_search_ran_out_of_time():
    # The search budget comes from the server's settings (WEB_SEARCH_SECONDS).
    app = create_app(
        config=Config(push_enabled=False, web_search_seconds=-1),
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
    assert any("ran out of time (-1 seconds)" in note for note in plan["notes"])


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


class CountingSearch(FakeRecipeAI):
    """A search that remembers each query and returns these pages."""

    def __init__(self, urls: list[str]) -> None:
        super().__init__()
        self.urls, self.queries = urls, []

    def find_recipe_links(self, query: str, count: int, avoid_titles: list[str]) -> list[str]:
        self.queries.append((query, count))
        return self.urls


MIXED = {
    f"https://mixed.example/{kind}-{n}": LinkContent(
        f"https://mixed.example/{kind}-{n}",
        f"{kind.capitalize()} dish {n}\\n- 1 thing",
        "recipe-data",
        None,
    )
    for kind in ("fish", "chicken", "beef")
    for n in range(1, 4)
}


def test_one_search_covers_every_rule_and_empty_meal():
    ai = CountingSearch(list(MIXED))
    app = create_app(
        config=Config(push_enabled=False),
        repo=MemoryRepo(),
        ai=ai,
        notifier=LogNotifier(),
        verify_token=lambda token: {"uid": token, "email": "a@example.com", "email_verified": True},
        read_link=lambda url: MIXED[url],
    )
    client = TestClient(app)
    auth = {"Authorization": "Bearer ana"}
    settings = client.get("/api/settings", headers=auth).json()
    settings["rules"] = [
        {"kind": "min", "count": 2, "tag": "fish"},
        {"kind": "min", "count": 1, "tag": "chicken"},
    ]
    settings["slots"] = {
        key: {
            "cook": key.endswith("dinner") and key[:3] in ("mon", "tue", "wed", "thu", "fri"),
            "portions": 2,
        }
        for key in settings["slots"]
    }
    client.put("/api/settings", json=settings, headers=auth)

    plan = client.post("/api/plans/2026-11-16/generate", headers=auth).json()
    assert len(ai.queries) == 1
    query, count = ai.queries[0]
    assert "at least 2 with fish" in query and "at least 1 with chicken" in query
    # The balanced week asks for 4 meals with vegetables, 2 fish, 1 legumes; plus own rules.
    assert "at least 4 with vegetables" in query and count == 12
    assert len(plan["meals"]) == 5 and all(meal["is_new"] for meal in plan["meals"].values())
    assert all(status["ok"] for status in plan["rule_status"])


def test_slow_pages_are_left_out_instead_of_holding_up_the_plan(monkeypatch):
    import time

    def reader_with_a_slow_page(url: str) -> LinkContent:
        if url.endswith("fish-2"):
            time.sleep(2)
        return PAGES[url]

    ai = ListedLinks(
        [
            "https://good.example/fish-1",
            "https://good.example/fish-2",
            "https://good.example/fish-3",
        ]
    )
    # Downloads get 0.5 s, then 1 s is kept for reading the pages that did load.
    monkeypatch.setattr(web_recipes, "READ_RESERVE_SECONDS", 1.0)
    started = time.monotonic()
    found = find_web_recipes(
        ai, reader_with_a_slow_page, "fish", 3, [], deadline=time.monotonic() + 1.5
    )
    assert time.monotonic() - started < 1.9
    assert [draft.title for draft in found] == ["Fish tacos", "Grilled fish"]


def test_the_app_may_call_the_api_directly_but_other_sites_may_not():
    app = create_app(
        config=Config(push_enabled=False, cors_origins=["https://meals.web.app"]),
        repo=MemoryRepo(),
        ai=FakeRecipeAI(),
        notifier=LogNotifier(),
        verify_token=lambda token: {"uid": token, "email": "a@example.com", "email_verified": True},
        read_link=reader,
    )
    client = TestClient(app)
    ask = {
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization",
    }
    ours = client.options(
        "/api/plans/2026-11-16/generate", headers={"Origin": "https://meals.web.app", **ask}
    )
    assert ours.status_code == 200
    assert ours.headers["access-control-allow-origin"] == "https://meals.web.app"
    theirs = client.options(
        "/api/plans/2026-11-16/generate", headers={"Origin": "https://evil.example", **ask}
    )
    assert "access-control-allow-origin" not in theirs.headers


def test_search_budget_and_allowed_sites_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("WEB_SEARCH_SECONDS", "120")
    monkeypatch.setenv("APP_URL", "https://meals.web.app/")
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    config = Config()
    assert config.web_search_seconds == 120 and config.cors_origins == ["https://meals.web.app"]
    monkeypatch.setenv("CORS_ORIGINS", "https://meals.web.app, https://meals.firebaseapp.com")
    assert Config().cors_origins == ["https://meals.web.app", "https://meals.firebaseapp.com"]


def test_only_real_recipe_websites_are_used():
    from app.web_recipes import is_recipe_website

    recipe_site = LinkContent(
        "https://www.bbcgoodfood.com/recipes/fish-pie", "x", "recipe-data", None
    )
    assert is_recipe_website(recipe_site)
    for url in (
        "https://github.com/someone/recipes/blob/main/fish-pie.md",
        "https://raw.githubusercontent.com/someone/recipes/main/fish.md",
        "https://www.reddit.com/r/Cooking/comments/1/fish_pie/",
        "https://en.wikipedia.org/wiki/Fish_pie",
    ):
        assert not is_recipe_website(LinkContent(url, "x", "recipe-data", None)), url
    # A page without recipe data is not a recipe website's recipe page.
    assert not is_recipe_website(LinkContent("https://blog.example/fish", "x", "page", None))


def test_a_recipe_on_github_is_never_suggested():
    github = "https://github.com/someone/recipes/blob/main/fish-pie.md"
    pages = {**PAGES, github: LinkContent(github, "Fish pie\n- 1 cod", "recipe-data", None)}
    ai = ListedLinks([github, *PAGES])
    found = find_web_recipes(ai, lambda url: pages[url], "fish", 3, [])
    assert github not in {draft.source_url for draft in found}
    assert len(found) == 3
