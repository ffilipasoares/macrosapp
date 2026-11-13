"""The same storage contract, run against memory and (when the emulator is up) Firestore.

Start the emulator with ``firebase emulators:start`` and set
``FIRESTORE_EMULATOR_HOST=127.0.0.1:8085`` to include the Firestore run.
"""

import os
import uuid

import pytest

from app.models import GroceryItem, Ingredient, PlanMeal, Recipe, Rule, Settings, WeekPlan
from app.repo.memory import MemoryRepo


def _firestore_repo():
    from google.cloud import firestore

    from app.repo.firestore import FirestoreRepo

    return FirestoreRepo(firestore.Client(project="demo-mealplan"))


@pytest.fixture(params=["memory", "firestore"])
def repo(request):
    if request.param == "memory":
        return MemoryRepo()
    if not os.getenv("FIRESTORE_EMULATOR_HOST"):
        pytest.skip("Firestore emulator is not running")
    return _firestore_repo()


def test_household_is_created_once_and_found_by_shortcut_key(repo):
    uid = f"user-{uuid.uuid4().hex}"
    first = repo.household_for_user(uid, "a@example.com")
    again = repo.household_for_user(uid, "a@example.com")
    assert first.id == again.id and first.members == [uid] and len(first.shortcut_token) >= 24
    assert repo.household_by_shortcut_token(first.shortcut_token).id == first.id
    assert repo.household_by_shortcut_token("missing-" + uuid.uuid4().hex) is None
    assert first.id in {household.id for household in repo.list_households()}

    repo.add_device_token(first.id, "token-a")
    repo.add_device_token(first.id, "token-a")
    repo.add_device_token(first.id, "token-b")
    assert sorted(repo.household_for_user(uid, "").device_tokens) == ["token-a", "token-b"]
    repo.remove_device_tokens(first.id, ["token-a"])
    assert repo.household_for_user(uid, "").device_tokens == ["token-b"]


def test_settings_recipes_plans_and_groceries_round_trip(repo):
    household = repo.household_for_user(f"user-{uuid.uuid4().hex}", "b@example.com")
    hid = household.id

    assert repo.get_settings(hid) == Settings()
    settings = Settings(rules=[Rule(kind="min", count=2, tag="fish")], staples=["salt"])
    settings.slots["fri_lunch"].cook = True
    repo.save_settings(hid, settings)
    assert repo.get_settings(hid) == settings

    recipe = Recipe(
        title="Caldo verde",
        servings=4,
        protein="pork",
        ingredients=[Ingredient(name="kale", quantity=200, unit="g", aisle="produce")],
        steps=["Simmer."],
    )
    repo.save_recipe(hid, recipe)
    assert repo.get_recipe(hid, recipe.id) == recipe
    assert repo.list_recipes(hid) == [recipe]
    assert repo.get_recipe(hid, "missing") is None

    plan = WeekPlan(week_id="2026-11-16", meals={"mon_dinner": PlanMeal(recipe=recipe, portions=4)})
    repo.save_plan(hid, plan)
    repo.save_plan(hid, plan)  # same week id: overwrites
    assert repo.get_plan(hid, "2026-11-16") == plan
    assert repo.get_plan(hid, "2026-11-23") is None

    repo.add_groceries(
        hid,
        [
            GroceryItem(name="kale", quantity=200, unit="g", source="plan", week_id="2026-11-16"),
            GroceryItem(name="leek", source="plan", week_id="2026-11-09"),
            GroceryItem(name="oat milk", source="siri"),
        ],
    )
    repo.delete_plan_groceries(hid, "2026-11-16")
    assert sorted(item.name for item in repo.list_groceries(hid)) == ["leek", "oat milk"]

    repo.delete_recipe(hid, recipe.id)
    assert repo.list_recipes(hid) == []
