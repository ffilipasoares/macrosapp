"""Macros from ingredient data. Pure arithmetic: the AI only estimates per-ingredient values.

Each ingredient may carry an estimate of how much one unit weighs and its macros per
100 g. A recipe's totals are the sum over its ingredients, so changing an amount
updates the macros exactly, without asking the AI again.
"""

from collections.abc import Iterable
from typing import Any

# Units with a fixed weight in grams. Volumes are left to the estimate (oil is not water).
FIXED_GRAMS = {"g": 1.0, "kg": 1000.0}


def grams_of(quantity: float | None, unit: str, grams_per_unit: float | None) -> float | None:
    """The weight of an ingredient line, or None if it cannot be known."""
    if quantity is None:
        return None
    per_unit = FIXED_GRAMS.get(unit, grams_per_unit)
    if per_unit is None:
        return None
    return quantity * per_unit


def recipe_totals(ingredients: Iterable[Any]) -> dict | None:
    """Total kcal, protein, carbs, fat and raw weight of a whole recipe as written.

    Lines without an amount ("salt, to taste") are left out and do not count as
    missing. Lines with an amount but no estimate are listed in ``missing``.
    Returns None when no ingredient has an estimate yet.
    """
    totals = {"kcal": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0, "weight_g": 0.0}
    missing: list[str] = []
    known = 0
    for ingredient in ingredients:
        if ingredient.quantity is None:
            continue
        data = ingredient.nutrition
        grams = grams_of(
            ingredient.quantity, ingredient.unit, data.grams_per_unit if data else None
        )
        if data is None or grams is None:
            missing.append(ingredient.name)
            continue
        known += 1
        share = grams / 100
        totals["kcal"] += data.kcal_per_100g * share
        totals["protein_g"] += data.protein_per_100g * share
        totals["carbs_g"] += data.carbs_per_100g * share
        totals["fat_g"] += data.fat_per_100g * share
        totals["weight_g"] += grams
    if known == 0:
        return None
    return {key: round(value, 1) for key, value in totals.items()} | {"missing": missing}


def portion_factor(
    servings: int, weight_g: float, reference_kind: str, reference_grams: int
) -> float:
    """What share of the whole recipe one reference portion is."""
    if reference_kind == "grams" and weight_g > 0:
        return reference_grams / weight_g
    return 1 / max(servings, 1)
