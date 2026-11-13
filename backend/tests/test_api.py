"""End-to-end API tests with in-memory storage and a fake AI."""

import random
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import services
from app.ai.fake import FakeRecipeAI
from app.config import Config
from app.main import create_app
from app.notify import LogNotifier
from app.repo.memory import MemoryRepo

WEEK = "2026-11-16"


def fake_verify(token: str) -> dict:
    if token == "bad":
        raise ValueError("invalid token")
    return {"uid": token, "email": f"{token}@example.com", "email_verified": True}


def auth(user: str = "ana") -> dict[str, str]:
    return {"Authorization": f"Bearer {user}"}


@pytest.fixture
def ctx():
    repo, notifier = MemoryRepo(), LogNotifier()
    app = create_app(
        config=Config(job_token="job-secret", ai_provider="fake", push_enabled=False),
        repo=repo,
        ai=FakeRecipeAI(),
        notifier=notifier,
        verify_token=fake_verify,
    )
    return TestClient(app), repo, notifier


def add_recipes(client: TestClient, user: str = "ana") -> None:
    proteins = ["chicken"] * 4 + ["fish"] * 4 + ["beef"] * 3 + ["vegetarian"] * 5
    for index, protein in enumerate(proteins):
        body = {
            "title": f"{protein} dish {index}",
            "servings": 2,
            "protein": protein,
            "ingredients": [
                {"name": "Onions", "quantity": 1, "aisle": "produce"},
                {"name": f"{protein} fillet", "quantity": 300, "unit": "grams"},
                {"name": "salt"},
            ],
            "steps": ["Cook it."],
        }
        assert client.post("/api/recipes", json=body, headers=auth(user)).status_code == 201


def test_sign_in_is_required(ctx):
    client, _, _ = ctx
    assert client.get("/api/recipes").status_code == 401
    assert client.get("/api/recipes", headers=auth("bad")).status_code == 401


def test_allowlist_blocks_other_accounts():
    app = create_app(
        config=Config(allowed_emails=["ana@example.com"], push_enabled=False),
        repo=MemoryRepo(),
        verify_token=fake_verify,
        use_default_ai=False,
    )
    client = TestClient(app)
    assert client.get("/api/me", headers=auth("ana")).status_code == 200
    assert client.get("/api/me", headers=auth("eve")).status_code == 403


def test_recipe_crud_normalises_ingredients(ctx):
    client, _, _ = ctx
    created = client.post(
        "/api/recipes",
        json={
            "title": "Bacalhau à Brás",
            "protein": "Fish",
            "ingredients": [{"name": "Red Onions (sliced)", "quantity": 2, "unit": "pieces"}],
        },
        headers=auth(),
    ).json()
    assert created["protein"] == "fish"
    assert created["ingredients"][0] == {
        "name": "red onion", "quantity": 2.0, "unit": "", "aisle": "produce",
    }  # fmt: skip

    recipe_id = created["id"]
    updated = client.put(
        f"/api/recipes/{recipe_id}", json={**created, "servings": 6}, headers=auth()
    ).json()
    assert updated["servings"] == 6 and updated["id"] == recipe_id

    assert client.delete(f"/api/recipes/{recipe_id}", headers=auth()).status_code == 204
    assert client.get(f"/api/recipes/{recipe_id}", headers=auth()).status_code == 404


def test_households_cannot_see_each_other(ctx):
    client, _, _ = ctx
    add_recipes(client, "ana")
    assert len(client.get("/api/recipes", headers=auth("ana")).json()) == 16
    assert client.get("/api/recipes", headers=auth("bruno")).json() == []
    theirs = client.get("/api/recipes", headers=auth("ana")).json()[0]["id"]
    assert client.get(f"/api/recipes/{theirs}", headers=auth("bruno")).status_code == 404


def test_full_week_from_rules_to_grocery_list(ctx):
    client, _, _ = ctx
    add_recipes(client)
    settings = client.get("/api/settings", headers=auth()).json()
    settings["rules"] = [
        {"kind": "min", "count": 2, "tag": "chicken"},
        {"kind": "min", "count": 2, "tag": "fish"},
    ]
    settings["staples"] = ["Salt"]
    assert client.put("/api/settings", json=settings, headers=auth()).status_code == 200

    assert client.get(f"/api/plans/{WEEK}", headers=auth()).json() is None
    plan = client.post(f"/api/plans/{WEEK}/generate", headers=auth()).json()
    assert plan["status"] == "draft"
    assert len(plan["meals"]) == 9 and plan["open_slots"] == []
    assert all(status["ok"] for status in plan["rule_status"])
    assert plan["meals"]["thu_dinner"]["portions"] == 4
    assert not any(meal["is_new"] for meal in plan["meals"].values())

    # A typed item added before approval must survive list generation.
    client.post("/api/groceries", json={"text": "Oat milk, toilet paper"}, headers=auth())

    result = client.post(f"/api/plans/{WEEK}/approve", headers=auth()).json()
    assert result["plan"]["status"] == "approved"
    groceries = client.get("/api/groceries", headers=auth()).json()
    names = [item["name"] for item in groceries]
    assert "salt" not in names and "oat milk" in names
    onion = next(item for item in groceries if item["name"] == "onion")
    # 4 dinners for 4 and 5 meals for 2, each from a 2-serving recipe with 1 onion.
    assert onion["quantity"] == 13 and onion["source"] == "plan" and len(onion["recipes"]) == 9

    # Approving again replaces the generated items instead of duplicating them.
    client.post(f"/api/plans/{WEEK}/approve", headers=auth())
    again = client.get("/api/groceries", headers=auth()).json()
    assert len(again) == len(groceries)


def test_swapping_a_meal_checks_the_rules_and_reopens_the_plan(ctx):
    client, _, _ = ctx
    add_recipes(client)
    settings = client.get("/api/settings", headers=auth()).json()
    settings["rules"] = [{"kind": "min", "count": 2, "tag": "fish"}]
    client.put("/api/settings", json=settings, headers=auth())
    plan = client.post(f"/api/plans/{WEEK}/generate", headers=auth()).json()
    client.post(f"/api/plans/{WEEK}/approve", headers=auth())

    fish_slots = [s for s, meal in plan["meals"].items() if meal["recipe"]["protein"] == "fish"]
    slot = fish_slots[0]
    options = client.get(f"/api/plans/{WEEK}/meals/{slot}/alternatives", headers=auth()).json()
    planned_ids = {meal["recipe"]["id"] for meal in plan["meals"].values()}
    assert options and all(option["recipe"]["id"] not in planned_ids for option in options)
    if len(fish_slots) == 2:
        assert all(
            option["recipe"]["protein"] == "fish" for option in options if option["keeps_rules"]
        )

    breaking = next(option for option in options if option["recipe"]["protein"] != "fish")
    changed = client.put(
        f"/api/plans/{WEEK}/meals/{slot}",
        json={"recipe_id": breaking["recipe"]["id"]},
        headers=auth(),
    ).json()
    assert changed["status"] == "draft"
    assert changed["meals"][slot]["recipe"]["id"] == breaking["recipe"]["id"]

    cleared = client.put(
        f"/api/plans/{WEEK}/meals/{slot}", json={"recipe_id": None}, headers=auth()
    ).json()
    assert slot in cleared["open_slots"]
    assert (
        client.put(
            f"/api/plans/{WEEK}/meals/breakfast", json={"recipe_id": None}, headers=auth()
        ).status_code
        == 404
    )


def test_next_week_avoids_this_weeks_recipes(ctx):
    client, _, _ = ctx
    add_recipes(client)  # 16 recipes, 9 slots
    first = client.post("/api/plans/2026-11-09/generate", headers=auth()).json()
    client.post("/api/plans/2026-11-09/approve", headers=auth())
    second = client.post(f"/api/plans/{WEEK}/generate", headers=auth()).json()

    first_ids = {meal["recipe"]["id"] for meal in first["meals"].values()}
    library_repeats = [
        meal
        for meal in second["meals"].values()
        if meal["recipe"]["id"] in first_ids and not meal["is_new"]
    ]
    assert len(library_repeats) <= 1
    # Only 7 unused recipes remain, so the gap is filled with new suggestions.
    assert len(second["meals"]) == 9
    assert sum(1 for meal in second["meals"].values() if meal["is_new"]) >= 1


def test_empty_library_is_filled_with_suggestions_and_kept_on_approval(ctx):
    client, _, _ = ctx
    plan = client.post(f"/api/plans/{WEEK}/generate", headers=auth()).json()
    assert len(plan["meals"]) == 9
    assert all(meal["is_new"] for meal in plan["meals"].values())
    assert client.get("/api/recipes", headers=auth()).json() == []

    client.post(f"/api/plans/{WEEK}/approve", headers=auth())
    saved = client.get("/api/recipes", headers=auth()).json()
    assert len(saved) == 9 and all(recipe["last_planned_week"] == WEEK for recipe in saved)


def test_without_ai_a_small_library_leaves_open_slots():
    repo = MemoryRepo()
    app = create_app(
        config=Config(push_enabled=False), repo=repo, verify_token=fake_verify, use_default_ai=False
    )
    client = TestClient(app)
    plan = client.post(f"/api/plans/{WEEK}/generate", headers=auth()).json()
    assert plan["meals"] == {} and len(plan["open_slots"]) == 9 and plan["notes"]
    assert (
        client.post("/api/recipes/search", json={"query": "soup"}, headers=auth()).status_code
        == 503
    )


def test_invalid_week_is_rejected(ctx):
    client, _, _ = ctx
    assert client.get("/api/plans/2026-11-13", headers=auth()).status_code == 422
    assert client.get("/api/plans/next", headers=auth()).status_code == 422


def test_siri_adds_items_with_the_shortcut_key(ctx):
    client, _, _ = ctx
    token = client.get("/api/me", headers=auth()).json()["shortcut_token"]
    key = {"Authorization": f"Bearer {token}"}

    reply = client.post("/api/shortcuts/grocery", json={"item": "Eggs and bread"}, headers=key)
    assert reply.json() == {"message": "Added eggs, bread to your groceries."}
    reply = client.post("/api/shortcuts/grocery", json={"item": "egg"}, headers=key)
    assert reply.json() == {"message": "That is already on your list."}

    items = client.get("/api/groceries", headers=auth()).json()
    assert {(item["name"], item["aisle"], item["source"]) for item in items} == {
        ("eggs", "dairy_eggs", "siri"),
        ("bread", "bakery", "siri"),
    }
    wrong = {"Authorization": "Bearer nope"}
    assert (
        client.post("/api/shortcuts/grocery", json={"item": "x"}, headers=wrong).status_code == 401
    )


def test_recipe_imports_return_a_draft_to_review(ctx):
    client, repo, _ = ctx
    image = {"file": ("shot.png", b"\x89PNG fake", "image/png")}
    draft = client.post("/api/recipes/import/image", files=image, headers=auth()).json()
    assert draft["title"] and draft["ingredients"] and "id" not in draft
    assert client.get("/api/recipes", headers=auth()).json() == []

    pdf = {"file": ("doc.pdf", b"%PDF", "application/pdf")}
    assert client.post("/api/recipes/import/image", files=pdf, headers=auth()).status_code == 415

    text = client.post(
        "/api/recipes/import/text",
        json={"text": "Arroz de pato\n1 pato, 300g arroz..."},
        headers=auth(),
    )
    assert text.json()["title"] == "Arroz de pato"

    found = client.post("/api/recipes/search", json={"query": "fish", "count": 3}, headers=auth())
    assert len(found.json()) == 3


def test_shared_screenshot_is_saved_for_review(ctx):
    client, _, _ = ctx
    token = client.get("/api/me", headers=auth()).json()["shortcut_token"]
    image = {"file": ("shot.jpg", b"jpeg bytes", "image/jpeg")}
    reply = client.post(
        "/api/shortcuts/recipe-image", files=image, headers={"Authorization": f"Bearer {token}"}
    )
    assert reply.status_code == 200 and "Saved" in reply.json()["message"]
    saved = client.get("/api/recipes", headers=auth()).json()
    assert len(saved) == 1 and saved[0]["needs_review"] is True


def test_weekly_job_drafts_next_week_once_and_notifies(ctx):
    client, repo, notifier = ctx
    add_recipes(client)
    client.post("/api/devices", json={"token": "device-token-123"}, headers=auth())

    assert client.post("/api/jobs/weekly-plan").status_code == 401
    assert client.post("/api/jobs/weekly-plan", headers={"X-Job-Token": "wrong"}).status_code == 401

    friday = date(2026, 11, 13)
    household_id = client.get("/api/me", headers=auth()).json()["household_id"]
    first = services.run_weekly_job(
        repo, None, notifier, "https://app.example", friday, random.Random(1)
    )
    assert first == {"generated": 1, "skipped": 0, "failed": 0}
    assert repo.get_plan(household_id, "2026-11-16") is not None
    assert notifier.sent == [
        (["device-token-123"], "Meal plan ready", "Your meal plan for next week is ready.")
    ]

    second = services.run_weekly_job(repo, None, notifier, "https://app.example", friday)
    assert second == {"generated": 0, "skipped": 1, "failed": 0}
    assert len(notifier.sent) == 1

    ok = client.post("/api/jobs/weekly-plan", headers={"X-Job-Token": "job-secret"})
    assert ok.status_code == 200 and set(ok.json()) == {"generated", "skipped", "failed"}
