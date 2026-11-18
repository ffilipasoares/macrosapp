import random

from app import services
from app.models import Ingredient, Recipe
from app.repo.memory import MemoryRepo

WEEKS = ["2026-11-02", "2026-11-09", "2026-11-16", "2026-11-23", "2026-11-30"]


def setup(recipe_count: int):
    repo = MemoryRepo()
    household = repo.household_for_user("ana", "a@example.com")
    settings = repo.get_settings(household.id)
    settings.slots = {
        key: slot.model_copy(update={"cook": key.endswith("dinner")})
        for key, slot in settings.slots.items()
    }  # 7 dinners
    repo.save_settings(household.id, settings)
    for n in range(recipe_count):
        protein = ["chicken", "fish", "vegetarian", "beef", "egg"][n % 5]
        repo.save_recipe(
            household.id,
            Recipe(
                title=f"Dish {n}",
                protein=protein,
                ingredients=[Ingredient(name="lentils" if n % 7 == 0 else "carrot", quantity=1)],
            ),
        )
    return repo, household.id


def test_no_recipe_from_last_week_and_half_new_from_two_weeks_ago():
    repo, household_id = setup(30)
    plans = [
        services.generate_plan(repo, None, household_id, week, random.Random(i))
        for i, week in enumerate(WEEKS)
    ]
    ids = [{meal.recipe.id for meal in plan.meals.values()} for plan in plans]
    for i in range(1, len(ids)):
        assert not ids[i] & ids[i - 1], f"{WEEKS[i]} repeats last week"
    for i in range(2, len(ids)):
        assert len(ids[i] & ids[i - 2]) <= len(ids[i]) // 2, f"{WEEKS[i]} repeats too much"


def test_a_small_library_leaves_meals_empty_rather_than_repeat_last_week():
    repo, household_id = setup(9)
    first = services.generate_plan(repo, None, household_id, WEEKS[0], random.Random(1))
    second = services.generate_plan(repo, None, household_id, WEEKS[1], random.Random(2))
    assert len(first.meals) == 7
    assert len(second.meals) == 2  # only 2 recipes were not cooked the week before
    assert second.notes  # and the plan says why some meals are empty


def test_last_week_recipes_can_be_chosen_by_hand_freely_but_are_never_swapped_in():
    repo, household_id = setup(9)
    services.generate_plan(repo, None, household_id, WEEKS[0], random.Random(1))
    services.generate_plan(repo, None, household_id, WEEKS[1], random.Random(2))
    last_week = {m.recipe.id for m in repo.get_plan(household_id, WEEKS[0]).meals.values()}
    options = services.meal_alternatives(repo, household_id, WEEKS[1], "sun_dinner")
    marked = {o.recipe.id for o in options if o.last_week}
    # Choosing by hand is free: nothing is flagged as breaking a rule for it.
    assert all(o.keeps_rules for o in options if o.last_week)
    assert marked == last_week - {
        m.recipe.id for m in repo.get_plan(household_id, WEEKS[1]).meals.values()
    }
    plan = repo.get_plan(household_id, WEEKS[1])
    slot = next(iter(plan.meals))
    for seed in range(10):
        try:
            swapped = services.swap_meal(repo, household_id, WEEKS[1], slot, random.Random(seed))
        except services.NotFound:
            break
        assert swapped.meals[slot].recipe.id not in last_week
