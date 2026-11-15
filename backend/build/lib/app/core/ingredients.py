"""Ingredient normalisation: canonical names and units so that lines merge cleanly."""

import re

UNIT_ALIASES = {
    "gram": "g",
    "grams": "g",
    "gr": "g",
    "grs": "g",
    "kilogram": "kg",
    "kilograms": "kg",
    "kgs": "kg",
    "kilo": "kg",
    "kilos": "kg",
    "milliliter": "ml",
    "milliliters": "ml",
    "millilitre": "ml",
    "millilitres": "ml",
    "mls": "ml",
    "liter": "l",
    "liters": "l",
    "litre": "l",
    "litres": "l",
    "teaspoon": "tsp",
    "teaspoons": "tsp",
    "tsps": "tsp",
    "tablespoon": "tbsp",
    "tablespoons": "tbsp",
    "tbsps": "tbsp",
    "tbs": "tbsp",
    "cups": "cup",
    "piece": "",
    "pieces": "",
    "pc": "",
    "pcs": "",
    "unit": "",
    "units": "",
    "whole": "",
    "cloves": "clove",
    "cans": "can",
    "tin": "can",
    "tins": "can",
    "slices": "slice",
    "bunches": "bunch",
    "pinches": "pinch",
    "handfuls": "handful",
    "packs": "pack",
    "packet": "pack",
    "packets": "pack",
    "package": "pack",
    "packages": "pack",
    "jars": "jar",
    "bottles": "bottle",
    "sprigs": "sprig",
    "stalks": "stalk",
    "heads": "head",
}

_SINGULAR_EXCEPTIONS = {"leaves": "leaf", "cookies": "cookie", "loaves": "loaf", "halves": "half"}
_KEEP_ENDINGS = ("ss", "us", "is")

_AISLE_OVERRIDES = {
    "pantry": [
        "stock",
        "broth",
        "peanut butter",
        "coconut milk",
        "tomato paste",
        "tomato puree",
        "passata",
        "chopped tomato",
        "tinned",
        "canned",
        "dried",
    ],
}
_AISLE_KEYWORDS = {
    "frozen": ["frozen", "ice cream"],
    "household": [
        "toilet",
        "paper",
        "detergent",
        "soap",
        "shampoo",
        "sponge",
        "bin bag",
        "foil",
        "toothpaste",
        "cling film",
        "napkin",
        "bleach",
        "dishwasher",
    ],
    "meat_fish": [
        "chicken",
        "beef",
        "pork",
        "lamb",
        "turkey",
        "salmon",
        "tuna",
        "cod",
        "fish",
        "prawn",
        "shrimp",
        "bacon",
        "sausage",
        "mince",
        "ham",
        "steak",
        "hake",
        "chorizo",
        "sea bass",
        "duck",
    ],
    "dairy_eggs": [
        "milk",
        "cheese",
        "yogurt",
        "yoghurt",
        "butter",
        "cream",
        "egg",
        "feta",
        "mozzarella",
        "parmesan",
        "halloumi",
        "ricotta",
    ],
    "bakery": [
        "bread",
        "bun",
        "wrap",
        "tortilla",
        "bagel",
        "pita",
        "pitta",
        "baguette",
        "roll",
        "croissant",
    ],
    "produce": [
        "onion",
        "garlic",
        "tomato",
        "potato",
        "carrot",
        "pepper",
        "lettuce",
        "spinach",
        "apple",
        "banana",
        "lemon",
        "lime",
        "avocado",
        "cucumber",
        "courgette",
        "zucchini",
        "broccoli",
        "mushroom",
        "coriander",
        "parsley",
        "basil",
        "ginger",
        "berry",
        "orange",
        "kale",
        "cabbage",
        "celery",
        "leek",
        "aubergine",
        "eggplant",
        "chilli",
        "mint",
        "pumpkin",
        "squash",
        "cauliflower",
        "pea",
        "corn",
        "rocket",
        "salad",
        "fruit",
        "herb",
        "shallot",
        "beetroot",
        "asparagus",
        "grape",
        "mango",
        "pear",
    ],
    "drinks": ["water", "juice", "wine", "beer", "soda", "cola", "kombucha"],
    "pantry": [
        "rice",
        "pasta",
        "flour",
        "sugar",
        "oil",
        "vinegar",
        "salt",
        "spice",
        "bean",
        "lentil",
        "chickpea",
        "sauce",
        "noodle",
        "oat",
        "cereal",
        "honey",
        "nut",
        "coffee",
        "tea",
        "cumin",
        "paprika",
        "oregano",
        "cinnamon",
        "mustard",
        "mayonnaise",
        "ketchup",
        "quinoa",
        "couscous",
        "seed",
        "chocolate",
        "almond",
        "tahini",
        "curry",
        "spaghetti",
        "olive",
        "yeast",
        "syrup",
        "jam",
        "cracker",
        "tofu",
    ],
}


def normalize_unit(unit: str | None) -> str:
    cleaned = (unit or "").strip().lower().rstrip(".")
    return UNIT_ALIASES.get(cleaned, cleaned)


def _singular(word: str) -> str:
    if word in _SINGULAR_EXCEPTIONS:
        return _SINGULAR_EXCEPTIONS[word]
    if len(word) <= 3 or word.endswith(_KEEP_ENDINGS):
        return word
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith("oes"):
        return word[:-2]
    if word.endswith("s"):
        return word[:-1]
    return word


def normalize_name(name: str) -> str:
    """Lower-case, strip notes in brackets and singularise the last word.

    "Red Onions (diced)" and "red onion" both become "red onion".
    """
    cleaned = re.sub(r"\([^)]*\)", " ", name or "").lower()
    cleaned = re.sub(r"[^\w\s'&%-]", " ", cleaned)
    words = cleaned.split()
    if not words:
        return ""
    words[-1] = _singular(words[-1])
    return " ".join(words)


def guess_aisle(name: str) -> str:
    """Best-effort supermarket aisle for an ingredient name."""
    normalized = normalize_name(name)
    words = set(normalized.split())

    def matches(keyword: str) -> bool:
        return keyword in normalized if " " in keyword else keyword in words

    for table in (_AISLE_OVERRIDES, _AISLE_KEYWORDS):
        for aisle, keywords in table.items():
            if any(matches(keyword) for keyword in keywords):
                return aisle
    return "other"
