import random

from fastapi.testclient import TestClient

from app import services
from app.ai.fake import FakeRecipeAI
from app.config import Config
from app.main import create_app
from app.notify import LogNotifier
from app.repo.memory import MemoryRepo

AUTH = {"Authorization": "Bearer ana"}
WEEK = "2026-11-16"


def make(language="pt"):
    repo, ai = MemoryRepo(), FakeRecipeAI()
    client = TestClient(
        create_app(
            config=Config(push_enabled=False),
            repo=repo,
            ai=ai,
            notifier=LogNotifier(),
            verify_token=lambda t: {"uid": t, "email": "a@example.com", "email_verified": True},
        )
    )
    settings = client.get("/api/settings", headers=AUTH).json()
    settings["language"] = language
    settings["slots"] = {
        k: {"cook": k in ("mon_dinner", "tue_dinner"), "portions": 2} for k in settings["slots"]
    }
    client.put("/api/settings", json=settings, headers=AUTH)
    household_id = client.get("/api/me", headers=AUTH).json()["household_id"]
    return client, repo, ai, household_id


def english_recipe(title, *ingredients):
    return {
        "title": title,
        "language": "en",
        "steps": ["Cook it."],
        "ingredients": [{"name": n, "quantity": q, "unit": u} for n, q, u in ingredients],
    }


def test_the_language_is_known_from_the_start():
    client, _, _, _ = make("pt")
    assert client.get("/api/me", headers=AUTH).json()["language"] == "pt"
    assert make("en")[0].get("/api/me", headers=AUTH).json()["language"] == "en"


def test_recipes_are_shown_in_portuguese_with_english_names_underneath():
    client, repo, ai, household_id = make()
    saved = client.post(
        "/api/recipes", json=english_recipe("Spinach pie", ("spinach", 200, "g")), headers=AUTH
    ).json()
    assert saved["title"] == "[pt] Spinach pie" and saved["language"] == "pt"
    ingredient = saved["ingredients"][0]
    assert (ingredient["name"], ingredient["label"]) == ("spinach", "[pt] spinach")
    # Translated once: listing again asks nothing more.
    calls = len(ai.calls)
    client.get("/api/recipes", headers=AUTH)
    assert len(ai.calls) == calls


def test_a_recipe_written_in_portuguese_gets_english_names():
    client, _, _, _ = make()
    body = {
        "title": "Sopa de legumes",
        "language": "pt",
        "ingredients": [{"name": "[pt] carrot", "label": "[pt] carrot", "quantity": 2}],
    }
    saved = client.post("/api/recipes", json=body, headers=AUTH).json()
    assert saved["title"] == "Sopa de legumes"
    assert (saved["ingredients"][0]["name"], saved["ingredients"][0]["label"]) == (
        "carrot",
        "[pt] carrot",
    )


def test_switching_language_translates_the_library_once():
    client, repo, ai, household_id = make("en")
    client.post("/api/recipes", json=english_recipe("Soup", ("leek", 1, "")), headers=AUTH)
    settings = client.get("/api/settings", headers=AUTH).json()
    client.put("/api/settings", json={**settings, "language": "pt"}, headers=AUTH)
    titles = [r["title"] for r in client.get("/api/recipes", headers=AUTH).json()]
    assert titles == ["[pt] Soup"]
    # And back.
    client.put("/api/settings", json={**settings, "language": "en"}, headers=AUTH)
    recipe = client.get("/api/recipes", headers=AUTH).json()[0]
    assert recipe["title"] == "Soup" and recipe["ingredients"][0]["label"] == ""


def test_the_plan_list_and_warnings_speak_portuguese():
    client, repo, _, household_id = make()
    settings = client.get("/api/settings", headers=AUTH).json()
    client.put(
        "/api/settings",
        json={
            **settings,
            "allergies": ["milk"],
            "rules": [{"kind": "min", "count": 1, "tag": "fish"}],
        },
        headers=AUTH,
    )
    client.post(
        "/api/recipes",
        json=english_recipe("Spinach pie", ("spinach", 200, "g"), ("cheese", 100, "g")),
        headers=AUTH,
    )
    client.post("/api/recipes", json=english_recipe("Cod", ("cod", 2, "")), headers=AUTH)
    plan = client.post(f"/api/plans/{WEEK}/generate", headers=AUTH).json()
    assert plan["rule_status"][0]["label"] == "Pelo menos 1 peixe"
    assert plan["rule_status"][-1]["label"].startswith("No máximo")
    assert {c["label"] for c in plan["balance"]["checks"]} >= {"Peixe ou marisco", "Carne vermelha"}
    assert any("Só foi possível preencher" in note for note in plan["notes"])
    options = client.get(f"/api/plans/{WEEK}/meals/tue_dinner/alternatives", headers=AUTH).json()
    pie = next(o for o in options if o["recipe"]["title"] == "[pt] Spinach pie")
    assert pie["warnings"] == ["contém leite"]
    # The grocery list: Portuguese names and packs.
    client.put(
        f"/api/plans/{WEEK}/meals/tue_dinner",
        json={"recipe_id": pie["recipe"]["id"], "portions": 2},
        headers=AUTH,
    )
    client.post(f"/api/plans/{WEEK}/approve", headers=AUTH)
    spinach = next(i for i in repo.list_groceries(household_id) if i.name == "spinach")
    assert (spinach.label, spinach.pack) == ("[pt] spinach", "1 saco (300 g)")


def test_portuguese_pantry_food_keeps_its_words_and_gets_english_names():
    client, repo, _, household_id = make()
    items = client.post("/api/pantry/text", json={"text": "2 [pt] eggs"}, headers=AUTH).json()
    assert [(i["name"], i["label"]) for i in items] == [("egg", "[pt] eggs")]
    seen = client.post(
        "/api/pantry/read/audio",
        files={"file": ("note.m4a", b"0" * 200, "audio/mp4")},
        headers=AUTH,
    ).json()
    assert {d["label"] for d in seen} == {"[pt] courgette", "[pt] rice"}


def test_notifications_in_the_household_language():
    client, repo, _, household_id = make()
    for n in range(3):
        client.post("/api/recipes", json=english_recipe(f"Dish {n}", ("rice", 1, "")), headers=AUTH)
    client.post("/api/devices", json={"token": "device-token-123"}, headers=AUTH)
    notifier = LogNotifier()
    from datetime import date

    services.run_weekly_job(repo, None, notifier, "", date(2026, 11, 13), random.Random(1))
    assert notifier.sent[0][1] == "Plano de refeições pronto"
