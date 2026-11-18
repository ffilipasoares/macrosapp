"""Diets. Pure logic; no AI here.

Diets are free text ("mediterranean", "high-protein", "low FODMAP"...), and several
can be chosen together. Vegetarian, vegan and pescatarian rule out main proteins,
which is decided by code. Whether a recipe fits any other diet is judged once by
the AI and stored on the recipe as a verdict.
"""

from collections.abc import Iterable
from typing import Any

_EXCLUDING = {
    "vegetarian": {"vegetarian", "vegan", "egg"},
    "vegan": {"vegan"},
    "pescatarian": {"fish", "seafood", "vegetarian", "vegan", "egg"},
}


def tidy(diets: Iterable[str]) -> list[str]:
    """Lower-case, single-spaced, without duplicates, in the order given."""
    seen: list[str] = []
    for diet in diets:
        cleaned = " ".join(str(diet).split()).lower()
        if cleaned and cleaned not in seen:
            seen.append(cleaned)
    return seen


def is_excluding(diet: str) -> bool:
    return diet in _EXCLUDING


def allowed_proteins(diets: Iterable[str]) -> set[str] | None:
    """The main proteins every chosen diet allows, or None if none rules any out."""
    allowed: set[str] | None = None
    for diet in diets:
        proteins = _EXCLUDING.get(diet)
        if proteins is not None:
            allowed = set(proteins) if allowed is None else allowed & proteins
    return allowed


def needs_verdict(diets: Iterable[str], recipe: Any) -> list[str]:
    """The chosen diets the AI has not judged this recipe against yet."""
    return [d for d in diets if not is_excluding(d) and d not in recipe.diet_fit]


def fits(diets: list[str], recipe: Any) -> bool:
    """Whether a recipe fits every chosen diet. Without a verdict yet, it is given the benefit."""
    allowed = allowed_proteins(diets)
    if allowed is not None and recipe.protein not in allowed:
        return False
    return all(recipe.diet_fit.get(d, True) for d in diets if not is_excluding(d))


def search_phrase(diets: list[str], needs: dict[str, int], wishes: list[str] | None = None) -> str:
    """What to ask the web search for: healthy, varied dinners that fit every diet."""
    phrase = "healthy home-cooked dinner recipes"
    if diets:
        phrase += " that are " + " and ".join(diets)
    if allowed_proteins(diets) is None:
        phrase += (
            ", with a varied mix of main proteins, such as chicken, fish, seafood, beef, pork, "
            "eggs, and beans or lentils"
        )
    else:
        phrase += ", with a varied mix of main ingredients"
    if needs:
        phrase += ", including " + ", ".join(f"at least {n} with {tag}" for tag, n in needs.items())
    if wishes:
        phrase += "; " + "; ".join(wishes)
    return phrase
