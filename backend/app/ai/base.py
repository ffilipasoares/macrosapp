"""The one place the rest of the app talks to a language model."""

from typing import Protocol

from app.models import RecipeDraft


class AIError(Exception):
    """The model failed or returned something unusable. Safe to show to the user."""


class RecipeAI(Protocol):
    def recipe_from_images(self, images: list[tuple[bytes, str]]) -> RecipeDraft:
        """Read one recipe spread over one or more screenshots or photos, in order."""
        ...

    def recipe_from_video(self, data: bytes, mime_type: str, caption: str = "") -> RecipeDraft:
        """Watch and listen to a short cooking video (and its caption, if known)."""
        ...

    def recipe_from_text(self, text: str, source_url: str | None = None) -> RecipeDraft:
        """Structure a recipe given as free text, in any language."""
        ...

    def search_recipes(self, query: str, count: int, avoid_titles: list[str]) -> list[RecipeDraft]:
        """Find up to ``count`` real recipes on the web for a query."""
        ...
