"""The one place the rest of the app talks to a language model."""

from typing import Protocol

from app.models import RecipeDraft


class AIError(Exception):
    """The model failed or returned something unusable. Safe to show to the user."""


class RecipeAI(Protocol):
    def recipe_from_image(self, data: bytes, mime_type: str) -> RecipeDraft:
        """Read a recipe from a screenshot or photo."""
        ...

    def recipe_from_text(self, text: str) -> RecipeDraft:
        """Structure a recipe pasted as free text, in any language."""
        ...

    def search_recipes(self, query: str, count: int, avoid_titles: list[str]) -> list[RecipeDraft]:
        """Find up to ``count`` real recipes on the web for a query."""
        ...
