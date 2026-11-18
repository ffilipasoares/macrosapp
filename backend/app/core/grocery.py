"""Portion scaling and grocery-list merging. Pure functions."""

import json
import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from app.core import pantry as pantry_logic
from app.models import Ingredient, PantryItem, Recipe

_PACKS_FILE = Path(__file__).resolve().parent.parent / "data" / "packs.json"


@lru_cache
def load_packs() -> dict[str, dict]:
    return json.loads(_PACKS_FILE.read_text())["packs"]


def pack_for(name: str, unit: str, packs: dict[str, dict]) -> dict | None:
    """The typical pack for a food in this (base) unit, if there is one."""
    best = None
    name = pantry_logic.normalize_name(name)
    for food, pack in packs.items():
        # The pack's food must be the same or more general: "spinach" packs fit
        # "baby spinach", but "baby spinach" packs do not fit any spinach.
        if pack["unit"] == unit and (name == food or name.endswith(" " + food)):
            if best is None or len(food) > len(best[0]):
                best = (food, pack)
    return best[1] if best else None


def pack_label(count: int, pack: dict) -> str:
    label = pack["label"]
    name = label if " of " in label or count == 1 else label + "s"
    amount = count * pack["size"]
    unit = pack["unit"]
    if not unit:
        return f"{count} {name}"
    shown, shown_unit = _display(float(amount), unit)
    return f"{count} {name} ({shown:g} {shown_unit})"


# Units that can be added together are converted to one base unit first.
_TO_BASE = {"kg": ("g", 1000.0), "l": ("ml", 1000.0), "tbsp": ("tsp", 3.0)}
_MEASURED = {"g", "ml", "tsp", "cup"}


@dataclass
class GroceryLine:
    name: str
    quantity: float | None
    unit: str
    aisle: str
    recipes: list[str] = field(default_factory=list)
    needed: float | None = None  # what the recipes need, when whole packs are bought
    pack: str = ""
    note: str = ""


def scale_ingredients(recipe: Recipe, portions: int) -> list[Ingredient]:
    """Scale a recipe written for ``recipe.servings`` to ``portions``."""
    factor = portions / recipe.servings
    return [
        ingredient.model_copy(
            update={
                "quantity": None if ingredient.quantity is None else ingredient.quantity * factor
            }
        )
        for ingredient in recipe.ingredients
    ]


def _round_up(quantity: float, unit: str) -> float:
    """Round to an amount you can actually buy or measure, never below what is needed."""
    quantity = round(quantity, 6)
    if unit in ("g", "ml"):
        return float(math.ceil(quantity / 5) * 5) if quantity >= 10 else round(quantity, 1)
    if unit in ("tsp", "cup"):
        return math.ceil(quantity * 4) / 4
    return float(math.ceil(quantity))  # things bought whole: eggs, tins, onions


def _display(quantity: float, unit: str) -> tuple[float, str]:
    if unit == "g" and quantity >= 1000:
        return round(quantity / 1000, 2), "kg"
    if unit == "ml" and quantity >= 1000:
        return round(quantity / 1000, 2), "l"
    if unit == "tsp" and quantity >= 3 and (quantity / 3 * 2).is_integer():
        return quantity / 3, "tbsp"
    return quantity, unit


def build_grocery_lines(
    meals: list[tuple[Recipe, int]],
    staples: list[str] | None = None,
    pantry: list[PantryItem] | None = None,
    packs: dict[str, dict] | None = None,
) -> list[GroceryLine]:
    """Merge the scaled ingredients of every planned meal into one list.

    The same ingredient in compatible units becomes one line ("onion 2" + "onion 1"
    is "onion 3"). Staples the household always has are left out, food already in the
    pantry is taken off, and food sold in typical packs is bought in whole packs.
    """
    skip = set(staples or [])
    merged: dict[tuple[str, str], GroceryLine] = {}

    for recipe, portions in meals:
        for ingredient in scale_ingredients(recipe, portions):
            if ingredient.name in skip:
                continue
            unit, factor = _TO_BASE.get(ingredient.unit, (ingredient.unit, 1.0))
            quantity = None if ingredient.quantity is None else ingredient.quantity * factor
            # "Salt, to taste" has no amount: keep it as its own unitless line.
            key = (ingredient.name, unit if quantity is not None else "?")
            line = merged.get(key)
            if line is None:
                line = merged[key] = GroceryLine(ingredient.name, quantity, unit, ingredient.aisle)
            elif quantity is not None:
                line.quantity = (line.quantity or 0) + quantity
            if line.aisle == "other":
                line.aisle = ingredient.aisle
            if recipe.title not in line.recipes:
                line.recipes.append(recipe.title)

    lines = []
    for line in merged.values():
        if pantry:
            found, have = pantry_logic.available(pantry, line.name, line.unit)
            if found and (have is None or line.quantity is None):
                line.note = "you have some at home"
            elif found and have:
                if have >= (line.quantity or 0) - 1e-9:
                    continue  # all of it is at home already
                line.quantity = (line.quantity or 0) - have
                line.note = "the rest is at home"
        unsure = line.note == "you have some at home"
        pack = (
            pack_for(line.name, line.unit, packs)
            if packs and line.quantity and not unsure
            else None
        )
        if pack is not None and line.quantity is not None:
            count = pantry_logic.packs_needed(line.quantity, pack["size"])
            needed = _round_up(line.quantity, line.unit)
            line.pack = pack_label(count, pack)
            bought, unit = _display(float(count * pack["size"]), line.unit)
            # The needed amount in the same unit as the amount bought ("0.15 kg", not "150 kg").
            scale = bought / (count * pack["size"])
            line.needed = round(needed * scale, 3)
            line.quantity, line.unit = bought, unit
        elif line.quantity is not None:
            rounded = _round_up(line.quantity, line.unit)
            line.quantity, line.unit = _display(rounded, line.unit)
        lines.append(line)
    lines.sort(key=lambda line: (line.aisle, line.name))
    return lines
