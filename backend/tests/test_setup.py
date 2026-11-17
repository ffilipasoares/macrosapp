import random
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app import services
from app.ai.fake import FakeRecipeAI
from app.config import Config
from app.core.allergens import found_in, missing_equipment
from app.main import create_app
from app.models import Household, Ingredient, Recipe, Settings
from app.notify import LogNotifier
from app.repo.memory import MemoryRepo

AUTH = {"Authorization": "Bearer ana"}
WEEK = "2026-11-16"


def make(repo=None):
    repo = repo or MemoryRepo()
    client = TestClient(
        create_app(
            config=Config(push_enabled=False),
            repo=repo,
            ai=FakeRecipeAI(),
            notifier=LogNotifier(),
            verify_token=lambda t: {"uid": t, "email": "a@example.com", "email_verified": True},
        )
    )
    return client, repo


def recipe(title, *ingredients, protein="chicken", equipment=()):
    return Recipe(
        title=title,
        protein=protein,
        ingredients=[Ingredient(name=n) for n in ingredients],
        equipment=list(equipment),
    )


def save(client, **changes):
    settings = client.get("/api/settings", headers=AUTH).json()
    settings.update(changes)
    response = client.put("/api/settings", json=settings, headers=AUTH)
    assert response.status_code == 200, response.text
    return response.json()


# Plan day ----------------------------------------------------------------------------


def test_the_plan_is_due_from_the_chosen_day_and_hour():
    settings = Settings(plan_day="sun", plan_hour=10)
    lisbon = datetime(2026, 11, 22, 9, 59).astimezone()  # Sunday
    assert not services.plan_is_due(settings, lisbon.replace(hour=9, minute=59))
    assert services.plan_is_due(settings, lisbon.replace(hour=10, minute=0))
    # Earlier in the week it is not due yet; Friday is the default.
    assert not services.plan_is_due(settings, datetime(2026, 11, 20, 18).astimezone())
    assert Settings().plan_day == "fri" and Settings().plan_hour == 17


def test_the_hourly_job_plans_each_household_on_its_own_day():
    client, repo = make()
    for n in range(4):
        client.post(
            "/api/recipes",
            json={"title": f"Dish {n}", "ingredients": [{"name": "rice", "quantity": 1}]},
            headers=AUTH,
        )
    save(client, plan_day="sun", plan_hour=9)
    household_id = client.get("/api/me", headers=AUTH).json()["household_id"]
    notifier = LogNotifier()

    # Friday 18:00 Lisbon: a Sunday household waits.
    friday = datetime(2026, 11, 20, 18, tzinfo=UTC)
    result = services.run_weekly_job(repo, None, notifier, "", now=friday)
    assert result["waiting"] == 1 and result["generated"] == 0

    # Sunday 9:00 Lisbon: the week starting tomorrow is planned.
    sunday = datetime(2026, 11, 22, 9, 0, tzinfo=UTC)
    result = services.run_weekly_job(repo, None, notifier, "", rng=random.Random(1), now=sunday)
    assert result["generated"] == 1
    assert repo.get_plan(household_id, "2026-11-23") is not None

    # The next hourly run does nothing more.
    later = datetime(2026, 11, 22, 10, 0, tzinfo=UTC)
    assert services.run_weekly_job(repo, None, notifier, "", now=later)["skipped"] == 1


# Allergies, avoided foods, equipment ------------------------------------------------


def test_allergens_are_found_by_word_and_by_the_ai_verdict():
    pasta = recipe("Creamy pasta", "spaghetti", "cream", "parmesan")
    assert found_in(pasta, ["gluten", "milk"], []) == ["gluten", "milk"]
    # Whole words only: eggplant is not egg, coconut is not a tree nut.
    curry = recipe("Curry", "eggplant", "coconut milk")
    assert found_in(curry, ["eggs", "tree nuts"], []) == []
    # Something the words cannot see, but the AI said.
    hidden = recipe("Stew", "stock cube")
    hidden.diet_fit = {"free of celery": False}
    assert found_in(hidden, ["celery"], []) == ["celery"]
    # Your own allergy or avoided food, by name.
    assert found_in(recipe("Salad", "kiwi", "mushrooms"), ["kiwi"], ["mushroom"]) == [
        "kiwi",
        "mushroom",
    ]


def test_equipment_only_counts_once_asked():
    roast = recipe("Roast", "chicken", equipment=["oven"])
    assert missing_equipment(roast, None) == []
    assert missing_equipment(roast, ["air fryer"]) == ["oven"]
    assert missing_equipment(roast, ["oven"]) == []


def test_allergies_avoided_foods_and_missing_equipment_stay_out_of_the_plan():
    client, _ = make()
    save(
        client,
        allergies=["Milk"],
        avoid=["mushroom"],
        equipment=["oven"],
        slots={
            k: {"cook": k in ("mon_dinner", "tue_dinner"), "portions": 2}
            for k in client.get("/api/settings", headers=AUTH).json()["slots"]
        },
    )
    bodies = [
        ("Cheese toastie", ["bread", "cheese"], []),
        ("Mushroom risotto", ["rice", "mushrooms"], []),
        ("Air fryer wings", ["chicken wings"], ["air fryer"]),
        ("Baked cod", ["cod", "lemon"], ["oven"]),
        ("Chicken stir fry", ["chicken", "pepper"], []),
    ]
    for title, ingredients, equipment in bodies:
        client.post(
            "/api/recipes",
            json={
                "title": title,
                "ingredients": [{"name": n, "quantity": 1} for n in ingredients],
                "equipment": equipment,
            },
            headers=AUTH,
        )
    plan = client.post(f"/api/plans/{WEEK}/generate", headers=AUTH).json()
    titles = {m["recipe"]["title"] for m in plan["meals"].values()}
    assert titles == {"Baked cod", "Chicken stir fry"}

    # Still choosable by hand, with the reason shown.
    options = client.get(f"/api/plans/{WEEK}/meals/mon_dinner/alternatives", headers=AUTH).json()
    warnings = {o["recipe"]["title"]: o["warnings"] for o in options}
    assert warnings["Cheese toastie"] == ["contains milk"]
    assert warnings["Mushroom risotto"] == ["contains mushroom"]
    assert warnings["Air fryer wings"] == ["needs an air fryer"]
    # And listed after the ones without a warning.
    order = [o["recipe"]["title"] for o in options]
    assert order.index("Cheese toastie") > order.index("Baked cod") or "Baked cod" not in order


def test_settings_tidy_allergies_and_reject_unknown_equipment():
    client, _ = make()
    saved = save(client, allergies=["  Tree   Nuts", "tree nuts"], avoid=["Coriander"])
    assert saved["allergies"] == ["tree nuts"] and saved["avoid"] == ["coriander"]
    settings = client.get("/api/settings", headers=AUTH).json()
    settings["equipment"] = ["teleporter"]
    assert client.put("/api/settings", json=settings, headers=AUTH).status_code == 422


# First-use setup ------------------------------------------------------------------------


def test_new_households_go_through_setup_once():
    client, _ = make()
    assert client.get("/api/me", headers=AUTH).json()["setup_done"] is False
    assert client.post("/api/setup/done", headers=AUTH).status_code == 204
    assert client.get("/api/me", headers=AUTH).json()["setup_done"] is True


def test_households_from_before_the_setup_are_treated_as_set_up():
    stored = {"members": ["ana"], "owner_email": "a@example.com", "shortcut_token": "x"}
    assert Household(**stored).setup_done is True
