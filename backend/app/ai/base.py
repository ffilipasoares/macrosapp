"""The one place the rest of the app talks to a language model."""

from typing import Protocol

from app.models import Ingredient, IngredientNutrition, RecipeDraft


class AIError(Exception):
    """The model failed or returned something unusable. Safe to show to the user."""


class RecipeAI(Protocol):
    def recipe_from_images(self, images: list[tuple[bytes, str]]) -> RecipeDraft:
        """Read one recipe spread over one or more screenshots or photos, in order."""
        ...

    def recipe_from_video(self, data: bytes, mime_type: str, caption: str = "") -> RecipeDraft:
        """Watch and listen to a short cooking video (and its caption, if known)."""
        ...

    def recipe_from_audio(self, data: bytes, mime_type: str) -> RecipeDraft:
        """Listen to someone describing a recipe out loud and write it down."""
        ...

    def recipe_from_text(self, text: str, source_url: str | None = None) -> RecipeDraft:
        """Structure a recipe given as free text, in any language."""
        ...

    def estimate_nutrition(self, ingredients: list[Ingredient]) -> list[IngredientNutrition | None]:
        """For each ingredient, in order: the weight of one unit and macros per 100 g."""
        ...

    def check_diets(
        self, recipes: list[tuple[str, list[str]]], diets: list[str]
    ) -> list[dict[str, bool]]:
        """For each (title, ingredient names), whether it fits each diet, in order."""
        ...

    def find_recipe_links(self, query: str, count: int, avoid_titles: list[str]) -> list[str]:
        """Addresses of recipe pages found by a web search. They are checked before use."""
        ...
