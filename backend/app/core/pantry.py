"""The pantry: food at home now. Pure functions; no database or AI here.

Amounts are kept in base units (g, ml, tsp, or whole things) so they can be added
and taken away. An item with no amount ("some rice") is never used up by counting.
"""

import math
import re
from collections.abc import Iterable
from datetime import date, timedelta

from app.core.ingredients import guess_aisle, normalize_name, normalize_unit
from app.models import Ingredient, PantryItem

# Rough days fresh food keeps once bought. Cupboard and freezer food: no limit.
SHELF_DAYS = {"meat_fish": 2, "bakery": 3, "produce": 5, "dairy_eggs": 7}

_TO_BASE = {"kg": ("g", 1000.0), "l": ("ml", 1000.0), "tbsp": ("tsp", 3.0)}
_WORDS = {
    "a": 1, "an": 1, "one": 1, "half": 0.5, "half a": 0.5, "half an": 0.5, "two": 2,
    "three": 3, "four": 4, "five": 5, "six": 6, "a dozen": 12, "dozen": 12,
    "um": 1, "uma": 1, "meio": 0.5, "meia": 0.5, "dois": 2, "duas": 2, "três": 3,
}  # fmt: skip
_UNITS = r"g|gr|grams?|kg|kilos?|ml|l|litres?|liters?|tbsp|tsp|cups?|cans?|tins?|packs?|bunch"
_AMOUNT = re.compile(
    rf"^(?P<n>\d+(?:[.,]\d+)?|{'|'.join(sorted(map(re.escape, _WORDS), key=len, reverse=True))})"
    rf"\s*(?P<u>{_UNITS})?\b\s*(?:of\s+|de\s+)?(?P<name>.+)$",
    re.IGNORECASE,
)


def base(quantity: float | None, unit: str) -> tuple[float | None, str]:
    unit = normalize_unit(unit)
    to, factor = _TO_BASE.get(unit, (unit, 1.0))
    return (None if quantity is None else quantity * factor), to


def use_by(aisle: str, bought: date) -> date | None:
    days = SHELF_DAYS.get(aisle)
    return bought + timedelta(days=days) if days else None


def same_food(a: str, b: str) -> bool:
    """ "spinach" and "baby spinach" are the same food; "chicken" and "chicken stock" are not."""
    a, b = normalize_name(a), normalize_name(b)
    if a == b:
        return True
    short, long = sorted((a, b), key=len)
    return bool(short) and long.endswith(" " + short)


def parse_text(text: str) -> list[tuple[str, float | None, str]]:
    """ "2 eggs, half a courgette and 200 g spinach" → (name, quantity, unit) per food."""
    # A comma between digits is a decimal comma ("1,5 kg"), not a separator.
    parts = re.split(r"(?<!\d),|,(?!\d)|;|\n|\band\b|\be\b", text, flags=re.IGNORECASE)
    found = []
    for part in parts:
        part = re.sub(
            r"^\s*(some|a bit of|a few|algum|alguma|alguns|algumas)\s+",
            "",
            part.strip(" .").lower(),
        )
        if not part:
            continue
        match = _AMOUNT.match(part)
        if match and match.group("name").strip():
            raw = match.group("n").replace(",", ".")
            quantity = float(raw) if raw[0].isdigit() else float(_WORDS[raw])
            unit = normalize_unit(match.group("u") or "")
            name = match.group("name").strip()
        else:
            quantity, unit, name = None, "", part
        found.append((name[:120], quantity, unit))
    return found


def add(items: list[PantryItem], new: Iterable[PantryItem]) -> list[PantryItem]:
    """Put food in. The same food in a compatible unit adds up; otherwise a new item."""
    items = [item.model_copy() for item in items]
    for incoming in new:
        quantity, unit = base(incoming.quantity, incoming.unit)
        match = next(
            (
                item
                for item in items
                if same_food(item.name, incoming.name) and base(item.quantity, item.unit)[1] == unit
            ),
            None,
        )
        if match is None:
            items.append(incoming.model_copy(update={"quantity": quantity, "unit": unit}))
            continue
        have, _ = base(match.quantity, match.unit)
        match.quantity = None if have is None or quantity is None else have + quantity
        match.unit = unit
        # The soonest use-by wins: that is when something needs eating.
        dates = [d for d in (match.use_by, incoming.use_by) if d]
        match.use_by = min(dates) if dates else None
        if incoming.note and not match.note:
            match.note = incoming.note
    return items


def take(items: list[PantryItem], used: Iterable[Ingredient]) -> list[PantryItem]:
    """Take what a cooked meal used out. Food not in the pantry, or with no amount, is skipped."""
    items = [item.model_copy() for item in items]
    for ingredient in used:
        quantity, unit = base(ingredient.quantity, ingredient.unit)
        if quantity is None:
            continue
        for item in items:
            have, item_unit = base(item.quantity, item.unit)
            if have is None or item_unit != unit or not same_food(item.name, ingredient.name):
                continue
            taken = min(have, quantity)
            item.quantity, item.unit = have - taken, item_unit
            quantity -= taken
            if quantity <= 1e-9:
                break
    # Gone when (almost) nothing is left: under 5 g/ml, or under a quarter of a thing.
    return [
        item
        for item in items
        if item.quantity is None or item.quantity > (5 if item.unit in ("g", "ml") else 0.25)
    ]


def available(items: list[PantryItem], name: str, unit: str) -> tuple[bool, float | None]:
    """Whether the pantry has this food, and how much in this (base) unit; None = some."""
    _, wanted = base(None, unit)
    total, found, unknown = 0.0, False, False
    for item in items:
        if not same_food(item.name, name):
            continue
        have, item_unit = base(item.quantity, item.unit)
        if have is None:
            found = unknown = True
        elif item_unit == wanted:
            found, total = True, total + have
    return found, (None if unknown and total == 0 else total)


def used_by(items: list[PantryItem], ingredients: Iterable[Ingredient]) -> list[str]:
    """The pantry foods a recipe would use."""
    names = []
    for ingredient in ingredients:
        for item in items:
            if same_food(item.name, ingredient.name) and item.name not in names:
                names.append(item.name)
    return names


def preference(items: list[PantryItem], ingredients: Iterable[Ingredient], today: date) -> float:
    """How much a recipe helps use the pantry up: food close to its use-by counts double."""
    score = 0.0
    for item in items:
        if any(same_food(item.name, i.name) for i in ingredients):
            soon = item.use_by is not None and (item.use_by - today).days <= 2
            score += 2.0 if soon else 1.0
    return score


def from_text(text: str, bought: date) -> list[PantryItem]:
    items = []
    for name, quantity, unit in parse_text(text):
        aisle = guess_aisle(name)
        items.append(
            PantryItem(name=name, quantity=quantity, unit=unit, use_by=use_by(aisle, bought))
        )
    return items


def packs_needed(need: float, size: float) -> int:
    return max(1, math.ceil(round(need / size, 6)))
