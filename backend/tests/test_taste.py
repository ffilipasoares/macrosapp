import random
from datetime import date, timedelta

from fastapi.testclient import TestClient

from app import services
from app.ai.fake import FakeRecipeAI
from app.config import Config
from app.core import planner
from app.core import taste as taste_logic
from app.main import create_app
from app.models import Ingredient, Recipe, Settings, TasteProfile
from app.notify import LogNotifier
from app.repo.memory import MemoryRepo

AUTH = {"Authorization": "Bearer ana"}
WEEK = "2026-11-16"
TODAY = date(2026, 11, 18)


def recipe(rid, protein="chicken", minutes=None, tags=()):
    return Recipe(
        id=rid,
        title=rid.title(),
        protein=protein,
        prep_minutes=minutes,
        tags=list(tags),
        ingredients=[Ingredient(name="carrot", quantity=1)],
    )


# The taste profile --------------------------------------------------------------------------


def test_actions_nudge_the_recipe_and_its_traits_and_fade_with_time():
    salmon = recipe("salmon", "fish", 20, ["traybake"])
    profile = taste_logic.nudge(TasteProfile(), salmon, taste_logic.CHOSE, TODAY)
    assert taste_logic.score(profile, salmon, TODAY) > 1.5  # recipe + fish + traybake + quick
    cod = recipe("cod", "fish")
    assert 0 < taste_logic.score(profile, cod, TODAY) < 0.5  # only through "fish"
    later = TODAY + timedelta(days=taste_logic.HALF_LIFE_DAYS)
    assert taste_logic.score(profile, salmon, later) == round(
        taste_logic.score(profile, salmon, TODAY) / 2, 4
    )
    likes, dislikes = taste_logic.leanings(profile, TODAY)
    assert "protein:fish" in likes and dislikes == []


# Learning from what the household does ------------------------------------------------------


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
        k: v.model_copy(update={"cook": k == "mon_dinner"}) for k, v in settings.slots.items()
    }
    repo.save_settings(household_id, settings)
    return client, repo, household_id


def add(repo, household_id, *recipes):
    for r in recipes:
        repo.save_recipe(household_id, r)


def test_choosing_by_hand_counts_for_and_the_replaced_meal_against():
    client, repo, household_id = make()
    add(repo, household_id, recipe("lamb", "lamb"), recipe("salmon", "fish"))
    # The app planned lamb; salmon was chosen in its place.
    services.set_meal(repo, household_id, WEEK, "mon_dinner", "lamb", None, chosen=False)
    client.put(f"/api/plans/{WEEK}/meals/mon_dinner", json={"recipe_id": "salmon"}, headers=AUTH)
    taste = repo.get_taste(household_id)
    today = services.local_today(repo.get_settings(household_id))
    assert taste_logic.score(taste, recipe("salmon", "fish"), today) > 0
    assert taste_logic.score(taste, recipe("lamb", "lamb"), today) < 0


def test_approving_counts_once():
    client, repo, household_id = make()
    add(repo, household_id, recipe("salmon", "fish"))
    client.put(f"/api/plans/{WEEK}/meals/mon_dinner", json={"recipe_id": "salmon"}, headers=AUTH)
    before = repo.get_taste(household_id).scores["recipe:salmon"][0]
    client.post(f"/api/plans/{WEEK}/approve", headers=AUTH)
    after = repo.get_taste(household_id).scores["recipe:salmon"][0]
    client.post(f"/api/plans/{WEEK}/approve", headers=AUTH)
    assert after > before and repo.get_taste(household_id).scores["recipe:salmon"][0] == after


def test_heart_and_not_for_us():
    client, repo, household_id = make()
    add(repo, household_id, *[recipe(f"dish{n}") for n in range(6)])
    liked = client.post("/api/recipes/dish3/feedback", json={"liked": True}, headers=AUTH).json()
    assert liked["liked"] is True
    # The liked recipe wins the plan's single meal every time.
    for seed in range(5):
        plan = services.generate_plan(repo, None, household_id, WEEK, random.Random(seed))
        assert plan.meals["mon_dinner"].recipe.id == "dish3"
        repo.save_plan(household_id, plan.model_copy(update={"meals": {}}))
    out = client.get(f"/api/plans/{WEEK}", headers=AUTH).json()
    client.post(f"/api/plans/{WEEK}/generate", headers=AUTH)
    out = client.get(f"/api/plans/{WEEK}", headers=AUTH).json()
    assert "You ♥ this" in out["meals"]["mon_dinner"]["reasons"]
    # "Not for us": never planned or swapped in again, still choosable by hand.
    client.post("/api/recipes/dish3/feedback", json={"not_for_us": True}, headers=AUTH)
    for seed in range(10):
        plan = services.generate_plan(repo, None, household_id, WEEK, random.Random(seed))
        assert plan.meals["mon_dinner"].recipe.id != "dish3"
    options = client.get(f"/api/plans/{WEEK}/meals/mon_dinner/alternatives", headers=AUTH).json()
    assert "dish3" in [o["recipe"]["id"] for o in options]


def test_not_for_us_on_a_planned_meal_swaps_it_and_remembers_new_ideas_by_title():
    client, repo, household_id = make()
    add(repo, household_id, recipe("dish1"), recipe("dish2"))
    client.put(f"/api/plans/{WEEK}/meals/mon_dinner", json={"recipe_id": "dish1"}, headers=AUTH)
    plan = client.post(f"/api/plans/{WEEK}/meals/mon_dinner/not-for-us", headers=AUTH).json()
    assert plan["meals"]["mon_dinner"]["recipe"]["id"] == "dish2"
    assert repo.get_recipe(household_id, "dish1").not_for_us
    # A web idea never saved is remembered by its title.
    stored = repo.get_plan(household_id, WEEK)
    stored.meals["mon_dinner"].recipe = recipe("web-idea")
    repo.save_plan(household_id, stored)
    client.post(f"/api/plans/{WEEK}/meals/mon_dinner/not-for-us", headers=AUTH)
    assert "Web-Idea" in repo.get_taste(household_id).blocked


def test_what_the_app_learned_and_starting_again():
    client, repo, household_id = make()
    add(repo, household_id, recipe("salmon", "fish", 20))
    client.post("/api/recipes/salmon/feedback", json={"liked": True}, headers=AUTH)
    learned = client.get("/api/taste", headers=AUTH).json()
    assert "protein:fish" in learned["likes"] and "tag:quick" in learned["likes"]
    assert client.delete("/api/taste", headers=AUTH).status_code == 204
    assert client.get("/api/taste", headers=AUTH).json() == {"likes": [], "dislikes": []}


def test_the_web_search_asks_for_the_household_s_leanings_and_time():
    settings = Settings(cook_minutes_weekday=30)
    profile = taste_logic.nudge(TasteProfile(), recipe("x", "fish", None, ["traybake"]), 3.0, TODAY)
    profile = taste_logic.nudge(profile, recipe("y", "lamb"), -3.0, TODAY)
    wishes = services.search_wishes(settings, profile, TODAY)
    assert wishes[0] == "most ready in under 30 minutes"
    assert "fish" in wishes[1] and wishes[2] == "not lamb"


# Something new now and then -----------------------------------------------------------------


def test_one_pick_in_five_ignores_taste():
    recipes = [recipe(f"r{n}") for n in range(10)]
    favourites = {f"r{n}": 5.0 for n in range(5)}
    picks = planner.pick_recipes(recipes, 5, [], planner.Recent(), random.Random(1), favourites)
    assert sum(1 for r in picks if r.id in favourites) == 4


# Cooking time --------------------------------------------------------------------------------


def test_recipes_go_where_their_time_fits():
    quick, slow, unknown = recipe("quick", minutes=20), recipe("slow", minutes=90), recipe("u")
    assert planner.fits_times([slow, quick], [30, None])
    assert not planner.fits_times([slow, slow.model_copy(update={"id": "s2"})], [30, None])
    placed = planner.assign_slots(
        [slow, quick, unknown], ["mon", "tue", "sat"], [30, 30, None], random.Random(0)
    )
    assert placed["sat"].id == "slow"


def test_weekday_and_weekend_cooking_times_are_respected():
    client, repo, household_id = make()
    settings = repo.get_settings(household_id)
    settings.slots = {
        k: v.model_copy(update={"cook": k.endswith("dinner")}) for k, v in settings.slots.items()
    }
    settings.cook_minutes_weekday, settings.cook_minutes_weekend = 30, 90
    repo.save_settings(household_id, settings)
    add(repo, household_id, *[recipe(f"q{n}", minutes=25) for n in range(6)])
    add(repo, household_id, *[recipe(f"s{n}", minutes=75) for n in range(4)])
    add(repo, household_id, recipe("too-long", minutes=180))
    for seed in range(10):
        plan = services.generate_plan(repo, None, household_id, WEEK, random.Random(seed))
        for slot, meal in plan.meals.items():
            limit = 90 if slot.startswith(("sat", "sun")) else 30
            assert (meal.recipe.prep_minutes or 0) <= limit, (slot, meal.recipe.id)
        assert len(plan.meals) == 7
