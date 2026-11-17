"""The week balance check and the count of different plants. Pure functions.

Everything a nutritionist would decide (targets, which foods count as what) comes
from the standards; this module only counts.
"""

import math
import re
from collections.abc import Iterable
from typing import Any

from app.standards import Standards

# Food groups that count as plants; herbs and spices count partly.
PLANT_GROUPS = (
    "herbs_spices", "legumes", "whole_grains", "nuts_seeds", "fruit", "starchy_vegetables",
    "vegetables",
)  # fmt: skip


def _matches(name: str, keyword: str) -> bool:
    # Whole words, allowing a plural: "chickpeas" matches "chickpea", "pea" does not match "peanut".
    return re.search(rf"\b{re.escape(keyword)}(e?s)?\b", name) is not None


def classify(name: str, aisle: str, standards: Standards) -> tuple[str | None, str | None]:
    """The food group of an ingredient and the plant it counts as, if any.

    Longer keywords win, so "sweet potato" is a starchy vegetable, not "potato" alone,
    and "coriander seed" is a spice. Unknown items from the produce aisle still count
    as a vegetable, under their own name.
    """
    if any(_matches(name, word) for word in standards.not_plants):
        return None, None  # olive oil, vegetable stock
    best: tuple[int, str, str] | None = None
    for group in PLANT_GROUPS:
        for keyword in standards.foods.get(group, []):
            if _matches(name, keyword) and (best is None or len(keyword) > best[0]):
                best = (len(keyword), group, keyword)
    if best:
        return best[1], best[2]
    if aisle == "produce":
        return "vegetables", name
    return None, None


def week_balance(meals: Iterable[tuple[str, Any]], standards: Standards) -> dict:
    """Check a week of (slot, recipe) pairs against the standards."""
    meals = list(meals)
    plants: dict[str, float] = {}
    vegetable_days: set[str] = set()
    planned_days: set[str] = set()
    legume_meals = 0
    proteins: list[str] = []

    for slot, recipe in meals:
        day = slot.split("_")[0]
        planned_days.add(day)
        proteins.append(recipe.protein or "other")
        has_legumes = False
        for ingredient in recipe.ingredients:
            group, plant = classify(ingredient.name, ingredient.aisle, standards)
            if plant is None:
                continue
            weight = standards.plants.partial_weight if group == "herbs_spices" else 1.0
            plants[plant] = max(plants.get(plant, 0.0), weight)
            if group == "vegetables":
                vegetable_days.add(day)
            if group == "legumes":
                has_legumes = True
        legume_meals += has_legumes

    def count_protein(kind: str) -> int:
        return sum(1 for p in proteins if p in standards.proteins.get(kind, []))

    days = len(planned_days)
    measured = {
        # key: (value, detail, comparison field in the standard)
        "vegetable_days": (len(vegetable_days), f"{len(vegetable_days)} of {days} days", None),
        "fish": (count_protein("fish"), None, "min_meals"),
        "legumes": (legume_meals, None, "min_meals"),
        "red_meat": (count_protein("red_meat"), None, "max_meals"),
        "protein_variety": (len({p for p in proteins if p != "other"}), None, "min_kinds"),
    }
    checks = []
    for key, rule in standards.checks.items():
        if key not in measured:
            continue  # a standard this version of the app does not know yet
        value, detail, field = measured[key]
        if key == "vegetable_days":
            target = math.ceil((rule.min_share_of_days or 0) * days)
        else:
            target = getattr(rule, field)
            if target is None:
                continue
        if field == "max_meals":
            ok = value <= target
        else:
            ok = value >= target
        unit = "kinds" if key == "protein_variety" else "meals"
        checks.append(
            {
                "key": key,
                "label": rule.label,
                "ok": ok,
                "value": value,
                "target": target,
                "detail": detail or f"{value} {unit}",
            }
        )

    plant_count = round(sum(plants.values()), 2)
    return {
        "balanced": bool(meals) and all(check["ok"] for check in checks),
        "checks": checks,
        "plants": plant_count,
        "plants_target": standards.plants.target,
        "plant_names": sorted(plants),
        "standards_version": standards.version,
        "reviewed": standards.reviewed_by is not None,
    }
