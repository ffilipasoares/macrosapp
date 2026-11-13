"""Use cases: each function loads data, calls the pure core logic and saves the result."""

import logging
import random
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.ai.base import AIError, RecipeAI
from app.core import planner
from app.core.grocery import build_grocery_lines
from app.core.ingredients import guess_aisle, normalize_name
from app.core.weeks import SLOT_KEYS, next_week_id, previous_week_ids
from app.models import (
    Alternative,
    GroceryItem,
    PlanMeal,
    PlanOut,
    Recipe,
    Settings,
    WeekPlan,
    now,
)
from app.notify import Notifier
from app.repo.base import Repo

log = logging.getLogger(__name__)


class NotFound(Exception):
    pass


def recent_recipe_ids(repo: Repo, household_id: str, week_id: str, settings: Settings) -> set[str]:
    """Recipes planned in the weeks just before ``week_id``."""
    ids: set[str] = set()
    for previous in previous_week_ids(week_id, settings.repeat_window_weeks):
        plan = repo.get_plan(household_id, previous)
        if plan:
            ids.update(meal.recipe.id for meal in plan.meals.values())
    return ids


def plan_out(repo: Repo, household_id: str, plan: WeekPlan) -> PlanOut:
    settings = repo.get_settings(household_id)
    cook_slots = settings.cook_slots()
    slot_count = max(len(cook_slots), len(plan.meals))
    statuses = planner.rule_status(
        [meal.recipe for meal in plan.meals.values()],
        slot_count,
        settings.rules,
        recent_recipe_ids(repo, household_id, plan.week_id, settings),
        settings.max_repeat_ratio,
    )
    open_slots = [slot for slot in cook_slots if slot not in plan.meals]
    return PlanOut(**plan.model_dump(), rule_status=statuses, open_slots=open_slots)


def _fill_with_suggestions(
    ai: RecipeAI,
    picks: list[Recipe],
    slot_count: int,
    settings: Settings,
    library_titles: list[str],
) -> tuple[list[Recipe], set[str]]:
    """Use web recipes to cover what the library could not: unmet rules, then empty slots."""
    picks = list(picks)
    new_ids: set[str] = set()
    min_rules = [rule for rule in settings.rules if rule.kind == "min"]
    max_rules = [rule for rule in settings.rules if rule.kind == "max"]
    titles = list(library_titles)

    def count(tag: str) -> int:
        return sum(1 for recipe in picks if planner.matches(recipe, tag))

    def allowed(recipe: Recipe) -> bool:
        return all(
            not planner.matches(recipe, rule.tag) or count(rule.tag) < rule.count
            for rule in max_rules
        )

    def suggest(query: str, amount: int) -> list[Recipe]:
        recipes = [Recipe(**d.model_dump()) for d in ai.search_recipes(query, amount, titles)]
        titles.extend(recipe.title for recipe in recipes)
        return recipes

    for rule in min_rules:
        missing = rule.count - count(rule.tag)
        if missing <= 0:
            continue
        for recipe in suggest(f"healthy {rule.tag} dinner", missing):
            if not planner.matches(recipe, rule.tag) or not allowed(recipe):
                continue
            if len(picks) >= slot_count:
                # No free slot: replace a meal that no "at least" rule depends on.
                spare = next(
                    (
                        index
                        for index in range(len(picks) - 1, -1, -1)
                        if not any(planner.matches(picks[index], r.tag) for r in min_rules)
                    ),
                    None,
                )
                if spare is None:
                    break
                picks.pop(spare)
            picks.append(recipe)
            new_ids.add(recipe.id)

    gaps = slot_count - len(picks)
    if gaps > 0:
        for recipe in suggest("healthy easy dinner", gaps):
            if len(picks) < slot_count and allowed(recipe):
                picks.append(recipe)
                new_ids.add(recipe.id)
    return picks, new_ids


def generate_plan(
    repo: Repo, ai: RecipeAI | None, household_id: str, week_id: str, rng: random.Random
) -> WeekPlan:
    """Build a draft plan for a week and save it under the week's id."""
    settings = repo.get_settings(household_id)
    slots = settings.cook_slots()
    recipes = repo.list_recipes(household_id)
    recent = recent_recipe_ids(repo, household_id, week_id, settings)

    picks = planner.pick_recipes(
        recipes, len(slots), settings.rules, recent, settings.max_repeat_ratio, rng
    )
    notes: list[str] = []
    new_ids: set[str] = set()

    statuses = planner.rule_status(
        picks, len(slots), settings.rules, recent, settings.max_repeat_ratio
    )
    if ai is not None and (len(picks) < len(slots) or not all(s.ok for s in statuses)):
        try:
            picks, new_ids = _fill_with_suggestions(
                ai, picks, len(slots), settings, [recipe.title for recipe in recipes]
            )
        except AIError as error:
            notes.append(f"Could not look for new recipes: {error}")

    if len(picks) < len(slots):
        notes.append(
            f"Only {len(picks)} of {len(slots)} meals could be filled without breaking your "
            "rules. Add more recipes to your library."
        )

    plan = WeekPlan(
        week_id=week_id,
        meals={
            slot: PlanMeal(
                recipe=recipe, portions=settings.slots[slot].portions, is_new=recipe.id in new_ids
            )
            for slot, recipe in zip(slots, picks, strict=False)
        },
        notes=notes,
    )
    repo.save_plan(household_id, plan)
    return plan


def set_meal(
    repo: Repo,
    household_id: str,
    week_id: str,
    slot: str,
    recipe_id: str | None,
    portions: int | None,
) -> WeekPlan:
    """Put a recipe in a slot, change its portions, or clear the slot."""
    if slot not in SLOT_KEYS:
        raise NotFound(f"Unknown meal slot: {slot}")
    plan = repo.get_plan(household_id, week_id) or WeekPlan(week_id=week_id)
    existing = plan.meals.get(slot)

    if recipe_id is None:
        plan.meals.pop(slot, None)
    else:
        if existing and existing.recipe.id == recipe_id:
            recipe = existing.recipe
        else:
            recipe = repo.get_recipe(household_id, recipe_id)
            if recipe is None:
                raise NotFound("Recipe not found")
        default = (
            existing.portions if existing else repo.get_settings(household_id).slots[slot].portions
        )
        plan.meals[slot] = PlanMeal(
            recipe=recipe,
            portions=portions or default,
            is_new=bool(existing and existing.is_new and existing.recipe.id == recipe_id),
        )

    # Any change means the grocery list no longer matches, so approval is needed again.
    plan.status = "draft"
    plan.approved_at = None
    repo.save_plan(household_id, plan)
    return plan


def meal_alternatives(repo: Repo, household_id: str, week_id: str, slot: str) -> list[Alternative]:
    if slot not in SLOT_KEYS:
        raise NotFound(f"Unknown meal slot: {slot}")
    settings = repo.get_settings(household_id)
    plan = repo.get_plan(household_id, week_id) or WeekPlan(week_id=week_id)
    planned = {key: meal.recipe for key, meal in plan.meals.items()}
    slot_count = max(len(settings.cook_slots()), len(planned))
    return planner.alternatives(
        planned,
        slot,
        repo.list_recipes(household_id),
        slot_count,
        settings.rules,
        recent_recipe_ids(repo, household_id, week_id, settings),
        settings.max_repeat_ratio,
    )


def approve_plan(repo: Repo, household_id: str, week_id: str) -> tuple[WeekPlan, int]:
    """Lock in the plan and turn it into grocery items. Safe to run more than once."""
    plan = repo.get_plan(household_id, week_id)
    if plan is None:
        raise NotFound("There is no plan for this week yet")
    settings = repo.get_settings(household_id)

    ordered = [plan.meals[slot] for slot in SLOT_KEYS if slot in plan.meals]
    lines = build_grocery_lines(
        [(meal.recipe, meal.portions) for meal in ordered], settings.staples
    )
    items = [
        GroceryItem(
            name=line.name,
            quantity=line.quantity,
            unit=line.unit,
            aisle=line.aisle,
            source="plan",
            week_id=week_id,
            recipes=line.recipes,
        )
        for line in lines
    ]
    repo.delete_plan_groceries(household_id, week_id)
    repo.add_groceries(household_id, items)

    # Remember when each recipe was last cooked; keep recipes that came from a web suggestion.
    for meal in ordered:
        stored = repo.get_recipe(household_id, meal.recipe.id) or meal.recipe
        if (stored.last_planned_week or "") < week_id:
            stored.last_planned_week = week_id
        repo.save_recipe(household_id, stored)

    plan.status = "approved"
    plan.approved_at = now()
    repo.save_plan(household_id, plan)
    return plan, len(items)


def add_items_from_text(
    repo: Repo, household_id: str, text: str, source: str = "manual"
) -> list[GroceryItem]:
    """Add one or more items said or typed in plain words: "milk, eggs and bread"."""
    names = [part.strip(" .") for part in re.split(r",|\band\b|\n", text, flags=re.IGNORECASE)]
    waiting = {
        normalize_name(item.name)
        for item in repo.list_groceries(household_id)
        if not item.checked and item.quantity is None
    }
    items = []
    for name in names:
        key = normalize_name(name)
        if not key or key in waiting:  # already on the list
            continue
        waiting.add(key)
        items.append(
            GroceryItem(name=name.lower()[:120], aisle=guess_aisle(name), source=source)  # type: ignore[arg-type]
        )
    repo.add_groceries(household_id, items)
    return items


def run_weekly_job(
    repo: Repo,
    ai: RecipeAI | None,
    notifier: Notifier,
    app_url: str,
    today: date | None = None,
    rng: random.Random | None = None,
) -> dict[str, int]:
    """Draft next week's plan for every household and tell them it is ready.

    A household that already has a plan for next week is skipped, so running the
    job twice does not overwrite changes or send a second notification.
    """
    summary = {"generated": 0, "skipped": 0, "failed": 0}
    for household in repo.list_households():
        try:
            settings = repo.get_settings(household.id)
            local_today = today or datetime.now(ZoneInfo(settings.timezone)).date()
            target = next_week_id(local_today)
            if repo.get_plan(household.id, target) is not None:
                summary["skipped"] += 1
                continue
            generate_plan(repo, ai, household.id, target, rng or random.Random())
            invalid = notifier.send(
                household.device_tokens,
                "Meal plan ready",
                "Your meal plan for next week is ready.",
                f"{app_url}/plan/{target}" if app_url else "",
            )
            repo.remove_device_tokens(household.id, invalid)
            summary["generated"] += 1
        except Exception:
            log.exception("Weekly plan failed for household %s", household.id)
            summary["failed"] += 1
    return summary
