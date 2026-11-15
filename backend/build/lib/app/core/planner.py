"""Weekly plan selection. Pure functions: no database, no AI, no clock.

The rules are enforced by counting, so a plan either satisfies them or the
shortfall is reported; nothing here depends on a language model.
"""

import random
from collections.abc import Iterable

from app.models import Alternative, Recipe, Rule, RuleStatus


def matches(recipe: Recipe, tag: str) -> bool:
    """A rule tag matches a recipe's main protein or any of its tags."""
    return recipe.protein == tag or tag in recipe.tags


def max_repeats(slot_count: int, max_repeat_ratio: float) -> int:
    """How many meals may come from recent weeks, e.g. 9 slots at 20% gives 1."""
    return int(slot_count * max_repeat_ratio + 1e-9)


def _count(recipes: Iterable[Recipe], tag: str) -> int:
    return sum(1 for recipe in recipes if matches(recipe, tag))


def pick_recipes(
    recipes: list[Recipe],
    slot_count: int,
    rules: list[Rule],
    recent_ids: set[str],
    max_repeat_ratio: float,
    rng: random.Random,
) -> list[Recipe]:
    """Choose up to ``slot_count`` different recipes.

    Order of priority: never exceed a "max" rule or the repeat allowance, then
    satisfy "min" rules, then prefer recipes that were cooked longest ago.
    Returns fewer than ``slot_count`` recipes when the library is too small.
    """
    repeat_budget = max_repeats(slot_count, max_repeat_ratio)
    min_rules = [rule for rule in rules if rule.kind == "min"]
    max_rules = [rule for rule in rules if rule.kind == "max"]

    def ordered(pool: Iterable[Recipe]) -> list[Recipe]:
        shuffled = list(pool)
        rng.shuffle(shuffled)
        # Fresh before recent, then never-planned first, then oldest first.
        shuffled.sort(key=lambda r: (r.id in recent_ids, r.last_planned_week or ""))
        return shuffled

    chosen: list[Recipe] = []
    chosen_ids: set[str] = set()

    def can_add(recipe: Recipe) -> bool:
        if recipe.id in chosen_ids:
            return False
        repeats_used = sum(1 for r in chosen if r.id in recent_ids)
        if recipe.id in recent_ids and repeats_used >= repeat_budget:
            return False
        return all(
            not matches(recipe, rule.tag) or _count(chosen, rule.tag) < rule.count
            for rule in max_rules
        )

    def add(recipe: Recipe) -> None:
        chosen.append(recipe)
        chosen_ids.add(recipe.id)

    # Hardest rules first: the ones with the fewest matching recipes.
    for rule in sorted(min_rules, key=lambda rule: _count(recipes, rule.tag)):
        for recipe in ordered(r for r in recipes if matches(r, rule.tag)):
            if len(chosen) >= slot_count or _count(chosen, rule.tag) >= rule.count:
                break
            if can_add(recipe):
                add(recipe)

    for recipe in ordered(recipes):
        if len(chosen) >= slot_count:
            break
        if can_add(recipe):
            add(recipe)

    rng.shuffle(chosen)
    return chosen


def rule_status(
    planned: list[Recipe],
    slot_count: int,
    rules: list[Rule],
    recent_ids: set[str],
    max_repeat_ratio: float,
) -> list[RuleStatus]:
    """Where a plan stands against every rule, for display and for checking swaps."""
    statuses = []
    for rule in rules:
        count = _count(planned, rule.tag)
        if rule.kind == "min":
            label, ok = f"At least {rule.count} {rule.tag}", count >= rule.count
        else:
            label, ok = f"At most {rule.count} {rule.tag}", count <= rule.count
        statuses.append(RuleStatus(label=label, ok=ok, count=count, target=rule.count))

    budget = max_repeats(slot_count, max_repeat_ratio)
    repeats = sum(1 for recipe in planned if recipe.id in recent_ids)
    statuses.append(
        RuleStatus(
            label=f"At most {budget} repeated from recent weeks",
            ok=repeats <= budget,
            count=repeats,
            target=budget,
        )
    )
    return statuses


def alternatives(
    planned_by_slot: dict[str, Recipe],
    slot: str,
    recipes: list[Recipe],
    slot_count: int,
    rules: list[Rule],
    recent_ids: set[str],
    max_repeat_ratio: float,
) -> list[Alternative]:
    """Recipes that could replace the meal in ``slot``, rule-keeping ones first."""
    others = [recipe for key, recipe in planned_by_slot.items() if key != slot]
    used_ids = {recipe.id for recipe in planned_by_slot.values()}

    def failures(planned: list[Recipe]) -> int:
        statuses = rule_status(planned, slot_count, rules, recent_ids, max_repeat_ratio)
        return sum(1 for status in statuses if not status.ok)

    # A swap "keeps the rules" if it leaves no more rules broken than removing the meal would.
    baseline = min(failures(list(planned_by_slot.values())), failures(others))
    options = [
        Alternative(recipe=recipe, keeps_rules=failures([*others, recipe]) <= baseline)
        for recipe in recipes
        if recipe.id not in used_ids
    ]
    options.sort(
        key=lambda option: (
            not option.keeps_rules,
            option.recipe.id in recent_ids,
            option.recipe.last_planned_week or "",
            option.recipe.title.lower(),
        )
    )
    return options
