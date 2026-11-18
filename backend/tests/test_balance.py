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


def _client():
    return TestClient(
        create_app(
            config=Config(push_enabled=False),
            repo=MemoryRepo(),
            ai=None,
            notifier=LogNotifier(),
            verify_token=lambda t: {"uid": t, "email": "a@example.com", "email_verified": True},
        )
    )


def _dinners_only(client, auth, rules):
    settings = client.get("/api/settings", headers=auth).json()
    settings["rules"] = rules
    settings["slots"] = {
        key: {"cook": key.endswith("dinner") and key[:3] in ("mon", "tue", "wed", "thu", "fri"),
              "portions": 2}
        for key in settings["slots"]
    }  # fmt: skip
    client.put("/api/settings", json=settings, headers=auth)


def _add(client, auth, title, protein, *ingredients):
    body = {
        "title": title,
        "protein": protein,
        "ingredients": [{"name": n, "quantity": 1} for n in ingredients],
    }
    client.post("/api/recipes", json=body, headers=auth)


def _library(client, auth):
    for n in range(6):
        _add(client, auth, f"Steak {n}", "beef", "beef", "chips")
    # Two different fish: the same fish twice in a week is never planned.
    _add(client, auth, "Salmon 0", "fish", "salmon", "broccoli")
    _add(client, auth, "Cod 1", "fish", "cod", "broccoli")
    _add(client, auth, "Lentil soup", "vegetarian", "lentils", "carrot")
    _add(client, auth, "Chicken salad", "chicken", "chicken", "lettuce")


def test_the_planner_aims_for_a_balanced_week_without_any_own_rules():
    client, auth = _client(), {"Authorization": "Bearer ana"}
    _dinners_only(client, auth, [])
    _library(client, auth)
    for _ in range(5):
        plan = client.post("/api/plans/2026-11-16/generate", headers=auth).json()
        proteins = [m["recipe"]["protein"] for m in plan["meals"].values()]
        assert proteins.count("fish") == 2
        assert proteins.count("beef") <= 2
        assert "Lentil soup" in [m["recipe"]["title"] for m in plan["meals"].values()]
        assert plan["balance"]["balanced"], plan["balance"]["checks"]
        # Only the household's own rules appear among the rule chips.
        assert plan["rule_status"] == []


def test_own_rules_are_extras_on_top_of_the_balanced_week():
    client, auth = _client(), {"Authorization": "Bearer ana"}
    _dinners_only(client, auth, [{"kind": "min", "count": 1, "tag": "chicken"}])
    _library(client, auth)
    plan = client.post("/api/plans/2026-11-16/generate", headers=auth).json()
    titles = [m["recipe"]["title"] for m in plan["meals"].values()]
    assert "Chicken salad" in titles and "Lentil soup" in titles
    assert sum(t.startswith(("Salmon", "Cod")) for t in titles) == 2
