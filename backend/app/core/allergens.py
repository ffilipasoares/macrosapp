"""Allergies, foods never eaten and kitchen equipment. Pure logic; no AI here.

Allergies are a safety feature, so they are checked twice: here, by matching ingredient
names against word lists, and once per recipe by the AI (stored like a diet verdict,
under "free of <allergen>"). Either one is enough to keep a recipe out of the plan.
Word lists miss hidden ingredients, so the app always tells people to check labels.
"""

import re
from collections.abc import Iterable
from typing import Any, Literal

# The 14 allergens EU food labels must declare, with the words that give them away.
ALLERGENS: dict[str, list[str]] = {
    "gluten": [
        "wheat", "flour", "bread", "breadcrumb", "panko", "pasta", "spaghetti", "noodle",
        "couscous", "bulgur", "barley", "rye", "spelt", "semolina", "tortilla", "pita",
        "naan", "croissant", "pastry", "puff pastry", "filo", "biscuit", "cracker", "seitan",
        "soy sauce", "beer", "farro",
    ],
    "milk": [
        "milk", "butter", "cream", "cheese", "yogurt", "yoghurt", "parmesan", "mozzarella",
        "feta", "ricotta", "mascarpone", "cheddar", "ghee", "whey", "creme fraiche",
        "crème fraîche", "buttermilk", "halloumi", "requeijão", "natas", "queijo", "leite",
    ],
    "eggs": ["egg", "mayonnaise", "mayo", "meringue", "aioli", "ovo", "ovos"],
    "fish": [
        "fish", "salmon", "cod", "tuna", "hake", "sardine", "anchovy", "mackerel", "trout",
        "sea bass", "bream", "tilapia", "haddock", "bacalhau", "fish sauce", "pescada",
    ],
    "crustaceans": ["prawn", "shrimp", "crab", "lobster", "langoustine", "crayfish", "camarão"],
    "molluscs": [
        "mussel", "clam", "oyster", "squid", "octopus", "scallop", "cuttlefish", "lula", "polvo",
        "amêijoa",
    ],
    "peanuts": ["peanut", "peanut butter", "groundnut", "amendoim"],
    "tree nuts": [
        "almond", "walnut", "cashew", "hazelnut", "pistachio", "pecan", "macadamia",
        "brazil nut", "pine nut", "praline", "marzipan", "nut", "noz", "amêndoa",
    ],
    "soy": ["soy", "soya", "tofu", "tempeh", "edamame", "miso", "soy sauce"],
    "sesame": ["sesame", "tahini", "hummus", "sésamo"],
    "celery": ["celery", "celeriac", "aipo"],
    "mustard": ["mustard", "dijon", "mostarda"],
    "lupin": ["lupin", "lupini", "tremoço"],
    "sulphites": ["wine", "vinegar", "dried apricot", "vinho", "vinagre"],
}  # fmt: skip

Equipment = Literal[
    "oven", "air fryer", "microwave", "slow cooker", "pressure cooker", "blender", "grill"
]  # fmt: skip
EQUIPMENT: tuple[str, ...] = (
    "oven", "air fryer", "microwave", "slow cooker", "pressure cooker", "blender", "grill"
)  # fmt: skip


def _has_word(text: str, word: str) -> bool:
    # Whole words, allowing a plural: "eggs" matches "egg", "eggplant" does not.
    return re.search(rf"\b{re.escape(word.lower())}(e?s)?\b", text.lower()) is not None


def verdict_key(allergen: str) -> str:
    """How an allergy is stored among a recipe's AI verdicts, next to the diets."""
    return f"free of {allergen}"


def words_for(allergen: str) -> list[str]:
    """The words for one of the 14 allergens, or the allergy itself for anything else."""
    return ALLERGENS.get(allergen, [allergen])


def found_in(recipe: Any, allergies: Iterable[str], avoid: Iterable[str]) -> list[str]:
    """Allergies and avoided foods this recipe contains, by name, as far as words can tell."""
    names = [ingredient.name for ingredient in recipe.ingredients] + [recipe.title]
    hits = []
    for allergen in allergies:
        by_words = any(_has_word(n, w) for n in names for w in words_for(allergen))
        by_ai = recipe.diet_fit.get(verdict_key(allergen)) is False
        if by_words or by_ai:
            hits.append(allergen)
    hits += [food for food in avoid if any(_has_word(n, food) for n in names)]
    return hits


def missing_equipment(recipe: Any, equipment: list[str] | None) -> list[str]:
    """Equipment the recipe needs that the household does not have. None means not asked."""
    if equipment is None:
        return []
    return [item for item in recipe.equipment if item not in equipment]
