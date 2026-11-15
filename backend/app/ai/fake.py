"""Canned AI responses for local development and tests. Never used in production."""

import re

from app.ai.base import AIError
from app.models import Ingredient, IngredientNutrition, RecipeDraft

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
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def recipe_from_images(self, images: list[tuple[bytes, str]]) -> RecipeDraft:
        self.calls.append(("images", len(images)))
        if not images or not any(data for data, _ in images):
            raise AIError("No recipe was found in what you sent.")
        steps = [*_SAMPLE.steps, *[f"Step from image {i + 1}." for i in range(1, len(images))]]
        return _SAMPLE.model_copy(deep=True, update={"steps": steps})

    def recipe_from_video(self, data: bytes, mime_type: str, caption: str = "") -> RecipeDraft:
        self.calls.append(("video", caption))
        if not data:
            raise AIError("No recipe was found in what you sent.")
        return _SAMPLE.model_copy(deep=True, update={"title": "Recipe from a video"})

    def recipe_from_audio(self, data: bytes, mime_type: str) -> RecipeDraft:
        self.calls.append(("audio", mime_type))
        if not data:
            raise AIError("No recipe was found in what you sent.")
        return _SAMPLE.model_copy(deep=True, update={"title": "Recipe from a voice note"})

    def recipe_from_text(self, text: str, source_url: str | None = None) -> RecipeDraft:
        self.calls.append(("text", text))
        first_line = text.strip().splitlines()[0][:80] if text.strip() else ""
        if not first_line or "no recipe here" in text.lower():
            raise AIError("No recipe was found in what you sent.")
        protein = next(
            (p for p in ("fish", "chicken", "beef", "pork", "vegetarian") if p in text.lower()),
            _SAMPLE.protein,
        )
        return _SAMPLE.model_copy(
            deep=True, update={"title": first_line, "source_url": source_url, "protein": protein}
        )

    def estimate_nutrition(self, ingredients: list[Ingredient]) -> list[IngredientNutrition | None]:
        self.calls.append(("nutrition", [item.name for item in ingredients]))
        weights = {"": 100.0, "tbsp": 13.5, "tsp": 4.5, "clove": 5.0, "can": 400.0, "cup": 200.0,
                   "ml": 1.0, "l": 1000.0, "slice": 30.0}  # fmt: skip
        return [
            None
            if "unknown" in item.name
            else IngredientNutrition(
                grams_per_unit=weights.get(item.unit, 50.0),
                kcal_per_100g=200.0,
                protein_per_100g=20.0,
                carbs_per_100g=10.0,
                fat_per_100g=8.0,
            )
            for item in ingredients
        ]

    def check_diets(
        self, recipes: list[tuple[str, list[str]]], diets: list[str]
    ) -> list[dict[str, bool]]:
        self.calls.append(("diets", [title for title, _ in recipes]))
        # Pretend fried food and burgers fit no diet; everything else fits.
        return [
            {diet: not any(word in title.lower() for word in ("fried", "burger")) for diet in diets}
            for title, _ in recipes
        ]

    def find_recipe_links(self, query: str, count: int, avoid_titles: list[str]) -> list[str]:
        self.calls.append(("search", query))
        # Pages named after the start of the query, taking turns at any protein a rule asks for.
        start = "-".join(query.lower().split()[:4])
        tags = re.findall(r"at least \d+ with ([\w-]+)", query.lower()) or [""]
        return [
            f"https://recipes.example/{start}-{tags[index % len(tags)]}-{index + 1}".replace(
                "--", "-"
            )
            for index in range(count * 2)
        ]
