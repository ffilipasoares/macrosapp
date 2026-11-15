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

    def find_recipe_links(self, query: str, count: int, avoid_titles: list[str]) -> list[str]:
        slug = "-".join(query.lower().split())
        return [f"https://recipes.example/{slug}-{index + 1}" for index in range(count * 2)]
