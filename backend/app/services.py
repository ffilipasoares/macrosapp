"""Use cases: each function loads data, calls the pure core logic and saves the result."""

import logging
import random
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app import standards
from app.ai.base import AIError, RecipeAI
from app.core import balance, planner
from app.core.diet import fits, needs_verdict, search_phrase
from app.core.grocery import build_grocery_lines
from app.core.ingredients import guess_aisle, normalize_name
from app.core.weeks import SLOT_KEYS, next_week_id, previous_week_ids
from app.images import ImageStore, keep_own_copy
from app.links import LinkContent, read_image, read_link
from app.models import (
    Alternative,
    GroceryItem,
    PlanMeal,
    PlanOut,
    Recipe,
    Rule,
    Settings,
    WeekBalance,
    WeekPlan,
    now,
)
from app.notify import Notifier
from app.repo.base import Repo
from app.web_recipes import find_web_recipes

log = logging.getLogger(__name__)


class NotFound(Exception):
    pass


# How long plan generation may search the web, unless the server is configured otherwise.
WEB_SEARCH_SECONDS = 50
# How many recipes are judged against the diets in one AI call.
DIET_CHECK_BATCH = 40


@dataclass
class Web:
    """How the app reaches the internet: reading recipe pages and keeping copies of photos."""

    read_link: Callable[[str], LinkContent] = read_link
    read_image: Callable[[str], tuple[bytes, str]] = read_image
    images: ImageStore | None = field(default=None)
    search_seconds: float = field(default_factory=lambda: WEB_SEARCH_SECONDS)


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
    out = PlanOut(**plan.model_dump(), rule_status=statuses, open_slots=open_slots)

    # Meals are copies of recipes taken when planned. If macros were worked out since,
    # show them, as long as the ingredients are still the same.
    library = {recipe.id: recipe for recipe in repo.list_recipes(household_id)}
    for meal in out.meals.values():
        saved = library.get(meal.recipe.id)
        same = saved is not None and [(i.name, i.unit, i.quantity) for i in saved.ingredients] == [
            (i.name, i.unit, i.quantity) for i in meal.recipe.ingredients
        ]
        if same and meal.recipe.macros is None and saved.macros is not None:
            meal.recipe.ingredients = saved.ingredients
            meal.recipe.refresh_macros()

    out.balance = WeekBalance.model_validate(
        balance.week_balance(
            [(slot, meal.recipe) for slot, meal in out.meals.items()], standards.load()
        )
    )
    return out


def _fill_with_suggestions(
    ai: RecipeAI,
    web: Web,
    deadline: float,
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

    # What the web has to provide: recipes for each "at least" rule that is short,
    # and enough recipes overall to fill the empty meals. One search covers it all.
    needs = {rule.tag: rule.count - count(rule.tag) for rule in min_rules}
    needs = {tag: missing for tag, missing in needs.items() if missing > 0}
    gaps = max(0, slot_count - len(picks))
    total = max(gaps, sum(needs.values()))
    if total == 0:
        return picks, new_ids
    query = search_phrase(settings.diets, needs)
    # Ask for a couple more than needed, since some pages will not work.
    drafts = find_web_recipes(ai, web.read_link, query, total + 2, titles, deadline)
    found = []
    for draft in drafts:
        # Found by a search for these diets, so they count as fitting them.
        recipe = Recipe(**draft.model_dump(), diet_fit={d: True for d in settings.diets})
        if recipe.category == "main" and fits(settings.diets, recipe):
            found.append(recipe)

    def take(recipe: Recipe) -> None:
        found.remove(recipe)
        picks.append(recipe)
        new_ids.add(recipe.id)

    for rule in min_rules:
        for recipe in [r for r in found if planner.matches(r, rule.tag)]:
            if count(rule.tag) >= rule.count or not allowed(recipe):
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
            take(recipe)

    # Fill the rest with variety: each time, the protein used least so far this week.
    while len(picks) < slot_count:
        candidates = [recipe for recipe in found if allowed(recipe)]
        if not candidates:
            break
        take(
            min(candidates, key=lambda recipe: sum(1 for p in picks if p.protein == recipe.protein))
        )

    # If some web pages failed to load or did not cover every rule/slot, fill the remaining
    # gaps directly so a single Generate always produces a complete week.
    remaining_needs = {rule.tag: rule.count - count(rule.tag) for rule in min_rules}
    remaining_needs = {tag: missing for tag, missing in remaining_needs.items() if missing > 0}
    remaining_gaps = max(0, slot_count - len(picks))
    fallback_fn = getattr(ai, "generate_fallback_recipes", None)
    if (
        (remaining_needs or remaining_gaps > 0)
        and callable(fallback_fn)
        and time.monotonic() < deadline
    ):
        forbidden = [rule.tag for rule in max_rules if count(rule.tag) >= rule.count]
        used_titles = [*titles, *(r.title for r in picks)]
        try:
            extra_drafts = fallback_fn(
                remaining_needs,
                remaining_gaps,
                forbidden,
                used_titles,
                " and ".join(settings.diets),
            )
            # Written for these diets, so they count as fitting them.
            extra_found = [
                recipe
                for draft in extra_drafts
                if draft.category == "main"
                and fits(
                    settings.diets,
                    recipe := Recipe(
                        **draft.model_dump(), diet_fit={d: True for d in settings.diets}
                    ),
                )
            ]
        except AIError as error:
            log.warning("Fallback recipe generation failed: %s", error)
            extra_found = []

        for rule in min_rules:
            for recipe in [r for r in extra_found if planner.matches(r, rule.tag)]:
                if count(rule.tag) >= rule.count or not allowed(recipe):
                    continue
                if len(picks) >= slot_count:
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
                extra_found.remove(recipe)
                picks.append(recipe)
                new_ids.add(recipe.id)

        while len(picks) < slot_count:
            candidates = [recipe for recipe in extra_found if allowed(recipe)]
            if not candidates:
                break
            best = min(
                candidates, key=lambda recipe: sum(1 for p in picks if p.protein == recipe.protein)
            )
            extra_found.remove(best)
            picks.append(best)
            new_ids.add(best.id)

    return picks, new_ids


def check_diets(
    repo: Repo, ai: RecipeAI | None, household_id: str, recipes: list[Recipe], diets: list[str]
) -> str | None:
    """Make sure each recipe has been judged against each diet. Returns a problem, if any.

    Verdicts are stored on the recipe, so each recipe is only judged once per diet.
    Recipes that could not be judged are treated as fitting.
    """
    pending = [recipe for recipe in recipes if needs_verdict(diets, recipe)]
    if not pending or ai is None:
        return None
    try:
        for start in range(0, len(pending), DIET_CHECK_BATCH):
            batch = pending[start : start + DIET_CHECK_BATCH]
            verdicts = ai.check_diets(
                [(r.title, [i.name for i in r.ingredients]) for r in batch], diets
            )
            for recipe, verdict in zip(batch, verdicts, strict=False):
                if verdict:
                    recipe.diet_fit = {**recipe.diet_fit, **verdict}
                    repo.save_recipe(household_id, recipe)
    except AIError as error:
        log.warning("Could not check recipes against diets: %s", error)
        return f"Could not check your recipes against your diets: {error}"
    return None


def _adjusted_rules(rules: list[Rule], kept: list[Recipe]) -> list[Rule]:
    """The rules still to meet once some meals are already decided."""
    adjusted = []
    for rule in rules:
        already = sum(1 for recipe in kept if planner.matches(recipe, rule.tag))
        adjusted.append(rule.model_copy(update={"count": max(0, rule.count - already)}))
    return adjusted


def generate_plan(
    repo: Repo,
    ai: RecipeAI | None,
    household_id: str,
    week_id: str,
    rng: random.Random,
    web: Web | None = None,
    keep: dict[str, PlanMeal] | None = None,
) -> WeekPlan:
    """Build a draft plan for a week and save it under the week's id.

    Meals in ``keep`` stay as they are; the other meals are chosen around them.
    """
    settings = repo.get_settings(household_id)
    kept = dict(keep or {})
    slots = [slot for slot in settings.cook_slots() if slot not in kept]
    kept_recipes = [meal.recipe for meal in kept.values()]
    kept_ids = {recipe.id for recipe in kept_recipes}
    notes: list[str] = []

    # Only main dishes are planned; desserts, breakfasts and the rest stay in the library.
    library = [r for r in repo.list_recipes(household_id) if r.category == "main"]
    problem = check_diets(repo, ai, household_id, library, settings.diets)
    if problem:
        notes.append(problem)
    recipes = [r for r in library if fits(settings.diets, r) and r.id not in kept_ids]
    recent = recent_recipe_ids(repo, household_id, week_id, settings)
    rules = _adjusted_rules(settings.rules, kept_recipes)
    open_settings = settings.model_copy(update={"rules": rules})

    picks = planner.pick_recipes(recipes, len(slots), rules, recent, settings.max_repeat_ratio, rng)
    new_ids: set[str] = set()
    web = web or Web()
    deadline = time.monotonic() + web.search_seconds

    statuses = planner.rule_status(picks, len(slots), rules, recent, settings.max_repeat_ratio)
    if ai is not None and (len(picks) < len(slots) or not all(s.ok for s in statuses)):
        try:
            picks, new_ids = _fill_with_suggestions(
                ai,
                web or Web(),
                deadline,
                picks,
                len(slots),
                open_settings,
                [recipe.title for recipe in library],
            )
        except AIError as error:
            notes.append(f"Could not look for new recipes: {error}")

    if ai is not None and len(picks) < len(slots) and time.monotonic() >= deadline:
        notes.append(
            f"The web search ran out of time ({web.search_seconds:g} seconds) before finding "
            "enough recipes, so some meals are empty. Choose them yourself, or generate again."
        )
    total = len(slots) + len(kept)
    filled = len(picks) + len(kept)
    if filled < total:
        notes.append(
            f"Only {filled} of {total} meals could be filled without breaking your "
            "rules. Add more recipes to your library."
        )

    meals = dict(kept)
    for slot, recipe in zip(slots, picks, strict=False):
        meals[slot] = PlanMeal(
            recipe=recipe, portions=settings.slots[slot].portions, is_new=recipe.id in new_ids
        )
    plan = WeekPlan(
        week_id=week_id,
        meals={slot: meals[slot] for slot in SLOT_KEYS if slot in meals},
        notes=notes,
        diets=settings.diets,
    )
    repo.save_plan(household_id, plan)
    return plan


def apply_diets(
    repo: Repo,
    ai: RecipeAI | None,
    household_id: str,
    week_id: str,
    rng: random.Random,
    web: Web | None = None,
) -> WeekPlan:
    """Bring an existing plan in line with the current diets.

    Meals that fit stay, with their portions; the others are replaced, from the
    library first and then from the web. The plan goes back to draft.
    """
    plan = repo.get_plan(household_id, week_id)
    if plan is None:
        raise NotFound("There is no plan for this week yet")
    settings = repo.get_settings(household_id)
    planned = [meal.recipe for meal in plan.meals.values()]
    check_diets(repo, ai, household_id, planned, settings.diets)
    keep = {
        slot: meal
        for slot, meal in plan.meals.items()
        if fits(settings.diets, meal.recipe) and slot in settings.cook_slots()
    }
    updated = generate_plan(repo, ai, household_id, week_id, rng, web, keep=keep)
    if plan.status == "approved":
        updated.notes.append("Approve the plan again to update your grocery list.")
        repo.save_plan(household_id, updated)
    return updated


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
    options = planner.alternatives(
        planned,
        slot,
        repo.list_recipes(household_id),  # the whole library: choosing a meal is always free
        slot_count,
        settings.rules,
        recent_recipe_ids(repo, household_id, week_id, settings),
        settings.max_repeat_ratio,
    )
    for option in options:
        option.fits_diets = fits(settings.diets, option.recipe)
    # Best suggestions first; everything else follows, flagged but still selectable:
    # main dishes before other types, then fitting the diets, then not already this
    # week, then keeping the rules (the order within each step stays as ranked).
    options.sort(
        key=lambda option: (
            option.recipe.category != "main",
            not option.fits_diets,
            option.already_planned,
            not option.keeps_rules,
        )
    )
    return options


def move_meal(
    repo: Repo, household_id: str, week_id: str, from_slot: str, to_slot: str
) -> WeekPlan:
    """Drag and drop: swap the meals of two slots, or move a meal to an empty one.

    Recipes trade places but each slot keeps its own portions, since portions are
    about who eats that meal (a dinner that also covers tomorrow's lunch is bigger).
    """
    for slot in (from_slot, to_slot):
        if slot not in SLOT_KEYS:
            raise NotFound(f"Unknown meal slot: {slot}")
    plan = repo.get_plan(household_id, week_id)
    if plan is None or from_slot not in plan.meals:
        raise NotFound("There is no meal to move there")
    if from_slot == to_slot:
        return plan
    settings = repo.get_settings(household_id)
    moving = plan.meals.pop(from_slot)
    other = plan.meals.pop(to_slot, None)
    target_portions = other.portions if other else settings.slots[to_slot].portions
    plan.meals[to_slot] = moving.model_copy(update={"portions": target_portions})
    if other is not None:
        plan.meals[from_slot] = other.model_copy(update={"portions": moving.portions})
    plan.meals = {slot: plan.meals[slot] for slot in SLOT_KEYS if slot in plan.meals}
    # The grocery list no longer matches, so approval is needed again.
    plan.status = "draft"
    plan.approved_at = None
    repo.save_plan(household_id, plan)
    return plan


def swap_meal(
    repo: Repo, household_id: str, week_id: str, slot: str, rng: random.Random
) -> WeekPlan:
    """One-tap swap: the app picks for you, so it picks sensibly.

    A main dish that fits the diets and is not already planned this week, keeping the
    rules if possible, chosen among the best few. To choose freely, pick from the list.
    """
    options = [
        option
        for option in meal_alternatives(repo, household_id, week_id, slot)
        if option.recipe.category == "main" and option.fits_diets and not option.already_planned
    ]
    if not options:
        raise NotFound("No other recipe in your library fits this meal. Add more recipes.")
    keeping = [option for option in options if option.keeps_rules] or options
    # Options come best first (rules kept, not eaten recently, cooked longest ago).
    choice = rng.choice(keeping[:5])
    return set_meal(repo, household_id, week_id, slot, choice.recipe.id, None)


def approve_plan(
    repo: Repo,
    household_id: str,
    week_id: str,
    web: Web | None = None,
    ai: RecipeAI | None = None,
) -> tuple[WeekPlan, int]:
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
        stored = repo.get_recipe(household_id, meal.recipe.id)
        if stored is None:
            # A new idea from the web joins the library, with our own copy of its photo.
            stored = meal.recipe
            if web is not None:
                keep_own_copy(web.images, web.read_image, household_id, stored)
            fill_nutrition(ai, stored)
            meal.recipe = stored.model_copy(deep=True)
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
    web: Web | None = None,
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
            generate_plan(repo, ai, household.id, target, rng or random.Random(), web)
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


def fill_nutrition(ai: RecipeAI | None, recipe: Recipe, previous: Recipe | None = None) -> None:
    """Give every ingredient a nutrition estimate and work out the recipe's macros.

    Estimates sent by the app are not trusted: they are kept from the saved recipe
    for ingredients whose name and unit did not change, and asked of the AI for new
    or renamed ones. Amounts can change freely, since estimates are per unit.
    A failed estimate never blocks saving; the macros then list what is missing.
    """
    known = {}
    for ingredient in previous.ingredients if previous else []:
        if ingredient.nutrition is not None:
            known[(ingredient.name, ingredient.unit)] = ingredient.nutrition
    for ingredient in recipe.ingredients:
        ingredient.nutrition = known.get((ingredient.name, ingredient.unit))

    unknown = [i for i in recipe.ingredients if i.nutrition is None and i.quantity is not None]
    if ai is not None and unknown:
        try:
            for ingredient, estimate in zip(unknown, ai.estimate_nutrition(unknown), strict=False):
                ingredient.nutrition = estimate
        except AIError as error:
            log.warning("Could not estimate nutrition for %r: %s", recipe.title, error)
    recipe.refresh_macros()


def recalculate_macros(repo: Repo, ai: RecipeAI, household_id: str, recipe_id: str) -> Recipe:
    """Estimate every ingredient again, for example after changing several of them."""
    recipe = repo.get_recipe(household_id, recipe_id)
    if recipe is None:
        raise NotFound("Recipe not found")
    fill_nutrition(ai, recipe)
    repo.save_recipe(household_id, recipe)
    return recipe
