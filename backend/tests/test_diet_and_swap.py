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
        plain.startswith("Everyday healthy home-cooked dinner recipes")
        and "chicken, fish, seafood, beef" in plain
    )
    both = search_phrase(["mediterranean", "high-protein"], {"fish": 2})
    # The meaning of each diet, never the bare label that would end up in titles.
    assert "plenty of vegetables, legumes, fish, olive oil" in both
    assert "high in protein" in both and "at least 2 with fish" in both
    assert "never choose a recipe because its title contains a diet or cuisine word" in both
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
    # Steak can still be chosen by hand: it is offered, flagged and listed last.
    beef = [o for o in options if o["recipe"]["protein"] == "beef"]
    assert beef and all(not o["fits_diets"] for o in beef)
    assert options.index(beef[0]) > max(i for i, o in enumerate(options) if o["fits_diets"])
    # The quick swap, which picks for you, never picks it.
    for _ in range(5):
        swapped = client.post(f"/api/plans/{WEEK}/meals/mon_dinner/swap", headers=AUTH)
        if swapped.status_code == 200:
            assert swapped.json()["meals"]["mon_dinner"]["recipe"]["protein"] != "beef"


def test_web_ideas_follow_the_diet_and_vary_the_protein():
    names = ["Chicken one", "Chicken two", "Chicken three", "Fish one", "Beef one", "Pork one"]
    names.append("Fish two")
    pages = {f"https://web.example/{name}": page(name) for name in names}
    ai = Web(pages)
    client = make(ai, pages)
    set_settings(client, diets=["mediterranean"])
    plan = client.post(f"/api/plans/{WEEK}/generate", headers=AUTH).json()
    assert "Mediterranean way of eating" in ai.queries[0]
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
    # Nothing in the library: the balanced week is what the written recipes must cover.
    assert ai.asked == (
        {"vegetables": 4, "fish": 2, "legumes": 1},
        5,
        "Mediterranean way of eating: plenty of vegetables, legumes, fish, olive oil and whole "
        "grains; little red meat and processed food; high in protein: a generous portion of "
        "meat, fish, eggs, dairy or legumes",
    )
    assert len(plan["meals"]) == 5 and all(meal["is_new"] for meal in plan["meals"].values())
    assert all(
        meal["recipe"]["diet_fit"] == {"mediterranean": True, "high-protein": True}
        for meal in plan["meals"].values()
    )


# Drag and drop ------------------------------------------------------------------------------


def test_dragging_a_meal_onto_another_day_swaps_them_and_each_day_keeps_its_portions():
    client = make()
    for title in ("Cod bake", "Bean stew", "Greek salad", "Lentil soup", "Fish pie"):
        add(client, title, "vegetarian")
    plan = client.post(f"/api/plans/{WEEK}/generate", headers=AUTH).json()
    client.put(
        f"/api/plans/{WEEK}/meals/thu_dinner",
        json={"recipe_id": plan["meals"]["thu_dinner"]["recipe"]["id"], "portions": 4},
        headers=AUTH,
    )
    client.post(f"/api/plans/{WEEK}/approve", headers=AUTH)
    thursday = plan["meals"]["thu_dinner"]["recipe"]["title"]
    friday = plan["meals"]["fri_dinner"]["recipe"]["title"]

    moved = client.post(
        f"/api/plans/{WEEK}/meals/thu_dinner/move", json={"to_slot": "fri_dinner"}, headers=AUTH
    ).json()
    assert moved["meals"]["fri_dinner"]["recipe"]["title"] == thursday
    assert moved["meals"]["thu_dinner"]["recipe"]["title"] == friday
    assert (
        moved["meals"]["thu_dinner"]["portions"] == 4
        and moved["meals"]["fri_dinner"]["portions"] == 2
    )
    assert moved["status"] == "draft"
    assert list(moved["meals"]) == [
        "mon_dinner",
        "tue_dinner",
        "wed_dinner",
        "thu_dinner",
        "fri_dinner",
    ]


def test_dragging_onto_an_empty_meal_moves_it_there():
    client = make()
    add(client, "Only recipe", "vegetarian")
    client.post(f"/api/plans/{WEEK}/generate", headers=AUTH)
    plan = client.get(f"/api/plans/{WEEK}", headers=AUTH).json()
    source = next(iter(plan["meals"]))
    target = next(slot for slot in DINNERS if slot not in plan["meals"])
    moved = client.post(
        f"/api/plans/{WEEK}/meals/{source}/move", json={"to_slot": target}, headers=AUTH
    ).json()
    assert (
        source not in moved["meals"] and moved["meals"][target]["recipe"]["title"] == "Only recipe"
    )
    assert moved["meals"][target]["portions"] == 2  # the empty day's own portions

    assert (
        client.post(
            f"/api/plans/{WEEK}/meals/{source}/move", json={"to_slot": target}, headers=AUTH
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/plans/{WEEK}/meals/{target}/move", json={"to_slot": "brunch"}, headers=AUTH
        ).status_code
        == 404
    )


def test_any_recipe_can_be_chosen_by_hand_even_one_already_in_the_week():
    client = make()
    set_settings(
        client, diets=["vegetarian"], rules=[{"kind": "min", "count": 1, "tag": "vegetarian"}]
    )
    stew = add(client, "Bean stew", "vegetarian")
    steak = add(client, "Steak", "beef")
    plan = client.post(f"/api/plans/{WEEK}/generate", headers=AUTH).json()
    assert plan["meals"]["mon_dinner"]["recipe"]["id"] == stew
    # The same stew again on Tuesday, and steak on Wednesday, despite the diet and the rule.
    client.put(f"/api/plans/{WEEK}/meals/tue_dinner", json={"recipe_id": stew}, headers=AUTH)
    chosen = client.put(
        f"/api/plans/{WEEK}/meals/mon_dinner", json={"recipe_id": steak}, headers=AUTH
    ).json()
    assert chosen["meals"]["mon_dinner"]["recipe"]["title"] == "Steak"
    assert chosen["meals"]["tue_dinner"]["recipe"]["title"] == "Bean stew"


def test_a_cuisine_guides_where_to_look_but_never_rules_a_recipe_out():
    from app.core.diet import cuisine_words, diet_words, fits

    words = ["portuguese", "low carb"]
    assert cuisine_words(words) == ["portuguese"] and diet_words(words) == ["low carb"]
    phrase = search_phrase(words, {})
    assert "Portuguese home cooking" in phrase and "Pingo Doce" in phrase
    assert "searched in the cuisine's own language (pt)" in phrase
    assert "no pasta, rice, bread or potatoes as the base" in phrase
    # An Italian dish is still fine for a household that likes Portuguese food.
    assert fits(["portuguese"], recipe("chicken"))


def test_carb_and_protein_limits_are_checked_on_the_macros():
    from app.core.diet import fits
    from app.models import Ingredient, IngredientNutrition, Recipe

    def dish(carbs_per_100g, protein_per_100g):
        nutrition = IngredientNutrition(
            grams_per_unit=None,
            kcal_per_100g=200,
            protein_per_100g=protein_per_100g,
            carbs_per_100g=carbs_per_100g,
            fat_per_100g=5,
        )
        return Recipe(
            title="Dish",
            servings=2,
            ingredients=[Ingredient(name="food", quantity=400, unit="g", nutrition=nutrition)],
        )

    pasta = dish(carbs_per_100g=30, protein_per_100g=10)  # 60 g carbs, 20 g protein a portion
    steak = dish(carbs_per_100g=2, protein_per_100g=20)  # 4 g carbs, 40 g protein a portion
    assert not fits(["low carb"], pasta) and fits(["low-carb"], steak)
    assert not fits(["high-protein"], pasta) and fits(["high-protein"], steak)


def test_own_diet_words_get_a_meaning_once_and_searches_use_it():
    ai = Web({})
    client = make(ai)
    saved = set_settings(client, diets=["low fodmap", "vietnamese", "mediterranean"])
    meanings = saved["diet_meanings"]
    # Known words need no AI; the others are interpreted once.
    assert set(meanings) == {"low fodmap", "vietnamese"}
    assert meanings["vietnamese"]["kind"] == "cuisine"
    assert ai.calls.count(("interpret", ("low fodmap", "vietnamese"))) == 1
    set_settings(client, diets=["low fodmap", "vietnamese", "mediterranean"])
    assert sum(1 for name, _ in ai.calls if name == "interpret") == 1
    client.post(f"/api/plans/{WEEK}/generate", headers=AUTH)
    query = ai.queries[0]
    assert "dishes that suit a low fodmap diet" in query and "vietnamese home cooking" in query
    # Dropping a word drops its meaning.
    assert set(set_settings(client, diets=["vietnamese"])["diet_meanings"]) == {"vietnamese"}


def test_old_diet_verdicts_are_judged_again_once_but_allergy_checks_stay():
    from app import services
    from app.models import Ingredient, Recipe
    from app.repo.memory import MemoryRepo

    repo = MemoryRepo()
    household = repo.household_for_user("ana", "a@example.com")
    old = Recipe(
        title="Fried fish",
        ingredients=[Ingredient(name="fish", quantity=1)],
        diet_fit={"mediterranean": True, "free of milk": True},
    )
    repo.save_recipe(household.id, old)
    ai = Web({})
    services.check_diets(repo, ai, household.id, [old], ["mediterranean", "free of milk"])
    again = repo.get_recipe(household.id, old.id)
    assert again.diet_fit_version == services.DIET_FIT_VERSION
    assert again.diet_fit["free of milk"] is True  # kept, not asked again
    assert "mediterranean" in again.diet_fit  # judged again, on its meaning
    asked = [call for call in ai.calls if call[0] == "diets"]
    assert len(asked) == 1
    services.check_diets(repo, ai, household.id, [again], ["mediterranean", "free of milk"])
    assert len([call for call in ai.calls if call[0] == "diets"]) == 1  # only once
