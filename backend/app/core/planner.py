"""Weekly plan selection. Pure functions: no database, no AI, no clock.

The rules are enforced by counting, so a plan either satisfies them or the
shortfall is reported; nothing here depends on a language model.
"""

import random
from collections.abc import Iterable

from app import standards
from app.core.balance import food_group
from app.models import Alternative, Recipe, Rule, RuleStatus


def matches(recipe: Recipe, rule: Rule | str) -> bool:
    """A rule matches a recipe's main protein or any of its tags.

    Balanced-week rules can also match several proteins ("fish" or "seafood") or a
    food group among the ingredients (any vegetable).
    """
    if isinstance(rule, str):
        rule = Rule(count=0, tag=rule)
    words = {rule.tag, *rule.also}
    if recipe.protein in words or words & set(recipe.tags):
        return True
    if rule.food_group:
        rules_data = standards.load()
        return any(food_group(i.name, rules_data) == rule.food_group for i in recipe.ingredients)
    return False


def max_repeats(slot_count: int, max_repeat_ratio: float) -> int:
    """How many meals may come from recent weeks, e.g. 9 slots at 20% gives 1."""
    return int(slot_count * max_repeat_ratio + 1e-9)


def _count(recipes: Iterable[Recipe], rule: Rule | str) -> int:
    return sum(1 for recipe in recipes if matches(recipe, rule))


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
            not matches(recipe, rule) or _count(chosen, rule) < rule.count for rule in max_rules
        )

    def add(recipe: Recipe) -> None:
        chosen.append(recipe)
        chosen_ids.add(recipe.id)

    # Hardest rules first: the ones with the fewest matching recipes.
    for rule in sorted(min_rules, key=lambda rule: _count(recipes, rule)):
        for recipe in ordered(r for r in recipes if matches(r, rule)):
            if len(chosen) >= slot_count or _count(chosen, rule) >= rule.count:
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
        count = _count(planned, rule)
        name = rule.label or rule.tag
        if rule.kind == "min":
            label, ok = f"At least {rule.count} {name}", count >= rule.count
        else:
            label, ok = f"At most {rule.count} {name}", count <= rule.count
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
    """Every recipe that could replace the meal in ``slot``, rule-keeping ones first.

    Nothing is left out except the recipe already in this slot: recipes planned on
    other days are included and flagged, since choosing a meal is always free.
    """
    others = [recipe for key, recipe in planned_by_slot.items() if key != slot]
    current = planned_by_slot.get(slot)
    other_ids = {recipe.id for recipe in others}

    def failures(planned: list[Recipe]) -> int:
        statuses = rule_status(planned, slot_count, rules, recent_ids, max_repeat_ratio)
        return sum(1 for status in statuses if not status.ok)

    # A swap "keeps the rules" if it leaves no more rules broken than removing the meal would.
    baseline = min(failures(list(planned_by_slot.values())), failures(others))
    options = [
        Alternative(
            recipe=recipe,
            keeps_rules=failures([*others, recipe]) <= baseline,
            already_planned=recipe.id in other_ids,
        )
        for recipe in recipes
        if current is None or recipe.id != current.id
    ]
    options.sort(
        key=lambda option: (
            not option.keeps_rules,
            option.already_planned,
            option.recipe.id in recent_ids,
            option.recipe.last_planned_week or "",
            option.recipe.title.lower(),
        )
    )
    return options
