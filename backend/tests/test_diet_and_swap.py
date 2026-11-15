"""Diet in Settings, varied web suggestions, and the one-tap swap."""

from fastapi.testclient import TestClient

from app.ai.fake import FakeRecipeAI
from app.config import Config
from app.core.diet import fits_diet, search_phrase
from app.links import LinkContent, LinkError
from app.main import create_app
from app.notify import LogNotifier
from app.repo.memory import MemoryRepo

AUTH = {"Authorization": "Bearer ana"}
WEEK = "2026-11-16"
DINNERS = ("mon_dinner", "tue_dinner", "wed_dinner", "thu_dinner", "fri_dinner")


class Web(FakeRecipeAI):
    """A web search that returns these pages, and remembers what it was asked."""

    def __init__(self, pages: dict[str, LinkContent]) -> None:
        super().__init__()
        self.pages, self.queries = pages, []

    def find_recipe_links(self, query: str, count: int, avoid_titles: list[str]) -> list[str]:
        self.queries.append(query)
        return list(self.pages)


def page(name: str) -> LinkContent:
    return LinkContent(f"https://web.example/{name}", f"{name}\n- 1 thing", "recipe-data", None)


def make(ai: FakeRecipeAI | None = None, pages: dict | None = None):
    def read(url: str) -> LinkContent:
        if pages and url in pages:
            return pages[url]
        raise LinkError("The link could not be opened.")

    app = create_app(
        config=Config(push_enabled=False),
        repo=MemoryRepo(),
        ai=ai or FakeRecipeAI(),
        notifier=LogNotifier(),
        verify_token=lambda token: {"uid": token, "email": "a@example.com", "email_verified": True},
        read_link=read,
    )
    client = TestClient(app)
    settings = client.get("/api/settings", headers=AUTH).json()
    settings["slots"] = {key: {"cook": key in DINNERS, "portions": 2} for key in settings["slots"]}
    client.put("/api/settings", json=settings, headers=AUTH)
    return client


def set_settings(client: TestClient, **changes) -> dict:
    settings = client.get("/api/settings", headers=AUTH).json()
    settings.update(changes)
    return client.put("/api/settings", json=settings, headers=AUTH).json()


def add(client: TestClient, title: str, protein: str) -> str:
    body = {"title": title, "protein": protein, "ingredients": [{"name": "onion", "quantity": 1}]}
    return client.post("/api/recipes", json=body, headers=AUTH).json()["id"]


# Diet ------------------------------------------------------------------------------


def test_diet_is_saved_tidied_and_limited():
    client = make()
    assert client.get("/api/settings", headers=AUTH).json()["diet"] == ""
    assert set_settings(client, diet="  Mediterranean  ")["diet"] == "mediterranean"
    too_long = client.get("/api/settings", headers=AUTH).json() | {"diet": "x" * 61}
    assert client.put("/api/settings", json=too_long, headers=AUTH).status_code == 422


def test_which_diets_rule_out_foods():
    assert fits_diet("mediterranean", "beef") and fits_diet("", "pork")
    assert fits_diet("vegetarian", "egg") and not fits_diet("vegetarian", "chicken")
    assert fits_diet("pescatarian", "fish") and not fits_diet("Pescatarian", "beef")
    assert not fits_diet("vegan", "egg")


def test_search_asks_for_healthy_varied_dinners_in_the_chosen_diet():
    plain = search_phrase("", {})
    assert (
        plain.startswith("healthy home-cooked dinner recipes")
        and "chicken, fish, seafood, beef" in plain
    )
    diet = search_phrase("mediterranean", {"fish": 2})
    assert (
        "healthy mediterranean home-cooked dinner recipes" in diet
        and "at least 2 with fish" in diet
    )
    assert "beef" not in search_phrase("vegetarian", {})


def test_a_vegetarian_diet_keeps_meat_out_of_the_plan_and_the_swaps():
    client = make()
    set_settings(client, diet="vegetarian")
    for n in range(4):
        add(client, f"Lentil dish {n}", "vegetarian")
        add(client, f"Steak {n}", "beef")
    add(client, "Omelette", "egg")
    plan = client.post(f"/api/plans/{WEEK}/generate", headers=AUTH).json()
    assert {meal["recipe"]["protein"] for meal in plan["meals"].values()} <= {"vegetarian", "egg"}
    options = client.get(f"/api/plans/{WEEK}/meals/mon_dinner/alternatives", headers=AUTH).json()
    assert all(option["recipe"]["protein"] != "beef" for option in options)


def test_web_ideas_follow_the_diet_and_vary_the_protein():
    names = ["Chicken one", "Chicken two", "Chicken three", "Fish one", "Beef one", "Pork one"]
    names.append("Fish two")
    pages = {f"https://web.example/{name}": page(name) for name in names}
    ai = Web(pages)
    client = make(ai, pages)
    set_settings(client, diet="mediterranean")
    plan = client.post(f"/api/plans/{WEEK}/generate", headers=AUTH).json()
    assert "mediterranean" in ai.queries[0]
    proteins = sorted(meal["recipe"]["protein"] for meal in plan["meals"].values())
    # Five meals from mostly-chicken results: no protein more than twice.
    assert len(proteins) == 5 and max(proteins.count(p) for p in set(proteins)) <= 2


# One-tap swap -------------------------------------------------------------------------


def test_swap_changes_the_meal_keeps_portions_and_rules():
    client = make()
    set_settings(client, rules=[{"kind": "min", "count": 1, "tag": "fish"}])
    add(client, "Cod bake", "fish")
    add(client, "Salmon bowl", "fish")
    for n in range(6):
        add(client, f"Veg dish {n}", "vegetarian")
    plan = client.post(f"/api/plans/{WEEK}/generate", headers=AUTH).json()
    fish_slot = next(
        slot for slot, meal in plan["meals"].items() if meal["recipe"]["protein"] == "fish"
    )
    client.put(
        f"/api/plans/{WEEK}/meals/{fish_slot}",
        json={"recipe_id": plan["meals"][fish_slot]["recipe"]["id"], "portions": 5},
        headers=AUTH,
    )
    before = {slot: meal["recipe"]["id"] for slot, meal in plan["meals"].items()}

    for _ in range(5):
        swapped = client.post(f"/api/plans/{WEEK}/meals/{fish_slot}/swap", headers=AUTH).json()
        meal = swapped["meals"][fish_slot]
        assert meal["recipe"]["id"] != before[fish_slot]
        assert meal["recipe"]["id"] not in {
            rid for slot, rid in before.items() if slot != fish_slot
        }
        assert meal["portions"] == 5 and swapped["status"] == "draft"
        assert all(status["ok"] for status in swapped["rule_status"])
        before[fish_slot] = meal["recipe"]["id"]


def test_swap_with_nothing_else_in_the_library_explains_why():
    client = make()
    add(client, "Only recipe", "chicken")
    client.post(f"/api/plans/{WEEK}/generate", headers=AUTH)
    reply = client.post(f"/api/plans/{WEEK}/meals/mon_dinner/swap", headers=AUTH)
    assert reply.status_code == 404 and "Add more recipes" in reply.json()["detail"]
    assert client.post(f"/api/plans/{WEEK}/meals/breakfast/swap", headers=AUTH).status_code == 404
