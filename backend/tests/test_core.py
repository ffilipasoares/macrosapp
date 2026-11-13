"""Tests for the pure logic: planning rules, scaling and merging."""

import random
from datetime import date

import pytest

from app.core import planner
from app.core.grocery import build_grocery_lines, scale_ingredients
from app.core.ingredients import guess_aisle, normalize_name, normalize_unit
from app.core.weeks import next_week_id, parse_week_id, previous_week_ids, week_id
from app.models import Ingredient, Recipe, Rule, Settings

RULES = [Rule(kind="min", count=2, tag="chicken"), Rule(kind="min", count=2, tag="fish")]


def make_recipe(title: str, protein: str = "other", **extra) -> Recipe:
    return Recipe(id=title, title=title, protein=protein, **extra)


def library() -> list[Recipe]:
    proteins = ["chicken"] * 6 + ["fish"] * 5 + ["beef"] * 5 + ["vegetarian"] * 8
    return [make_recipe(f"{protein}-{index}", protein) for index, protein in enumerate(proteins)]


# Weeks ---------------------------------------------------------------------


def test_week_ids_are_mondays():
    assert week_id(date(2026, 11, 13)) == "2026-11-09"  # a Friday
    assert week_id(date(2026, 11, 9)) == "2026-11-09"
    assert next_week_id(date(2026, 11, 13)) == "2026-11-16"
    assert previous_week_ids("2026-11-16", 2) == ["2026-11-09", "2026-11-02"]
    with pytest.raises(ValueError):
        parse_week_id("2026-11-13")


# Planner -------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(50))
def test_plan_always_satisfies_rules_and_repeat_limit(seed):
    recipes = library()
    recent = {recipe.id for recipe in recipes[:10]}  # includes all 6 chicken recipes
    picks = planner.pick_recipes(recipes, 9, RULES, recent, 0.2, random.Random(seed))

    assert len(picks) == 9
    assert len({recipe.id for recipe in picks}) == 9
    assert sum(1 for recipe in picks if recipe.protein == "fish") >= 2
    assert sum(1 for recipe in picks if recipe.id in recent) <= 1
    # Only one repeat is allowed and every chicken recipe is recent, so the
    # chicken rule cannot be fully met; it must be reported, not silently broken.
    statuses = planner.rule_status(picks, 9, RULES, recent, 0.2)
    assert [status.ok for status in statuses] == [False, True, True]


@pytest.mark.parametrize("seed", range(50))
def test_plan_meets_min_rules_when_library_allows(seed):
    picks = planner.pick_recipes(library(), 9, RULES, set(), 0.2, random.Random(seed))
    assert all(status.ok for status in planner.rule_status(picks, 9, RULES, set(), 0.2))


def test_max_rule_is_never_exceeded():
    rules = [Rule(kind="max", count=1, tag="beef")]
    for seed in range(30):
        picks = planner.pick_recipes(library(), 9, rules, set(), 0.2, random.Random(seed))
        assert sum(1 for recipe in picks if recipe.protein == "beef") <= 1


def test_rules_can_match_tags_as_well_as_protein():
    recipes = [make_recipe("a", tags=["quick"]), make_recipe("b"), make_recipe("c")]
    rules = [Rule(kind="min", count=1, tag="quick")]
    picks = planner.pick_recipes(recipes, 1, rules, set(), 0.2, random.Random(1))
    assert [recipe.id for recipe in picks] == ["a"]


def test_small_library_returns_fewer_meals_instead_of_repeating():
    recipes = library()[:9]
    recent = {recipe.id for recipe in recipes}
    picks = planner.pick_recipes(recipes, 9, [], recent, 0.2, random.Random(0))
    assert len(picks) == 1  # 20% of 9 slots


def test_prefers_recipes_cooked_longest_ago():
    recipes = [
        make_recipe("last-week", last_planned_week="2026-11-02"),
        make_recipe("long-ago", last_planned_week="2026-06-01"),
        make_recipe("never"),
    ]
    picks = planner.pick_recipes(recipes, 2, [], set(), 0.2, random.Random(0))
    assert {recipe.id for recipe in picks} == {"never", "long-ago"}


def test_repeat_allowance():
    assert planner.max_repeats(9, 0.2) == 1
    assert planner.max_repeats(10, 0.2) == 2
    assert planner.max_repeats(4, 0.2) == 0


def test_alternatives_put_rule_keeping_swaps_first():
    recipes = library()
    by_id = {recipe.id: recipe for recipe in recipes}
    planned = {
        "mon_dinner": by_id["chicken-0"],
        "tue_dinner": by_id["chicken-1"],
        "wed_dinner": by_id["fish-6"],
        "thu_dinner": by_id["fish-7"],
    }
    options = planner.alternatives(planned, "wed_dinner", recipes, 4, RULES, set(), 0.2)

    assert all(option.recipe.id not in {r.id for r in planned.values()} for option in options)
    keeping = [option for option in options if option.keeps_rules]
    assert keeping and all(option.recipe.protein == "fish" for option in keeping)
    assert options[: len(keeping)] == keeping


# Ingredients ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Red Onions (diced)", "red onion"),
        ("Tomatoes", "tomato"),
        ("Cherry tomatoes", "cherry tomato"),
        ("Bay leaves", "bay leaf"),
        ("Hummus", "hummus"),
        ("Blueberries", "blueberry"),
        ("  olive   oil ", "olive oil"),
    ],
)
def test_normalize_name(raw, expected):
    assert normalize_name(raw) == expected


def test_normalize_unit():
    assert normalize_unit("Tablespoons") == "tbsp"
    assert normalize_unit("grams") == "g"
    assert normalize_unit("pieces") == ""
    assert normalize_unit(None) == ""


@pytest.mark.parametrize(
    ("name", "aisle"),
    [
        ("oat milk", "dairy_eggs"),
        ("eggs", "dairy_eggs"),
        ("chicken stock", "pantry"),
        ("chicken breast", "meat_fish"),
        ("frozen peas", "frozen"),
        ("toilet paper", "household"),
        ("red onion", "produce"),
        ("sourdough bread", "bakery"),
        ("mystery thing", "other"),
    ],
)
def test_guess_aisle(name, aisle):
    assert guess_aisle(name) == aisle


# Scaling and merging --------------------------------------------------------


def test_scale_recipe_to_portions():
    recipe = make_recipe(
        "stew",
        servings=4,
        ingredients=[
            Ingredient(name="beef", quantity=800, unit="g"),
            Ingredient(name="salt"),
        ],
    )
    scaled = scale_ingredients(recipe, 3)
    assert scaled[0].quantity == pytest.approx(600)
    assert scaled[1].quantity is None


def test_grocery_list_merges_scales_and_rounds_up():
    curry = make_recipe(
        "Curry",
        servings=4,
        ingredients=[
            Ingredient(name="Onions", quantity=2, aisle="produce"),
            Ingredient(name="chopped tomato", quantity=1, unit="tin", aisle="pantry"),
            Ingredient(name="rice", quantity=0.3, unit="kg", aisle="pantry"),
            Ingredient(name="olive oil", quantity=1, unit="tbsp", aisle="pantry"),
            Ingredient(name="salt"),
        ],
    )
    soup = make_recipe(
        "Soup",
        servings=2,
        ingredients=[
            Ingredient(name="onion", quantity=1, aisle="produce"),
            Ingredient(name="rice", quantity=100, unit="g", aisle="pantry"),
            Ingredient(name="olive oil", quantity=1, unit="tsp", aisle="pantry"),
        ],
    )
    # Curry for 3 (written for 4), soup for 2.
    lines = build_grocery_lines([(curry, 3), (soup, 2)], staples=["salt"])
    by_name = {line.name: line for line in lines}

    assert "salt" not in by_name
    assert (by_name["onion"].quantity, by_name["onion"].unit) == (3, "")  # 1.5 + 1, rounded up
    assert by_name["onion"].recipes == ["Curry", "Soup"]
    assert (by_name["chopped tomato"].quantity, by_name["chopped tomato"].unit) == (1, "can")
    assert (by_name["rice"].quantity, by_name["rice"].unit) == (325, "g")  # 225 g + 100 g
    assert (by_name["olive oil"].quantity, by_name["olive oil"].unit) == (3.25, "tsp")
    assert [line.aisle for line in lines] == sorted(line.aisle for line in lines)


def test_large_amounts_are_shown_in_bigger_units():
    recipe = make_recipe(
        "Roast",
        servings=2,
        ingredients=[
            Ingredient(name="potato", quantity=800, unit="g"),
            Ingredient(name="soy sauce", quantity=3, unit="tsp"),
        ],
    )
    by_name = {line.name: line for line in build_grocery_lines([(recipe, 4)])}
    assert (by_name["potato"].quantity, by_name["potato"].unit) == (1.6, "kg")
    assert (by_name["soy sauce"].quantity, by_name["soy sauce"].unit) == (2, "tbsp")


def test_settings_defaults_match_the_household_routine():
    settings = Settings()
    assert len(settings.slots) == 14
    assert settings.cook_slots() == [
        "mon_dinner", "tue_dinner", "wed_dinner", "thu_dinner", "fri_dinner",
        "sat_lunch", "sat_dinner", "sun_lunch", "sun_dinner",
    ]  # fmt: skip
    assert settings.slots["thu_dinner"].portions == 4
    assert not settings.slots["fri_lunch"].cook
