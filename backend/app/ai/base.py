"""The one place the rest of the app talks to a language model."""

from typing import Protocol

from app.models import DietMeaning, Ingredient, IngredientNutrition, PantryDraft, RecipeDraft


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

    def pantry_from_images(self, images: list[tuple[bytes, str]]) -> list[PantryDraft]:
        """The food visible in photos of a fridge, freezer or cupboard."""
        ...

    def pantry_from_audio(self, data: bytes, mime_type: str) -> list[PantryDraft]:
        """The food someone says they have at home."""
        ...

    def translate_recipes(
        self, recipes: list[tuple[str, list[str], list[str]]], target: str
    ) -> list[tuple[str, list[str], list[str]] | None]:
        """Each (title, steps, ingredient names) in ``target`` ("en" or "pt"), in order.
        None for a recipe that could not be translated."""
        ...

    def interpret_diets(self, words: list[str]) -> dict[str, DietMeaning]:
        """What each diet or cuisine word means: what fits, limits, a cuisine's language."""
        ...

    def translate_names(self, names: list[str], target: str) -> list[str]:
        """Food names in ``target``, in order: "cebola roxa" → "red onion" for "en"."""
        ...
