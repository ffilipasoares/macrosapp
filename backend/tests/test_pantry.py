import random
from datetime import UTC, date, datetime

from fastapi.testclient import TestClient

from app import services
from app.ai.fake import FakeRecipeAI
from app.config import Config
from app.core import pantry
from app.core.grocery import build_grocery_lines, load_packs
from app.main import create_app
from app.models import Ingredient, PantryItem, PlanMeal, Recipe, WeekPlan
from app.notify import LogNotifier
from app.repo.memory import MemoryRepo

AUTH = {"Authorization": "Bearer ana"}
WEEK = "2026-11-16"  # Monday
NEXT = "2026-11-23"


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
    return client, repo, household_id


def cod(servings=2):
    return Recipe(
        title="Cod with tomato",
        servings=servings,
        protein="fish",
        ingredients=[
            Ingredient(name="cod fillet", quantity=2),
            Ingredient(name="spinach", quantity=200, unit="g"),
            Ingredient(name="olive oil", quantity=1, unit="tbsp"),
        ],
    )


# Pure logic ------------------------------------------------------------------------------


def test_typed_food_is_understood_in_english_and_portuguese():
    assert pantry.parse_text("2 eggs, half a courgette and 1,5 kg de batatas; some rice") == [
        ("eggs", 2.0, ""),
        ("courgette", 0.5, ""),
        ("batatas", 1.5, "kg"),
        ("rice", None, ""),
    ]


def test_same_food_by_its_last_words_only():
    assert pantry.same_food("baby spinach", "spinach")
    assert pantry.same_food("Eggs", "egg")
    assert not pantry.same_food("chicken stock", "chicken")


def test_adding_and_taking_keeps_amounts_in_step():
    items = pantry.add([], [PantryItem(name="spinach", quantity=0.3, unit="kg")])
    items = pantry.add(items, [PantryItem(name="spinach", quantity=100, unit="g")])
    assert [(i.name, i.quantity, i.unit) for i in items] == [("spinach", 400.0, "g")]
    items = pantry.take(items, [Ingredient(name="spinach", quantity=250, unit="g")])
    assert items[0].quantity == 150
    # Almost nothing left is gone; food with no amount is never used up by counting.
    items = pantry.add(items, [PantryItem(name="rice")])
    items = pantry.take(
        items,
        [Ingredient(name="spinach", quantity=148, unit="g"), Ingredient(name="rice", quantity=1)],
    )
    assert [i.name for i in items] == ["rice"]


def test_fresh_food_gets_a_rough_use_by():
    bought = date(2026, 11, 16)
    assert pantry.use_by("meat_fish", bought) == date(2026, 11, 18)
    assert pantry.use_by("produce", bought) == date(2026, 11, 21)
    assert pantry.use_by("pantry", bought) is None


def test_the_list_buys_whole_packs_and_skips_what_is_at_home():
    recipe = cod()
    lines = {
        line.name: line
        for line in build_grocery_lines([(recipe, 2)], ["olive oil"], [], load_packs())
    }
    assert lines["spinach"].pack == "1 bag (300 g)"
    assert (lines["spinach"].quantity, lines["spinach"].needed) == (300, 200)
    rice = Recipe(title="Rice", ingredients=[Ingredient(name="rice", quantity=150, unit="g")])
    line = build_grocery_lines([(rice, 2)], [], [], load_packs())[0]
    assert (line.quantity, line.unit, line.needed, line.pack) == (1, "kg", 0.15, "1 pack (1 kg)")
    at_home = [PantryItem(name="spinach", quantity=150, unit="g")]
    lines = {line.name: line for line in build_grocery_lines([(recipe, 2)], [], at_home, {})}
    assert lines["spinach"].quantity == 50 and lines["spinach"].note == "the rest is at home"
    enough = [PantryItem(name="spinach", quantity=500, unit="g")]
    assert "spinach" not in {line.name for line in build_grocery_lines([(recipe, 2)], [], enough)}


# Through the API ------------------------------------------------------------------------


def test_typed_photos_and_voice_go_into_the_pantry():
    client, _, _ = make()
    items = client.post("/api/pantry/text", json={"text": "2 eggs, 200 g spinach"}, headers=AUTH)
    assert {(i["name"], i["quantity"]) for i in items.json()} == {("egg", 2), ("spinach", 200)}
    # Photos and voice come back for checking first; nothing is saved yet.
    seen = client.post(
        "/api/pantry/read/images",
        files=[("files", ("fridge.jpg", b"\xff\xd8\xff" + b"0" * 100, "image/jpeg"))],
        headers=AUTH,
    )
    assert seen.status_code == 200, seen.text
    assert len(client.get("/api/pantry", headers=AUTH).json()) == 2
    saved = client.post("/api/pantry/items", json=seen.json(), headers=AUTH).json()
    eggs = next(i for i in saved if i["name"] == "egg")
    assert eggs["quantity"] == 8  # 2 typed + 6 seen
    # Edit and remove.
    edited = client.put(
        f"/api/pantry/items/{eggs['id']}",
        json={"name": "egg", "quantity": 4, "unit": ""},
        headers=AUTH,
    ).json()
    assert next(i for i in edited if i["name"] == "egg")["quantity"] == 4
    left = client.delete(f"/api/pantry/items/{eggs['id']}", headers=AUTH).json()
    assert "egg" not in {i["name"] for i in left}


def _approved_week(repo, household_id, *, put_away=True):
    meal = PlanMeal(recipe=cod(), portions=2)
    plan = WeekPlan(
        week_id=WEEK,
        status="approved",
        approved_at=datetime(2026, 11, 16, 18, tzinfo=UTC),
        meals={"fri_dinner": meal},
        put_away=put_away,
    )
    repo.save_plan(household_id, plan)
    if put_away:
        repo.save_pantry(
            household_id,
            [
                PantryItem(name="cod fillet", quantity=2, aisle="meat_fish",
                           use_by=date(2026, 11, 22), source="shopping"),
                PantryItem(name="spinach", quantity=300, unit="g", aisle="produce",
                           use_by=date(2026, 11, 25), source="shopping"),
            ],
        )  # fmt: skip


def test_putting_the_shopping_away_fills_the_pantry():
    client, repo, household_id = make()
    client.post("/api/groceries", json={"text": "milk"}, headers=AUTH)
    item = repo.list_groceries(household_id)[0]
    repo.set_grocery_checked(household_id, item.id, True)
    assert client.post("/api/pantry/put-away", headers=AUTH).json() == {"moved": 1}
    assert repo.list_groceries(household_id) == []
    assert [i.name for i in repo.get_pantry(household_id)] == ["milk"]


def test_a_meal_is_taken_out_of_the_pantry_once_its_day_has_passed():
    _, repo, household_id = make()
    _approved_week(repo, household_id)
    # Friday itself: still there.
    assert len(services.settle_pantry(repo, household_id, date(2026, 11, 20))) == 2
    # Saturday: the cod is gone, 100 g spinach is left over; settling again changes nothing.
    left = services.settle_pantry(repo, household_id, date(2026, 11, 21))
    assert [(i.name, i.quantity) for i in left] == [("spinach", 100)]
    assert services.settle_pantry(repo, household_id, date(2026, 11, 22)) == left


def test_not_cooking_moves_the_recipe_to_next_week_and_keeps_the_food():
    _, repo, household_id = make()
    _approved_week(repo, household_id)
    services.settle_pantry(repo, household_id, date(2026, 11, 21))  # Friday assumed cooked
    # Said the day after: the food comes back.
    result = services.skip_meal(repo, household_id, WEEK, "fri_dinner", today=date(2026, 11, 21))
    assert result.moved_to == f"{NEXT} mon_dinner"  # the first meal cooked
    assert "fri_dinner" not in repo.get_plan(household_id, WEEK).meals
    food = {i.name: i for i in repo.get_pantry(household_id)}
    assert food["cod fillet"].quantity == 2 and food["spinach"].quantity == 300
    assert food["cod fillet"].note == "bought for Friday's cod with tomato"
    # Bought on Monday: neither the cod nor the spinach keeps until next Monday.
    assert sorted(result.warnings) == [
        "The cod fillet won't keep until Monday. Freeze it, or cook this sooner.",
        "The spinach won't keep until Monday. Freeze it, or cook this sooner.",
    ]
    # Next week is waiting for its real plan, which keeps the moved meal.
    pending = repo.get_plan(household_id, NEXT)
    assert pending.pending and pending.meals["mon_dinner"].carried_from == f"{WEEK} fri_dinner"
    plan = services.generate_plan(repo, None, household_id, NEXT, random.Random(1))
    assert plan.meals["mon_dinner"].recipe.title == "Cod with tomato" and not plan.pending


def test_when_next_week_is_full_you_choose_the_meal_to_replace():
    _, repo, household_id = make()
    _approved_week(repo, household_id, put_away=False)
    settings = repo.get_settings(household_id)
    full = {
        slot: PlanMeal(recipe=Recipe(title=f"Dish {slot}"), portions=2)
        for slot in settings.cook_slots()
    }
    repo.save_plan(household_id, WeekPlan(week_id=NEXT, status="approved", meals=full))
    asked = services.skip_meal(repo, household_id, WEEK, "fri_dinner", today=date(2026, 11, 20))
    assert asked.moved_to is None and sorted(asked.choose_from) == sorted(full)
    assert "fri_dinner" in repo.get_plan(household_id, WEEK).meals  # nothing changed yet
    done = services.skip_meal(
        repo, household_id, WEEK, "fri_dinner", "wed_dinner", today=date(2026, 11, 20)
    )
    assert done.moved_to == f"{NEXT} wed_dinner"
    nxt = repo.get_plan(household_id, NEXT)
    assert nxt.meals["wed_dinner"].recipe.title == "Cod with tomato"
    assert nxt.status == "draft"  # its grocery list needs updating
    # Bought but never put away: the food is added now.
    assert {i.name for i in repo.get_pantry(household_id)} == {"cod fillet", "spinach", "olive oil"}


def test_the_skip_route():
    client, repo, household_id = make()
    _approved_week(repo, household_id)
    response = client.post(f"/api/plans/{WEEK}/meals/fri_dinner/skip", json={}, headers=AUTH)
    assert response.status_code == 200 and response.json()["moved_to"].startswith(NEXT)
    missing = client.post(f"/api/plans/{WEEK}/meals/fri_dinner/skip", json={}, headers=AUTH)
    assert missing.status_code == 404


def test_planning_prefers_recipes_that_use_food_at_home():
    _, repo, household_id = make()
    settings = repo.get_settings(household_id)
    settings.slots = {
        k: v.model_copy(update={"cook": k == "mon_dinner"}) for k, v in settings.slots.items()
    }
    repo.save_settings(household_id, settings)
    for n in range(6):
        repo.save_recipe(
            household_id, Recipe(title=f"Pasta {n}", ingredients=[Ingredient(name="pasta")])
        )
    repo.save_recipe(household_id, cod())
    repo.save_pantry(household_id, [PantryItem(name="spinach", quantity=300, unit="g")])
    for seed in range(5):
        plan = services.generate_plan(repo, None, household_id, NEXT, random.Random(seed))
        assert plan.meals["mon_dinner"].recipe.title == "Cod with tomato"
