"""Diet in Settings, varied web suggestions, and the one-tap swap."""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.ai.fake import FakeRecipeAI
from app.config import Config
from app.core.diet import allowed_proteins, fits, search_phrase
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


def test_diets_are_saved_tidied_and_limited():
    client = make()
    assert client.get("/api/settings", headers=AUTH).json()["diets"] == []
    saved = set_settings(client, diets=["  Mediterranean ", "high-protein", "mediterranean"])
    assert saved["diets"] == ["mediterranean", "high-protein"]
    too_long = client.get("/api/settings", headers=AUTH).json() | {"diets": ["x" * 61]}
    assert client.put("/api/settings", json=too_long, headers=AUTH).status_code == 422


def test_settings_saved_with_a_single_diet_still_load():
    from app.models import Settings

    assert Settings(diet="Mediterranean").diets == ["mediterranean"]
    assert Settings(diet="").diets == []


def recipe(protein: str, **verdicts: bool) -> SimpleNamespace:
    return SimpleNamespace(protein=protein, diet_fit=verdicts)


def test_several_diets_combine():
    assert allowed_proteins(["mediterranean"]) is None
    assert allowed_proteins(["vegetarian", "pescatarian"]) == {"vegetarian", "vegan", "egg"}
    assert fits(["mediterranean", "high-protein"], recipe("beef"))  # not judged yet: allowed
    assert not fits(["mediterranean", "high-protein"], recipe("beef", mediterranean=False))
    assert fits(["mediterranean", "pescatarian"], recipe("fish", mediterranean=True))
    assert not fits(["mediterranean", "pescatarian"], recipe("beef", mediterranean=True))
    assert not fits(["vegan"], recipe("egg"))


def test_search_asks_for_healthy_varied_dinners_in_every_chosen_diet():
    plain = search_phrase([], {})
    assert (
        plain.startswith("healthy home-cooked dinner recipes")
        and "chicken, fish, seafood, beef" in plain
    )
    both = search_phrase(["mediterranean", "high-protein"], {"fish": 2})
    assert "that are mediterranean and high-protein" in both and "at least 2 with fish" in both
    assert "beef" not in search_phrase(["vegetarian"], {})


def test_a_vegetarian_diet_keeps_meat_out_of_the_plan_and_the_swaps():
    client = make()
    set_settings(client, diets=["vegetarian"])
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
    set_settings(client, diets=["mediterranean"])
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


# Diets checked against your own recipes, and applied to this week --------------------------


def test_library_recipes_are_checked_once_and_unfitting_ones_left_out():
    ai = FakeRecipeAI()
    client = make(ai)
    for title in (
        "Fried chicken",
        "Greek salad",
        "Grilled fish",
        "Bean stew",
        "Lentil soup",
        "Fried rice",
    ):
        add(client, title, "chicken" if "chicken" in title.lower() else "vegetarian")
    set_settings(client, diets=["mediterranean", "high-protein"])

    plan = client.post(f"/api/plans/{WEEK}/generate", headers=AUTH).json()
    titles = {meal["recipe"]["title"] for meal in plan["meals"].values()}
    assert "Fried chicken" not in titles and "Fried rice" not in titles
    assert plan["diets"] == ["mediterranean", "high-protein"]
    checks = [names for kind, names in ai.calls if kind == "diets"]
    assert len(checks) == 1 and len(checks[0]) == 6

    # Verdicts are stored: generating again asks nothing new.
    client.post(f"/api/plans/{WEEK}/generate", headers=AUTH)
    assert len([1 for kind, _ in ai.calls if kind == "diets"]) == 1
    stored = {r["title"]: r["diet_fit"] for r in client.get("/api/recipes", headers=AUTH).json()}
    assert stored["Fried chicken"] == {"mediterranean": False, "high-protein": False}


def test_editing_a_recipe_clears_its_diet_verdicts():
    client = make()
    recipe_id = add(client, "Fried chicken", "chicken")
    set_settings(client, diets=["mediterranean"])
    client.post(f"/api/plans/{WEEK}/generate", headers=AUTH)
    saved = client.get(f"/api/recipes/{recipe_id}", headers=AUTH).json()
    assert saved["diet_fit"] == {"mediterranean": False}
    renamed = client.put(
        f"/api/recipes/{recipe_id}", json={**saved, "title": "Grilled chicken"}, headers=AUTH
    ).json()
    assert renamed["diet_fit"] == {}
    servings = client.put(
        f"/api/recipes/{recipe_id}", json={**renamed, "servings": 4}, headers=AUTH
    ).json()
    assert servings["diet_fit"] == {}  # still empty: it was not checked again yet


def test_update_this_week_keeps_meals_that_fit_and_replaces_the_rest():
    client = make()
    for title in (
        "Fried chicken",
        "Chicken burger",
        "Greek salad",
        "Grilled fish",
        "Bean stew",
        "Lentil soup",
        "Baked cod",
    ):
        add(client, title, "fish" if title in ("Grilled fish", "Baked cod") else "vegetarian")
    plan = client.post(f"/api/plans/{WEEK}/generate", headers=AUTH).json()
    assert plan["diets"] == []
    # Make sure the unhealthy ones are in the plan, with custom portions on a meal that fits.
    slots = list(plan["meals"])
    ids = {r["title"]: r["id"] for r in client.get("/api/recipes", headers=AUTH).json()}
    for slot, title in zip(
        slots,
        ("Fried chicken", "Chicken burger", "Greek salad", "Grilled fish", "Bean stew"),
        strict=True,
    ):
        client.put(f"/api/plans/{WEEK}/meals/{slot}", json={"recipe_id": ids[title]}, headers=AUTH)
    client.put(
        f"/api/plans/{WEEK}/meals/{slots[2]}",
        json={"recipe_id": ids["Greek salad"], "portions": 7},
        headers=AUTH,
    )
    client.post(f"/api/plans/{WEEK}/approve", headers=AUTH)

    set_settings(client, diets=["mediterranean"])
    updated = client.post(f"/api/plans/{WEEK}/apply-diets", headers=AUTH).json()
    titles = [updated["meals"][slot]["recipe"]["title"] for slot in slots]
    assert titles[2:] == ["Greek salad", "Grilled fish", "Bean stew"]  # kept where they were
    assert updated["meals"][slots[2]]["portions"] == 7
    assert "Fried chicken" not in titles and "Chicken burger" not in titles
    assert len(set(titles)) == 5
    assert updated["diets"] == ["mediterranean"] and updated["status"] == "draft"
    assert any("Approve the plan again" in note for note in updated["notes"])
    assert client.post("/api/plans/2026-12-07/apply-diets", headers=AUTH).status_code == 404


def test_fallback_recipes_fill_what_the_web_could_not_and_follow_the_diets():
    from app.models import Ingredient, RecipeDraft

    class WithFallback(FakeRecipeAI):
        def __init__(self) -> None:
            super().__init__()
            self.asked = None

        def generate_fallback_recipes(self, needs, total_slots, forbidden, avoid_titles, diet=""):
            self.asked = (needs, total_slots, diet)
            return [
                RecipeDraft(
                    title=f"Written dish {n}",
                    protein="vegetarian",
                    ingredients=[Ingredient(name="bean", quantity=1)],
                )
                for n in range(total_slots)
            ]

    ai = WithFallback()
    client = make(ai)  # the web returns nothing usable in these tests
    set_settings(client, diets=["mediterranean", "high-protein"])
    plan = client.post(f"/api/plans/{WEEK}/generate", headers=AUTH).json()
    assert ai.asked == ({}, 5, "mediterranean and high-protein")
    assert len(plan["meals"]) == 5 and all(meal["is_new"] for meal in plan["meals"].values())
    assert all(
        meal["recipe"]["diet_fit"] == {"mediterranean": True, "high-protein": True}
        for meal in plan["meals"].values()
    )
