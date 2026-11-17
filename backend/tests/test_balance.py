from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.ai.fake import FakeRecipeAI
from app.config import Config
from app.core.balance import food_group, week_balance
from app.main import create_app
from app.models import Ingredient
from app.notify import LogNotifier
from app.repo.memory import MemoryRepo
from app.standards import Standards, load

S = load()


def recipe(protein: str, *names: str):
    return SimpleNamespace(protein=protein, ingredients=[Ingredient(name=n) for n in names])


def test_standards_are_a_placeholder_until_reviewed():
    assert S.version.startswith("placeholder")
    assert S.reviewed_by is None


def test_food_groups_use_whole_words_and_the_longest_match():
    assert food_group("chickpeas", S) == "legumes"
    assert food_group("green beans", S) == "vegetables"
    assert food_group("peanut butter", S) is None
    assert food_group("chicken breast", S) is None


def test_a_balanced_week_passes_every_check():
    meals = [
        ("mon_dinner", recipe("fish", "salmon", "broccoli")),
        ("tue_dinner", recipe("chicken", "chicken", "spinach")),
        ("wed_dinner", recipe("vegetarian", "lentils", "carrot")),
        ("thu_dinner", recipe("fish", "cod", "potato", "kale")),
        ("fri_dinner", recipe("beef", "beef", "onion")),
    ]
    result = week_balance(meals, S)
    assert result["balanced"], result["checks"]
    assert not result["reviewed"]


def test_a_heavy_week_explains_what_is_missing():
    meals = [(f"{d}_dinner", recipe("beef", "beef", "rice")) for d in ("mon", "tue", "wed")]
    checks = {c["key"]: c for c in week_balance(meals, S)["checks"]}
    assert not checks["vegetable_days"]["ok"]
    assert not checks["fish"]["ok"]
    assert not checks["legumes"]["ok"]
    assert not checks["red_meat"]["ok"] and checks["red_meat"]["value"] == 3
    assert not checks["protein_variety"]["ok"]


def test_new_standards_replace_the_numbers_without_code_changes():
    data = S.model_dump()
    data["checks"]["fish"]["min_meals"] = 0
    data["checks"]["new_check_from_the_future"] = {"label": "Unknown"}
    custom = Standards.model_validate(data)
    checks = week_balance([("mon_dinner", recipe("beef", "beef"))], custom)["checks"]
    assert {c["key"]: c["ok"] for c in checks}["fish"]
    assert "new_check_from_the_future" not in {c["key"] for c in checks}


def test_an_empty_week_is_not_called_balanced():
    assert not week_balance([], S)["balanced"]


def test_the_plan_returns_its_balance():
    client = TestClient(
        create_app(
            config=Config(push_enabled=False),
            repo=MemoryRepo(),
            ai=FakeRecipeAI(),
            notifier=LogNotifier(),
            verify_token=lambda t: {"uid": t, "email": "a@example.com", "email_verified": True},
        )
    )
    auth = {"Authorization": "Bearer ana"}
    for title, protein, ingredients in [
        ("Salmon bowl", "fish", ["salmon", "broccoli", "rice"]),
        ("Lentil stew", "vegetarian", ["lentils", "carrot", "onion"]),
    ]:
        body = {
            "title": title,
            "protein": protein,
            "ingredients": [{"name": n, "quantity": 1} for n in ingredients],
        }
        assert client.post("/api/recipes", json=body, headers=auth).status_code in (200, 201)
    plan = client.post("/api/plans/2026-11-16/generate", headers=auth).json()
    balance = plan["balance"]
    assert "plants" not in balance
    assert balance["standards_version"].startswith("placeholder")
    assert {c["key"] for c in balance["checks"]} >= {"fish", "legumes", "red_meat"}
