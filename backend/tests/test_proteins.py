import random
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import services
from app.ai.fake import FakeRecipeAI
from app.config import Config
from app.core.proteins import clash, cooking_method, fish_kinds
from app.main import create_app
from app.models import Ingredient, Recipe
from app.notify import LogNotifier
from app.repo.memory import MemoryRepo

AUTH = {"Authorization": "Bearer ana"}
WEEK = "2026-11-16"


def dish(title, protein, *ingredients, rid=None):
    return Recipe(
        id=rid or title.lower().replace(" ", "-"),
        title=title,
        protein=protein,
        ingredients=[Ingredient(name=n, quantity=1) for n in (ingredients or ["carrot"])],
    )


def test_fish_by_kind_and_meat_by_cooking_method():
    salmon = dish("Grilled salmon", "fish", "salmon fillet")
    assert fish_kinds(salmon) == {"salmon"}
    assert fish_kinds(dish("Bacalhau à Brás", "fish", "cod")) == {"cod"}
    assert cooking_method(dish("Caril de frango", "chicken")) == "curry"
    assert cooking_method(dish("Frango assado", "chicken")) == "roast"
    assert cooking_method(dish("Chicken with peppers", "chicken")) is None
    assert clash(salmon, dish("Salmão no forno", "fish", "salmon")) == "same fish: salmon"
    assert clash(salmon, dish("Cod with tomato", "fish", "cod")) is None
    curry = dish("Chicken curry", "chicken")
    assert clash(curry, dish("Caril de frango", "chicken", rid="x")) == "same chicken, curry"
    assert clash(curry, dish("Grilled chicken", "chicken")) is None
    assert clash(curry, dish("Beef curry", "beef")) is None  # different meat


def make():
    repo = MemoryRepo()
    client = TestClient(
        create_app(
            config=Config(push_enabled=False),
            repo=repo,
            ai=FakeRecipeAI(),
            notifier=LogNotifier(),
            verify_token=lambda t: {"uid": t, "email": "a@example.com", "email_verified": True},
        )
    )
    household_id = client.get("/api/me", headers=AUTH).json()["household_id"]
    settings = repo.get_settings(household_id)
    settings.slots = {
        k: v.model_copy(update={"cook": k.endswith("dinner")}) for k, v in settings.slots.items()
    }
    repo.save_settings(household_id, settings)
    return client, repo, household_id


def test_a_week_never_repeats_a_fish_or_a_meat_cooked_the_same_way():
    client, repo, household_id = make()
    library = [
        dish("Salmon traybake", "fish", "salmon", "broccoli"),
        dish("Salmon teriyaki", "fish", "salmon", "spinach"),
        dish("Salmon salad", "fish", "salmon", "lettuce"),
        dish("Chicken curry", "chicken", "chicken", "spinach"),
        dish("Caril de frango", "chicken", "chicken", "pepper"),
        dish("Grilled chicken", "chicken", "chicken", "courgette"),
        dish("Cod with tomato", "fish", "cod", "tomato"),
        dish("Lentil stew", "vegetarian", "lentils", "carrot"),
        dish("Omelette", "egg", "egg", "spinach"),
        dish("Pork stir-fry", "pork", "pork", "cabbage"),
    ]
    for recipe in library:
        repo.save_recipe(household_id, recipe)
    for seed in range(15):
        plan = services.generate_plan(repo, None, household_id, WEEK, random.Random(seed))
        meals = [meal.recipe for meal in plan.meals.values()]
        for i, a in enumerate(meals):
            for b in meals[i + 1 :]:
                assert clash(a, b) is None, (a.title, b.title)
        # And the swap button never brings one in.
        slot = next(iter(plan.meals))
        try:
            swapped = services.swap_meal(repo, household_id, WEEK, slot, random.Random(seed))
        except services.NotFound:
            continue
        others = [m.recipe for s, m in swapped.meals.items() if s != slot]
        assert all(clash(swapped.meals[slot].recipe, o) is None for o in others)


def test_how_often_a_week_replaces_the_balanced_default():
    client, repo, household_id = make()
    library = [
        dish("Salmon traybake", "fish", "salmon", "broccoli"),
        dish("Cod with tomato", "fish", "cod", "tomato"),
        dish("Hake stew", "fish", "hake", "pepper"),
        dish("Grilled sardines", "fish", "sardine", "lettuce"),
        dish("Chicken curry", "chicken", "chicken", "spinach"),
        dish("Grilled chicken", "chicken", "chicken", "courgette"),
        dish("Beef stew", "beef", "beef", "carrot"),
        dish("Pork stir-fry", "pork", "pork", "cabbage"),
        dish("Lentil soup", "vegetarian", "lentils", "carrot"),
        dish("Chickpea curry", "vegan", "chickpeas", "spinach"),
    ]
    for recipe in library:
        repo.save_recipe(household_id, recipe)
    settings = client.get("/api/settings", headers=AUTH).json()
    settings["meals_per_week"] = {"fish": 3, "red_meat": 0, "chicken": 2}
    assert client.put("/api/settings", json=settings, headers=AUTH).status_code == 200
    for seed in range(10):
        plan = services.generate_plan(repo, None, household_id, WEEK, random.Random(seed))
        proteins = [m.recipe.protein for m in plan.meals.values()]
        assert proteins.count("fish") == 3
        assert proteins.count("chicken") == 2
        assert not {"beef", "pork", "lamb"} & set(proteins)
    out = client.get(f"/api/plans/{WEEK}", headers=AUTH).json()
    chips = {
        s["group"]: (s["count"], s["target"], s["ok"]) for s in out["rule_status"] if s["group"]
    }
    assert chips == {"fish": (3, 3, True), "red_meat": (0, 0, True), "chicken": (2, 2, True)}
    bad = client.get("/api/settings", headers=AUTH).json()
    bad["meals_per_week"] = {"fish": 20}
    assert client.put("/api/settings", json=bad, headers=AUTH).status_code == 422


def test_simple_namespace_recipes_work_too():
    a = SimpleNamespace(id="a", title="Tuna pasta", protein="fish", tags=[], ingredients=[])
    b = SimpleNamespace(id="b", title="Tuna salad", protein="fish", tags=[], ingredients=[])
    assert clash(a, b) == "same fish: tuna"
