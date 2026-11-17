"""The week balance check. Pure functions.

Everything a nutritionist would decide (targets, which foods count as what) comes
from the standards; this module only counts.
"""

import math
import re
from collections.abc import Iterable
from typing import Any

from app.models import Rule
from app.standards import Standards


def _matches(name: str, keyword: str) -> bool:
    # Whole words, allowing a plural: "chickpeas" matches "chickpea", "pea" does not match "peanut".
    return re.search(rf"\b{re.escape(keyword)}(e?s)?\b", name) is not None


def food_group(name: str, standards: Standards) -> str | None:
    """The food group an ingredient belongs to, if the standards list it.

    Longer keywords win, so "green bean" is a vegetable, not a legume.
    """
    best: tuple[int, str] | None = None
    for group, keywords in standards.foods.items():
        for keyword in keywords:
            if _matches(name, keyword) and (best is None or len(keyword) > best[0]):
                best = (len(keyword), group)
    return best[1] if best else None


def week_balance(meals: Iterable[tuple[str, Any]], standards: Standards) -> dict:
    """Check a week of (slot, recipe) pairs against the standards."""
    meals = list(meals)
    vegetable_days: set[str] = set()
    planned_days: set[str] = set()
    legume_meals = 0
    proteins: list[str] = []

    for slot, recipe in meals:
        day = slot.split("_")[0]
        planned_days.add(day)
        proteins.append(recipe.protein or "other")
        groups = {food_group(i.name, standards) for i in recipe.ingredients}
        if "vegetables" in groups:
            vegetable_days.add(day)
        legume_meals += "legumes" in groups or recipe.protein == "legumes"

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

    return {
        "balanced": bool(meals) and all(check["ok"] for check in checks),
        "checks": checks,
        "standards_version": standards.version,
        "reviewed": standards.reviewed_by is not None,
    }


def planner_rules(standards: Standards, slot_count: int) -> list[Rule]:
    """The balance checks the planner can aim for, as counting rules.

    "Vegetables most days" becomes vegetables in that share of the meals. The
    variety of proteins is not a rule: the planner already spreads proteins.
    """
    checks = standards.checks
    rules = []
    if (check := checks.get("vegetable_days")) and check.min_share_of_days:
        count = math.ceil(check.min_share_of_days * slot_count)
        rules.append(
            Rule(kind="min", count=count, tag="vegetables", food_group="vegetables",
                 label=check.label.lower())
        )  # fmt: skip
    if (check := checks.get("fish")) and check.min_meals:
        fish = standards.proteins.get("fish", [])
        rules.append(Rule(kind="min", count=check.min_meals, tag="fish", also=fish, label="fish"))
    if (check := checks.get("legumes")) and check.min_meals:
        rules.append(
            Rule(kind="min", count=check.min_meals, tag="legumes", food_group="legumes",
                 label="beans, lentils or chickpeas")
        )  # fmt: skip
    if (check := checks.get("red_meat")) and check.max_meals is not None:
        red = standards.proteins.get("red_meat", [])
        rules.append(
            Rule(kind="max", count=check.max_meals, tag="red meat", also=red, label="red meat")
        )
    return [rule for rule in rules if 0 <= rule.count <= 14]
