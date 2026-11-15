"""Portion scaling and grocery-list merging. Pure functions."""

import math
from dataclasses import dataclass, field

from app.models import Ingredient, Recipe

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
    meals: list[tuple[Recipe, int]], staples: list[str] | None = None
) -> list[GroceryLine]:
    """Merge the scaled ingredients of every planned meal into one list.

    The same ingredient in compatible units becomes one line ("onion 2" + "onion 1"
    is "onion 3"). Staples the household always has are left out.
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
        if line.quantity is not None:
            rounded = _round_up(line.quantity, line.unit)
            line.quantity, line.unit = _display(rounded, line.unit)
        lines.append(line)
    lines.sort(key=lambda line: (line.aisle, line.name))
    return lines
