"""Which protein a meal really has, and how it is cooked. Pure functions.

A week never has the same fish twice, and never the same meat cooked the same way
twice: grilled chicken and chicken curry are fine together, two chicken curries are
not. Fish is told apart by kind (salmon, cod…), meat by cooking method.
"""

import re
from typing import Any

# Kinds of fish and seafood, with the words that name them (English names, as stored,
# and Portuguese, as titles may be).
FISH = {
    "salmon": ["salmon", "salmão"], "cod": ["cod", "bacalhau"], "tuna": ["tuna", "atum"],
    "hake": ["hake", "pescada"], "sea bass": ["sea bass", "seabass", "robalo"],
    "sea bream": ["sea bream", "bream", "dourada"], "sardine": ["sardine", "sardinha"],
    "mackerel": ["mackerel", "cavala", "carapau"], "trout": ["trout", "truta"],
    "haddock": ["haddock"], "tilapia": ["tilapia"], "sole": ["sole", "linguado"],
    "monkfish": ["monkfish", "tamboril"], "swordfish": ["swordfish", "espadarte"],
    "plaice": ["plaice", "solha"], "pollock": ["pollock", "red fish", "redfish"],
    "anchovy": ["anchovy", "biqueirão"], "octopus": ["octopus", "polvo"],
    "squid": ["squid", "calamari", "lula"], "cuttlefish": ["cuttlefish", "choco"],
    "prawn": ["prawn", "shrimp", "camarão", "gamba"], "mussel": ["mussel", "mexilhão"],
    "clam": ["clam", "amêijoa", "ameijoa"], "scallop": ["scallop", "vieira"],
    "crab": ["crab", "sapateira"], "lobster": ["lobster", "lagosta"],
}  # fmt: skip

# How a dish is cooked, from words in its title or tags.
METHODS = {
    "grilled": ["grilled", "grill", "barbecue", "barbecued", "bbq", "grelhado", "grelhada",
                "na brasa", "espetada", "skewer", "kebab"],
    "roast": ["roast", "roasted", "baked", "traybake", "tray bake", "oven", "assado",
              "assada", "no forno"],
    "stew": ["stew", "stewed", "casserole", "braised", "estufado", "estufada", "guisado",
             "jardineira", "caldeirada", "cozido"],
    "curry": ["curry", "caril", "tikka", "masala", "korma"],
    "fried": ["fried", "breaded", "crispy", "frito", "frita", "panado", "panada", "nuggets"],
    "stir-fry": ["stir-fry", "stir fry", "stir-fried", "wok", "salteado", "salteada"],
    "soup": ["soup", "broth", "sopa", "canja", "caldo"],
    "salad": ["salad", "salada", "bowl"],
    "pasta": ["pasta", "spaghetti", "penne", "lasagne", "lasagna", "massa", "esparguete"],
    "rice": ["risotto", "paella", "pilaf", "arroz", "rice"],
    "burger": ["burger", "hambúrguer", "meatball", "almôndega", "kofta"],
    "pie": ["pie", "empadão", "gratin", "gratinado", "bake"],
    "wrap": ["wrap", "fajita", "taco", "burrito", "tortilla", "sandwich", "sandes"],
    "pan-fried": ["pan-fried", "seared", "steak", "bife", "escalope", "à brás", "a bras"],
}  # fmt: skip

MEATS = {"chicken", "turkey", "beef", "pork", "lamb"}


def _has(text: str, word: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(word)}(e?s)?(?!\w)", text) is not None


def fish_kinds(recipe: Any) -> set[str]:
    """The kinds of fish and seafood a recipe is built on: its ingredients and title."""
    text = " | ".join([recipe.title.lower(), *(i.name.lower() for i in recipe.ingredients)])
    return {kind for kind, words in FISH.items() if any(_has(text, w) for w in words)}


def cooking_method(recipe: Any) -> str | None:
    """How the dish is cooked, from its title (then tags); None when it does not say."""
    for text in (recipe.title.lower(), " ".join(recipe.tags).lower()):
        best = None
        for method, words in METHODS.items():
            for word in words:
                if _has(text, word) and (best is None or len(word) > best[1]):
                    best = (method, len(word))
        if best:
            return best[0]
    return None


def clash(a: Any, b: Any) -> str | None:
    """Why two meals should not be in the same week, or None when they can be.

    The same fish twice, or the same meat cooked the same way twice."""
    if a.id == b.id or a.title.strip().lower() == b.title.strip().lower():
        return "same dish"
    shared = fish_kinds(a) & fish_kinds(b)
    if shared:
        return f"same fish: {sorted(shared)[0]}"
    if a.protein in MEATS and a.protein == b.protein:
        method = cooking_method(a)
        if method is not None and method == cooking_method(b):
            return f"same {a.protein}, {method}"
    return None


def clashes_with(recipe: Any, others: list[Any]) -> bool:
    return any(clash(recipe, other) for other in others)
