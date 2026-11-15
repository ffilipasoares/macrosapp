"""Recipe types: main dishes are planned; desserts and the rest only live in the library."""

from fastapi.testclient import TestClient

from app.ai import gemini
from app.ai.fake import FakeRecipeAI
from app.config import Config
from app.links import LinkContent, LinkError
from app.main import create_app
from app.models import Recipe
from app.notify import LogNotifier
from app.repo.memory import MemoryRepo

AUTH = {"Authorization": "Bearer ana"}
WEEK = "2026-11-16"


def make(ai=None, pages=None) -> TestClient:
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
    return TestClient(app)


def add(client: TestClient, title: str, category: str = "main") -> dict:
    body = {
        "title": title,
        "category": category,
        "protein": "vegetarian",
        "ingredients": [{"name": "egg", "quantity": 1}],
    }
    return client.post("/api/recipes", json=body, headers=AUTH).json()


def test_recipes_are_main_dishes_unless_said_otherwise():
    client = make()
    assert add(client, "Lentil soup")["category"] == "main"
    assert add(client, "Pastel de nata", "dessert")["category"] == "dessert"
    bad = client.post("/api/recipes", json={"title": "X", "category": "pudding"}, headers=AUTH)
    assert bad.status_code == 422
    # Recipes saved before types existed load as main dishes.
    assert Recipe(title="Old favourite").category == "main"


def test_desserts_are_never_planned_or_offered_as_a_swap():
    client = make()
    for n in range(4):
        add(client, f"Cake {n}", "dessert")
        add(client, f"Porridge {n}", "breakfast")
    for n in range(3):
        add(client, f"Bean stew {n}")
    plan = client.post(f"/api/plans/{WEEK}/generate", headers=AUTH).json()
    planned = {meal["recipe"]["title"] for meal in plan["meals"].values()}
    assert planned and all(title.startswith("Bean stew") for title in planned)
    slot = next(iter(plan["meals"]))
    options = client.get(f"/api/plans/{WEEK}/meals/{slot}/alternatives", headers=AUTH).json()
    # Desserts can still be chosen by hand; they are listed after the main dishes.
    categories = [option["recipe"]["category"] for option in options]
    assert "dessert" in categories and "breakfast" in categories
    assert categories.index("dessert") > max(i for i, c in enumerate(categories) if c == "main")
    for _ in range(5):
        swapped = client.post(f"/api/plans/{WEEK}/meals/{slot}/swap", headers=AUTH)
        if swapped.status_code == 200:
            assert swapped.json()["meals"][slot]["recipe"]["category"] == "main"


def test_desserts_found_on_the_web_are_not_planned():
    class CakeAware(FakeRecipeAI):
        def recipe_from_text(self, text, source_url=None):
            draft = super().recipe_from_text(text, source_url)
            return draft.model_copy(
                update={"category": "dessert" if "cake" in text.lower() else "main"}
            )

        def find_recipe_links(self, query, count, avoid_titles):
            return list(PAGES)

    PAGES = {
        f"https://web.example/{name}": LinkContent(
            f"https://web.example/{name}", f"{name}\n- 1 thing", "recipe-data", None
        )
        for name in ("Chocolate cake", "Fish stew", "Carrot cake", "Chicken salad")
    }
    client = make(CakeAware(), PAGES)
    plan = client.post(f"/api/plans/{WEEK}/generate", headers=AUTH).json()
    planned = sorted(meal["recipe"]["title"] for meal in plan["meals"].values())
    assert planned == ["Chicken salad", "Fish stew"]


def test_the_ai_says_what_kind_of_dish_it_read():
    recipe = gemini._AiRecipe(
        found=True, title="Pastel de nata", servings=6, ingredients=[], steps=["Bake."],
        protein="egg",
        category="dessert", tags=[], prep_minutes=None, original_language="pt", source_url=None,
    )  # fmt: skip
    assert gemini._to_draft(recipe).category == "dessert"
