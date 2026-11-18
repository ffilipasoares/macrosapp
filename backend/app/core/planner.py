"""Weekly plan selection. Pure functions: no database, no AI, no clock.

The rules are enforced by counting, so a plan either satisfies them or the
shortfall is reported; nothing here depends on a language model.
"""

import random
from collections.abc import Iterable
from dataclasses import dataclass

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


# Variety, the same for everyone: nothing from last week comes back, and at least half
# of the week is different from two weeks before.
TWO_WEEKS_AGO_SHARE = 0.5


@dataclass(frozen=True)
class Recent:
    """The recipes of the two weeks before the one being planned."""

    last_week: frozenset[str] = frozenset()
    two_weeks_ago: frozenset[str] = frozenset()


def max_repeats(slot_count: int, share: float = TWO_WEEKS_AGO_SHARE) -> int:
    """How many meals may come from two weeks ago, e.g. 5 meals at 50% gives 2."""
    return int(slot_count * share + 1e-9)


def _count(recipes: Iterable[Recipe], rule: Rule | str) -> int:
    return sum(1 for recipe in recipes if matches(recipe, rule))


def pick_recipes(
    recipes: list[Recipe],
    slot_count: int,
    rules: list[Rule],
    recent: Recent,
    rng: random.Random,
    prefer: dict[str, float] | None = None,
) -> list[Recipe]:
    """Choose up to ``slot_count`` different recipes.

    Recipes from last week are never chosen. Order of priority: never exceed a "max"
    rule or the share allowed from two weeks ago, then
    satisfy "min" rules, then prefer recipes that use food already at home
    (``prefer``: a score per recipe id) and fresh food already bought for another
    meal this week, then recipes that were cooked longest ago.
    Returns fewer than ``slot_count`` recipes when the library is too small.
    """
    prefer = prefer or {}
    recent_ids = recent.two_weeks_ago
    recipes = [recipe for recipe in recipes if recipe.id not in recent.last_week]
    repeat_budget = max_repeats(slot_count)
    min_rules = [rule for rule in rules if rule.kind == "min"]
    max_rules = [rule for rule in rules if rule.kind == "max"]

    def ordered(pool: Iterable[Recipe]) -> list[Recipe]:
        shuffled = list(pool)
        rng.shuffle(shuffled)
        # Fresh before recent, then food at home first, then never-planned, then oldest.
        shuffled.sort(
            key=lambda r: (r.id in recent_ids, -prefer.get(r.id, 0.0), r.last_planned_week or "")
        )
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

    # Fill the rest, keeping that order, but among equally good recipes take the one
    # that shares the most fresh food with meals already chosen: one bag of spinach
    # then covers two meals.
    rest = [recipe for recipe in ordered(recipes) if recipe.id not in chosen_ids]
    while len(chosen) < slot_count:
        options = [recipe for recipe in rest if can_add(recipe)]
        if not options:
            break
        best = options[0]
        rank = (best.id in recent_ids, -prefer.get(best.id, 0.0))
        same_rank = [r for r in options if (r.id in recent_ids, -prefer.get(r.id, 0.0)) == rank]
        pick = max(same_rank, key=lambda r: _shared_fresh(r, chosen))  # first wins a tie
        rest.remove(pick)
        add(pick)

    rng.shuffle(chosen)
    return chosen


# Meat and fish are left out: sharing them would make two meals of the same protein.
_FRESH = ("produce", "dairy_eggs", "bakery")


def _shared_fresh(recipe: Recipe, chosen: list[Recipe]) -> int:
    fresh = {i.name for r in chosen for i in r.ingredients if i.aisle in _FRESH}
    return sum(1 for i in recipe.ingredients if i.aisle in _FRESH and i.name in fresh)


def rule_status(
    planned: list[Recipe],
    slot_count: int,
    rules: list[Rule],
    recent: Recent,
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

    budget = max_repeats(slot_count)
    repeats = sum(1 for recipe in planned if recipe.id in recent.two_weeks_ago)
    from_last_week = sum(1 for recipe in planned if recipe.id in recent.last_week)
    statuses.append(
        RuleStatus(
            label=f"Nothing from last week, at most {budget} from two weeks ago",
            ok=from_last_week == 0 and repeats <= budget,
            count=repeats + from_last_week,
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
    recent: Recent,
) -> list[Alternative]:
    """Every recipe that could replace the meal in ``slot``, rule-keeping ones first.

    Nothing is left out except the recipe already in this slot: recipes planned on
    other days are included and flagged, since choosing a meal is always free.
    """
    others = [recipe for key, recipe in planned_by_slot.items() if key != slot]
    current = planned_by_slot.get(slot)
    other_ids = {recipe.id for recipe in others}

    def failures(planned: list[Recipe]) -> int:
        # Variety (the last status) only guides automatic choices; picking by hand is free.
        statuses = rule_status(planned, slot_count, rules, recent)[:-1]
        return sum(1 for status in statuses if not status.ok)

    # A swap "keeps the rules" if it leaves no more rules broken than removing the meal would.
    baseline = min(failures(list(planned_by_slot.values())), failures(others))
    options = [
        Alternative(
            recipe=recipe,
            keeps_rules=failures([*others, recipe]) <= baseline,
            already_planned=recipe.id in other_ids,
            last_week=recipe.id in recent.last_week,
        )
        for recipe in recipes
        if current is None or recipe.id != current.id
    ]
    options.sort(
        key=lambda option: (
            not option.keeps_rules,
            option.already_planned,
            option.last_week,
            option.recipe.id in recent.two_weeks_ago,
            option.recipe.last_planned_week or "",
            option.recipe.title.lower(),
        )
    )
    return options
