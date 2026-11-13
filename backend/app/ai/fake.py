"""Canned AI responses for local development and tests. Never used in production."""

from app.ai.base import AIError
from app.models import Ingredient, RecipeDraft

_SAMPLE = RecipeDraft(
    title="Lemon herb chicken traybake",
    servings=4,
    ingredients=[
        Ingredient(name="chicken thigh", quantity=8, unit="", aisle="meat_fish"),
        Ingredient(name="potato", quantity=600, unit="g", aisle="produce"),
        Ingredient(name="lemon", quantity=1, unit="", aisle="produce"),
        Ingredient(name="garlic", quantity=4, unit="clove", aisle="produce"),
        Ingredient(name="olive oil", quantity=2, unit="tbsp", aisle="pantry"),
    ],
    steps=[
        "Heat the oven to 200C.",
        "Toss everything in a roasting tin with the oil.",
        "Roast for 45 minutes.",
    ],
    protein="chicken",
    tags=["traybake", "healthy"],
    prep_minutes=55,
)


class FakeRecipeAI:
    def recipe_from_image(self, data: bytes, mime_type: str) -> RecipeDraft:
        if not data:
            raise AIError("No recipe was found in what you sent.")
        return _SAMPLE.model_copy(deep=True)

    def recipe_from_text(self, text: str) -> RecipeDraft:
        first_line = text.strip().splitlines()[0][:80] if text.strip() else ""
        if not first_line:
            raise AIError("No recipe was found in what you sent.")
        return _SAMPLE.model_copy(deep=True, update={"title": first_line})

    def search_recipes(self, query: str, count: int, avoid_titles: list[str]) -> list[RecipeDraft]:
        protein = next(
            (p for p in ("chicken", "fish", "beef", "pork", "vegetarian") if p in query.lower()),
            "vegetarian",
        )
        return [
            _SAMPLE.model_copy(
                deep=True,
                update={
                    "title": f"Sample {query.strip()} idea {index + 1}",
                    "protein": protein,
                    "source_url": "https://example.com/recipe",
                },
            )
            for index in range(count)
        ]
