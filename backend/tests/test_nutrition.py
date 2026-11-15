"""Macros: per-ingredient estimates, exact totals, and portions."""

import pytest
from fastapi.testclient import TestClient

from app.ai.fake import FakeRecipeAI
from app.config import Config
from app.core.nutrition import grams_of, portion_factor
from app.main import create_app
from app.models import Ingredient, IngredientNutrition, Recipe
from app.notify import LogNotifier
from app.repo.memory import MemoryRepo

AUTH = {"Authorization": "Bearer ana"}


def per100(
    kcal: float, protein: float, carbs: float, fat: float, grams_per_unit: float | None = None
):
    return IngredientNutrition(
        grams_per_unit=grams_per_unit,
        kcal_per_100g=kcal,
        protein_per_100g=protein,
        carbs_per_100g=carbs,
        fat_per_100g=fat,
    )


def test_totals_add_up_every_ingredient_by_weight():
    recipe = Recipe(
        title="Chicken and rice",
        servings=2,
        ingredients=[
            Ingredient(
                name="chicken breast", quantity=300, unit="g", nutrition=per100(120, 23, 0, 2.6)
            ),
            Ingredient(name="rice", quantity=0.15, unit="kg", nutrition=per100(360, 7, 79, 0.6)),
            Ingredient(
                name="olive oil", quantity=1, unit="tbsp", nutrition=per100(884, 0, 0, 100, 13.5)
            ),
            Ingredient(name="onion", quantity=1, nutrition=per100(40, 1.1, 9.3, 0.1, 150)),
            Ingredient(name="salt"),  # to taste: no amount, so not counted and not missing
        ],
    )
    m = recipe.macros
    assert m is not None
    # 300 g chicken + 150 g rice + 13.5 g oil + 150 g onion
    assert m.weight_g == pytest.approx(613.5)
    assert m.kcal == pytest.approx(360 + 540 + 119.34 + 60, abs=0.1)
    assert m.protein_g == pytest.approx(69 + 10.5 + 0 + 1.65, abs=0.1)
    assert m.missing == []


def test_missing_estimates_are_listed_and_none_known_means_no_macros():
    partial = Recipe(
        title="Soup",
        ingredients=[
            Ingredient(name="lentil", quantity=200, unit="g", nutrition=per100(350, 25, 60, 1)),
            Ingredient(name="mystery spice", quantity=2, unit="tsp"),
            Ingredient(
                name="leek", quantity=1, nutrition=per100(61, 1.5, 14, 0.3)
            ),  # no unit weight
        ],
    )
    assert partial.macros.kcal == 700 and partial.macros.missing == ["mystery spice", "leek"]
    assert (
        Recipe(title="Blank", ingredients=[Ingredient(name="water", quantity=1, unit="l")]).macros
        is None
    )


def test_grams_and_portions():
    assert grams_of(2, "kg", None) == 2000
    assert grams_of(2, "g", 999) == 2  # grams are grams, whatever the estimate says
    assert grams_of(3, "", 50) == 150
    assert grams_of(None, "g", None) is None
    assert portion_factor(4, 1200, "serving", 400) == 0.25
    assert portion_factor(4, 1200, "grams", 400) == pytest.approx(1 / 3)
    assert portion_factor(4, 0, "grams", 400) == 0.25  # no weight known: fall back to a serving


@pytest.fixture
def ctx():
    repo, ai = MemoryRepo(), FakeRecipeAI()
    app = create_app(
        config=Config(push_enabled=False),
        repo=repo,
        ai=ai,
        notifier=LogNotifier(),
        verify_token=lambda token: {"uid": token, "email": "a@example.com", "email_verified": True},
        read_link=lambda url: (_ for _ in ()).throw(AssertionError("no web in these tests")),
    )
    return TestClient(app), repo, ai


def nutrition_calls(ai: FakeRecipeAI) -> list[list[str]]:
    return [names for kind, names in ai.calls if kind == "nutrition"]


def test_saving_a_recipe_estimates_its_macros_and_ignores_values_sent_by_the_app(ctx):
    client, _, ai = ctx
    sent = {
        "grams_per_unit": 1,
        "kcal_per_100g": 999,
        "protein_per_100g": 0,
        "carbs_per_100g": 0,
        "fat_per_100g": 0,
    }
    recipe = client.post(
        "/api/recipes",
        json={
            "title": "Omelette",
            "servings": 1,
            "ingredients": [
                {"name": "egg", "quantity": 3, "nutrition": sent},
                {"name": "butter", "quantity": 10, "unit": "g"},
                {"name": "salt"},
            ],
        },
        headers=AUTH,
    ).json()
    assert nutrition_calls(ai) == [["egg", "butter"]]
    assert recipe["ingredients"][0]["nutrition"]["kcal_per_100g"] == 200  # the estimate, not 999
    # 3 eggs x 100 g + 10 g butter, at 200 kcal and 20 g protein per 100 g
    assert recipe["macros"]["weight_g"] == 310 and recipe["macros"]["kcal"] == 620
    assert recipe["macros"]["protein_g"] == 62 and recipe["macros"]["missing"] == []


def test_editing_reuses_estimates_and_only_asks_about_new_ingredients(ctx):
    client, _, ai = ctx
    recipe = client.post(
        "/api/recipes",
        json={
            "title": "Rice bowl",
            "ingredients": [
                {"name": "rice", "quantity": 100, "unit": "g"},
                {"name": "egg", "quantity": 1},
            ],
        },
        headers=AUTH,
    ).json()
    assert recipe["macros"]["kcal"] == 400

    # Twice the rice: no new estimate, exact new totals.
    doubled = {
        **recipe,
        "ingredients": [{**recipe["ingredients"][0], "quantity": 200}, recipe["ingredients"][1]],
    }
    updated = client.put(f"/api/recipes/{recipe['id']}", json=doubled, headers=AUTH).json()
    assert len(nutrition_calls(ai)) == 1 and updated["macros"]["kcal"] == 600

    # Renaming one ingredient asks only about that one, even if the app sends the old estimate.
    renamed = {
        **updated,
        "ingredients": [updated["ingredients"][0], {**updated["ingredients"][1], "name": "tofu"}],
    }
    client.put(f"/api/recipes/{recipe['id']}", json=renamed, headers=AUTH)
    assert nutrition_calls(ai)[-1] == ["tofu"]


def test_unknown_ingredients_are_reported(ctx):
    client, _, _ = ctx
    recipe = client.post(
        "/api/recipes",
        json={
            "title": "Stew",
            "ingredients": [
                {"name": "beef", "quantity": 500, "unit": "g"},
                {"name": "unknown herb", "quantity": 2, "unit": "tsp"},
            ],
        },
        headers=AUTH,
    ).json()
    assert recipe["macros"]["missing"] == ["unknown herb"] and recipe["macros"]["kcal"] == 1000


def test_recalculate_and_planned_meals_pick_up_new_macros(ctx):
    client, repo, ai = ctx
    household_id = client.get("/api/me", headers=AUTH).json()["household_id"]
    old = Recipe(
        title="Old favourite", ingredients=[Ingredient(name="pasta", quantity=200, unit="g")]
    )
    repo.save_recipe(household_id, old)
    settings = client.get("/api/settings", headers=AUTH).json()
    settings["slots"] = {
        key: {"cook": key == "mon_dinner", "portions": 2} for key in settings["slots"]
    }
    client.put("/api/settings", json=settings, headers=AUTH)
    plan = client.post("/api/plans/2026-11-16/generate", headers=AUTH).json()
    assert plan["meals"]["mon_dinner"]["recipe"]["macros"] is None

    recalculated = client.post(f"/api/recipes/{old.id}/macros", headers=AUTH).json()
    assert recalculated["macros"]["kcal"] == 400
    plan = client.get("/api/plans/2026-11-16", headers=AUTH).json()
    assert plan["meals"]["mon_dinner"]["recipe"]["macros"]["kcal"] == 400
    assert client.post("/api/recipes/missing/macros", headers=AUTH).status_code == 404


def test_reference_portion_setting(ctx):
    client, _, _ = ctx
    settings = client.get("/api/settings", headers=AUTH).json()
    assert settings["reference_portion"] == {"kind": "serving", "grams": 400}
    settings["reference_portion"] = {"kind": "grams", "grams": 350}
    saved = client.put("/api/settings", json=settings, headers=AUTH).json()
    assert saved["reference_portion"] == {"kind": "grams", "grams": 350}
    assert client.get("/api/settings", headers=AUTH).json()["reference_portion"]["grams"] == 350
    settings["reference_portion"] = {"kind": "grams", "grams": 5}
    assert client.put("/api/settings", json=settings, headers=AUTH).status_code == 422


def test_gemini_estimates_line_up_with_ingredients():
    from app.ai import gemini

    ai = gemini.GeminiRecipeAI.__new__(gemini.GeminiRecipeAI)
    seen = {}

    def structured(contents, schema, what):
        seen["prompt"] = contents[0]
        return gemini._AiNutritionList(
            items=[
                gemini._AiNutrition(
                    index=1,
                    grams_per_unit=13.5,
                    kcal_per_100g=884,
                    protein_per_100g=0,
                    carbs_per_100g=0,
                    fat_per_100g=100,
                ),
                gemini._AiNutrition(
                    index=0,
                    grams_per_unit=None,
                    kcal_per_100g=165,
                    protein_per_100g=31,
                    carbs_per_100g=0,
                    fat_per_100g=3.6,
                ),
                gemini._AiNutrition(
                    index=7,
                    grams_per_unit=1,
                    kcal_per_100g=1,
                    protein_per_100g=0,
                    carbs_per_100g=0,
                    fat_per_100g=0,
                ),
                gemini._AiNutrition(
                    index=2,
                    grams_per_unit=1,
                    kcal_per_100g=5000,
                    protein_per_100g=0,
                    carbs_per_100g=0,
                    fat_per_100g=0,
                ),
            ]
        )

    ai._structured = structured
    items = [
        Ingredient(name="chicken breast", quantity=250, unit="g"),
        Ingredient(name="olive oil", quantity=1.5, unit="tbsp"),
        Ingredient(name="salt"),
    ]
    estimates = ai.estimate_nutrition(items)
    assert "0. 250 g chicken breast" in seen["prompt"] and "1. 1.5 tbsp olive oil" in seen["prompt"]
    assert "2.  (counted whole) salt" in seen["prompt"]
    assert estimates[0].kcal_per_100g == 165 and estimates[1].grams_per_unit == 13.5
    assert estimates[2] is None  # 5000 kcal per 100 g is impossible, so it is dropped
