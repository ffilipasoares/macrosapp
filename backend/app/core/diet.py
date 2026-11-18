"""Diets and cuisines. Pure logic; no AI here.

Diets are free text ("mediterranean", "high-protein", "low FODMAP", "portuguese"...),
and several can be chosen together. Each word is first turned into a meaning: a way
of eating described by its ingredients (and limits per portion when it has them), or
a cuisine (where new recipes are looked for, and in which language). The search and
the AI get the meaning, never the bare label, so they pick ordinary dishes that fit
rather than dishes with the word in their title.

Vegetarian, vegan and pescatarian rule out main proteins, decided by code. Carb and
protein limits are checked against a recipe's macros when they are known. Whether a
recipe fits any other diet is judged once by the AI and stored on the recipe as a
verdict. Cuisines guide new ideas but never rule a recipe out.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class Meaning:
    kind: Literal["diet", "cuisine"]
    describe: str  # what fits, in words a search and the AI can use
    max_carbs_g: float | None = None  # per portion
    min_protein_g: float | None = None  # per portion
    language: str | None = None  # a cuisine's language, e.g. "pt"
    sites: tuple[str, ...] = ()  # well-known recipe websites for a cuisine


_DIETS = {
    "mediterranean": Meaning(
        "diet",
        "Mediterranean way of eating: plenty of vegetables, legumes, fish, olive oil and "
        "whole grains; little red meat and processed food",
    ),
    "high-protein": Meaning(
        "diet", "high in protein: a generous portion of meat, fish, eggs, dairy or legumes",
        min_protein_g=30,
    ),
    "low-carb": Meaning(
        "diet",
        "low in carbohydrates: no pasta, rice, bread or potatoes as the base; vegetables, "
        "protein and healthy fats instead",
        max_carbs_g=30,
    ),
    "pescatarian": Meaning("diet", "pescatarian: fish and seafood, no meat"),
    "vegetarian": Meaning("diet", "vegetarian: no meat or fish"),
    "vegan": Meaning("diet", "vegan: no animal products"),
}  # fmt: skip

_PT_SITES = ("Pingo Doce", "Continente Feed", "24Kitchen", "Teleculinária", "SAPO Lifestyle")
_CUISINES = {
    "portuguese": Meaning("cuisine", "Portuguese home cooking", language="pt", sites=_PT_SITES),
    "italian": Meaning("cuisine", "Italian home cooking", language="it"),
    "spanish": Meaning("cuisine", "Spanish home cooking", language="es"),
    "french": Meaning("cuisine", "French home cooking", language="fr"),
    "greek": Meaning("cuisine", "Greek home cooking"),
    "brazilian": Meaning("cuisine", "Brazilian home cooking", language="pt"),
    "indian": Meaning("cuisine", "Indian home cooking"),
    "mexican": Meaning("cuisine", "Mexican home cooking"),
    "japanese": Meaning("cuisine", "Japanese home cooking"),
    "chinese": Meaning("cuisine", "Chinese home cooking"),
    "thai": Meaning("cuisine", "Thai home cooking"),
    "asian": Meaning("cuisine", "East and South-East Asian home cooking"),
    "middle eastern": Meaning("cuisine", "Middle Eastern home cooking"),
}
_ALIASES = {
    "low carb": "low-carb", "lowcarb": "low-carb", "keto": "low-carb",
    "pobre em hidratos": "low-carb", "high protein": "high-protein",
    "rica em proteína": "high-protein", "mediterrânica": "mediterranean",
    "mediterranea": "mediterranean", "mediterrânea": "mediterranean",
    "portugal": "portuguese", "portuguesa": "portuguese", "português": "portuguese",
    "comida portuguesa": "portuguese", "cozinha portuguesa": "portuguese",
    "vegetariana": "vegetarian", "vegana": "vegan", "pescetariana": "pescatarian",
}  # fmt: skip


def meaning(word: str, learned: Mapping[str, Any] | None = None) -> Meaning:
    """What a chosen word means. Known words are built in; others were interpreted once by
    the AI (``learned``); anything else is taken as a diet described by the word itself."""
    key = _ALIASES.get(word, word)
    if key in _DIETS:
        return _DIETS[key]
    if key in _CUISINES:
        return _CUISINES[key]
    found = (learned or {}).get(word)
    if found is not None:
        get = found.get if isinstance(found, dict) else lambda name: getattr(found, name, None)
        return Meaning(
            kind=get("kind") or "diet",
            describe=get("describe") or word,
            max_carbs_g=get("max_carbs_g"),
            min_protein_g=get("min_protein_g"),
            language=get("language"),
        )
    return Meaning("diet", word)


def is_known(word: str) -> bool:
    key = _ALIASES.get(word, word)
    return key in _DIETS or key in _CUISINES or word.startswith("free of ")


def diet_words(words: Iterable[str], learned: Mapping[str, Any] | None = None) -> list[str]:
    """The chosen words that are diets (ways of eating), not cuisines."""
    return [w for w in words if meaning(w, learned).kind == "diet"]


def cuisine_words(words: Iterable[str], learned: Mapping[str, Any] | None = None) -> list[str]:
    return [w for w in words if meaning(w, learned).kind == "cuisine"]


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
    return _ALIASES.get(diet, diet) in _EXCLUDING


def allowed_proteins(diets: Iterable[str]) -> set[str] | None:
    """The main proteins every chosen diet allows, or None if none rules any out."""
    allowed: set[str] | None = None
    for diet in diets:
        proteins = _EXCLUDING.get(_ALIASES.get(diet, diet))
        if proteins is not None:
            allowed = set(proteins) if allowed is None else allowed & proteins
    return allowed


def needs_verdict(
    diets: Iterable[str], recipe: Any, learned: Mapping[str, Any] | None = None
) -> list[str]:
    """The chosen diets the AI has not judged this recipe against yet (cuisines are not
    judged: they only guide new ideas)."""
    return [
        d for d in diet_words(diets, learned) if not is_excluding(d) and d not in recipe.diet_fit
    ]


def _per_portion(recipe: Any) -> tuple[float, float] | None:
    macros = getattr(recipe, "macros", None)
    if macros is None or getattr(macros, "missing", None):
        return None
    servings = max(getattr(recipe, "servings", 1) or 1, 1)
    return macros.carbs_g / servings, macros.protein_g / servings


def fits(diets: list[str], recipe: Any, learned: Mapping[str, Any] | None = None) -> bool:
    """Whether a recipe fits every chosen diet. Cuisines never rule a recipe out. Carb and
    protein limits are checked on its macros when known; other diets by the AI's verdict,
    and without a verdict yet it is given the benefit."""
    chosen = diet_words(diets, learned)
    allowed = allowed_proteins(chosen)
    if allowed is not None and recipe.protein not in allowed:
        return False
    portion = _per_portion(recipe)
    for word in chosen:
        limits = meaning(word, learned)
        if portion is not None:
            carbs, protein = portion
            if limits.max_carbs_g is not None and carbs > limits.max_carbs_g:
                return False
            if limits.min_protein_g is not None and protein < limits.min_protein_g:
                return False
    return all(recipe.diet_fit.get(d, True) for d in chosen if not is_excluding(d))


def criteria(diets: Iterable[str], learned: Mapping[str, Any] | None = None) -> str:
    """What every recipe must be, in words: the meanings of the diets (and allergies)."""
    parts = []
    for word in diets:
        if word.startswith("free of "):
            parts.append(word)
        elif (m := meaning(word, learned)).kind == "diet":
            parts.append(m.describe)
    return "; ".join(parts)


def cuisine_hint(diets: Iterable[str], learned: Mapping[str, Any] | None = None) -> str:
    """Where to look and in which language, e.g. Portuguese sites, searched in Portuguese."""
    hints = []
    for word in cuisine_words(diets, learned):
        m = meaning(word, learned)
        hint = m.describe
        if m.language:
            hint += f", searched in the cuisine's own language ({m.language})"
        if m.sites:
            hint += f", on recipe websites from that country such as {', '.join(m.sites)}"
        hints.append(hint)
    return "; ".join(hints)


def search_phrase(
    diets: list[str],
    needs: dict[str, int],
    wishes: list[str] | None = None,
    learned: Mapping[str, Any] | None = None,
) -> str:
    """What to ask the web search for: ordinary, healthy, varied home-cooked dinners that
    meet the meaning of every choice, never dishes picked for a word in their title."""
    chosen = diet_words(diets, learned)
    phrase = "Everyday healthy home-cooked dinner recipes."
    if must := criteria(diets, learned):
        phrase += f" Criteria: {must}."
    if where := cuisine_hint(diets, learned):
        phrase += f" Cuisine: {where}."
    if allowed_proteins(chosen) is None:
        phrase += (
            " A varied mix of main proteins, such as chicken, fish, seafood, beef, pork, "
            "eggs, and beans or lentils."
        )
    else:
        phrase += " A varied mix of main ingredients."
    if needs:
        phrase += " Including " + ", ".join(f"at least {n} with {tag}" for tag, n in needs.items())
        phrase += "."
    if wishes:
        phrase += " " + "; ".join(wishes) + "."
    phrase += (
        " Choose ordinary, specific dishes that meet the criteria; never choose a recipe "
        "because its title contains a diet or cuisine word."
    )
    return phrase
