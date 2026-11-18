"""Use cases: each function loads data, calls the pure core logic and saves the result."""

import logging
import random
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from datetime import time as dt_time
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from app import i18n, standards
from app.ai.base import AIError, RecipeAI
from app.core import balance, planner
from app.core import pantry as pantry_logic
from app.core import taste as taste_logic
from app.core.allergens import found_in, missing_equipment
from app.core.diet import (
    criteria,
    cuisine_hint,
    fits,
    is_known,
    meaning,
    needs_verdict,
    search_phrase,
)
from app.core.grocery import build_grocery_lines, load_packs, scale_ingredients
from app.core.ingredients import guess_aisle, normalize_name
from app.core.weeks import DAYS, SLOT_KEYS, next_week_id, previous_week_ids
from app.core.weeks import week_id as week_id_of
from app.images import ImageStore, keep_own_copy
from app.links import LinkContent, read_image, read_link
from app.models import (
    Alternative,
    GroceryItem,
    PantryDraft,
    PantryItem,
    PlanMeal,
    PlanOut,
    Recipe,
    RecipeDraft,
    Rule,
    Settings,
    TasteProfile,
    WeekBalance,
    WeekPlan,
    now,
)
from app.notify import Notifier
from app.repo.base import Repo
from app.tasks import JobQueue, PlanJob, QueueError
from app.web_recipes import find_web_recipes

log = logging.getLogger(__name__)


class NotFound(Exception):
    pass


# How long plan generation may search the web, unless the server is configured otherwise.
WEB_SEARCH_SECONDS = 50
# How many recipes are judged against the diets in one AI call.
DIET_CHECK_BATCH = 40
DIET_FIT_VERSION = 2  # diet verdicts judged on meanings, not bare words


@dataclass
class Web:
    """How the app reaches the internet: reading recipe pages and keeping copies of photos."""

    read_link: Callable[[str], LinkContent] = read_link
    read_image: Callable[[str], tuple[bytes, str]] = read_image
    images: ImageStore | None = field(default=None)
    search_seconds: float = field(default_factory=lambda: WEB_SEARCH_SECONDS)


def recent_weeks(repo: Repo, household_id: str, week_id: str) -> planner.Recent:
    """Recipes planned in the two weeks before ``week_id``: last week's never come back,
    and at most half of the week may come from the week before that."""

    def ids(week: str) -> frozenset[str]:
        plan = repo.get_plan(household_id, week)
        return frozenset(meal.recipe.id for meal in plan.meals.values()) if plan else frozenset()

    last, before = previous_week_ids(week_id, 2)
    return planner.Recent(last_week=ids(last), two_weeks_ago=ids(before))


def plan_out(repo: Repo, household_id: str, plan: WeekPlan) -> PlanOut:
    settings = repo.get_settings(household_id)
    cook_slots = settings.cook_slots()
    slot_count = max(len(cook_slots), len(plan.meals))
    statuses = planner.rule_status(
        [meal.recipe for meal in plan.meals.values()],
        slot_count,
        settings.rules,
        recent_weeks(repo, household_id, plan.week_id),
    )
    open_slots = [slot for slot in cook_slots if slot not in plan.meals]
    # The variety rule (the last status) is applied automatically, not shown as a chip:
    # a meal chosen by hand is never marked for it.
    out = PlanOut(**plan.model_dump(), rule_status=statuses[:-1], open_slots=open_slots)

    # Meals are copies of recipes taken when planned. If macros were worked out since,
    # show them, as long as the ingredients are still the same.
    library = {recipe.id: recipe for recipe in repo.list_recipes(household_id)}
    for meal in out.meals.values():
        saved = library.get(meal.recipe.id)
        same = saved is not None and [(i.name, i.unit, i.quantity) for i in saved.ingredients] == [
            (i.name, i.unit, i.quantity) for i in meal.recipe.ingredients
        ]
        if saved is not None and saved.language != meal.recipe.language:
            # The library has it in the household's language now; the meal shows that.
            meal.recipe.title, meal.recipe.steps = saved.title, saved.steps
            meal.recipe.language = saved.language
            labels = {i.name: i.label for i in saved.ingredients}
            for ingredient in meal.recipe.ingredients:
                ingredient.label = labels.get(ingredient.name, "")
        if same and meal.recipe.macros is None and saved.macros is not None:
            meal.recipe.ingredients = saved.ingredients
            meal.recipe.refresh_macros()

    pantry = repo.get_pantry(household_id)
    for meal in out.meals.values():
        if not meal.consumed:
            meal.uses_pantry = pantry_logic.used_by(pantry, meal.recipe.ingredients)
    _explain(repo, household_id, out, settings)

    out.balance = WeekBalance.model_validate(
        balance.week_balance(
            [(slot, meal.recipe) for slot, meal in out.meals.items()], standards.load()
        )
    )
    _in_language(out, settings)
    return out


def _in_language(out: PlanOut, settings: Settings) -> None:
    """Rule chips and balance checks in the household's language."""
    lang = settings.language
    for status, rule in zip(out.rule_status, settings.rules, strict=False):
        key = "at_least" if rule.kind == "min" else "at_most"
        status.label = i18n.t(lang, key, count=rule.count, what=i18n.word(lang, rule.tag))
    if lang == "en" or out.balance is None:
        return
    for check in out.balance.checks:
        if f"check_{check.key}" in i18n._MESSAGES:
            check.label = i18n.t(lang, f"check_{check.key}")
        if match := re.fullmatch(r"(\d+) of (\d+) days", check.detail):
            check.detail = i18n.t(lang, "days_of", value=match[1], days=match[2])
        elif match := re.fullmatch(r"(\d+) (meals|kinds)", check.detail):
            check.detail = i18n.t(lang, f"n_{match[2]}", value=match[1])


def _fill_with_suggestions(
    ai: RecipeAI,
    web: Web,
    deadline: float,
    picks: list[Recipe],
    slot_count: int,
    settings: Settings,
    library_titles: list[str],
    wishes: list[str] | None = None,
    max_minutes: int | None = None,
) -> tuple[list[Recipe], set[str]]:
    """Use web recipes to cover what the library could not: unmet rules, then empty slots.

    ``wishes`` are the household's leanings and time limits, added to the search;
    recipes longer than ``max_minutes`` fit no meal and are left out."""
    picks = list(picks)
    new_ids: set[str] = set()
    min_rules = [rule for rule in settings.rules if rule.kind == "min"]
    max_rules = [rule for rule in settings.rules if rule.kind == "max"]
    # settings.rules here already holds the balanced-week rules plus the household's own.
    titles = list(library_titles)

    def count(rule: Rule) -> int:
        return sum(1 for recipe in picks if planner.matches(recipe, rule))

    def allowed(recipe: Recipe) -> bool:
        return all(
            not planner.matches(recipe, rule) or count(rule) < rule.count for rule in max_rules
        )

    # What the web has to provide: recipes for each "at least" rule that is short,
    # and enough recipes overall to fill the empty meals. One search covers it all.
    needs = {rule.tag: rule.count - count(rule) for rule in min_rules}
    needs = {tag: missing for tag, missing in needs.items() if missing > 0}
    gaps = max(0, slot_count - len(picks))
    total = max(gaps, sum(needs.values()))
    if total == 0:
        return picks, new_ids
    query = search_phrase(settings.planning_needs(), needs, wishes, settings.diet_meanings)
    # Ask for a couple more than needed, since some pages will not work.
    # Ask for a few more than needed: some pages will not work, and those with a photo
    # are preferred.
    drafts = find_web_recipes(ai, web.read_link, query, total + 4, titles, deadline)
    found = []
    for draft in drafts:
        # Found by a search for these diets, so they count as fitting them.
        recipe = Recipe(**draft.model_dump(), diet_fit={d: True for d in settings.diets})
        too_long = max_minutes is not None and (recipe.prep_minutes or 0) > max_minutes
        if recipe.category == "main" and suits(settings, recipe) and not too_long:
            found.append(recipe)

    def take(recipe: Recipe) -> None:
        found.remove(recipe)
        picks.append(recipe)
        new_ids.add(recipe.id)

    def best(recipe: Recipe) -> tuple[bool, int]:
        # A recipe with a photo first, then the least-used protein this week.
        return (not recipe.image_url, protein_use(recipe))

    def protein_use(recipe: Recipe) -> int:
        return sum(1 for p in picks if p.protein == recipe.protein)

    def meet_min_rules(pool: list[Recipe]) -> None:
        # For each short "at least" rule, take matching recipes, least-used protein first.
        for rule in min_rules:
            while count(rule) < rule.count:
                options = [r for r in pool if planner.matches(r, rule) and allowed(r)]
                if not options:
                    break
                if len(picks) >= slot_count:
                    # No free slot: replace a meal that no "at least" rule depends on.
                    spare = next(
                        (
                            index
                            for index in range(len(picks) - 1, -1, -1)
                            if not any(planner.matches(picks[index], r) for r in min_rules)
                        ),
                        None,
                    )
                    if spare is None:
                        break
                    picks.pop(spare)
                recipe = min(options, key=best)
                pool.remove(recipe)
                picks.append(recipe)
                new_ids.add(recipe.id)

    meet_min_rules(found)

    # Fill the rest with variety: each time, the protein used least so far this week.
    while len(picks) < slot_count:
        candidates = [recipe for recipe in found if allowed(recipe)]
        if not candidates:
            break
        take(min(candidates, key=best))

    # If some web pages failed to load or did not cover every rule/slot, fill the remaining
    # gaps directly so a single Generate always produces a complete week.
    remaining_needs = {rule.tag: rule.count - count(rule) for rule in min_rules}
    remaining_needs = {tag: missing for tag, missing in remaining_needs.items() if missing > 0}
    remaining_gaps = max(0, slot_count - len(picks))
    fallback_fn = getattr(ai, "generate_fallback_recipes", None)
    if (
        (remaining_needs or remaining_gaps > 0)
        and callable(fallback_fn)
        and time.monotonic() < deadline
    ):
        forbidden = [rule.tag for rule in max_rules if count(rule) >= rule.count]
        used_titles = [*titles, *(r.title for r in picks)]
        try:
            extra_drafts = fallback_fn(
                remaining_needs,
                remaining_gaps,
                forbidden,
                used_titles,
                "; ".join(
                    part
                    for part in (
                        criteria(settings.planning_needs(), settings.diet_meanings),
                        cuisine_hint(settings.planning_needs(), settings.diet_meanings),
                        *(wishes or []),
                    )
                    if part
                ),
            )
            # Written for these diets, so they count as fitting them.
            extra_found = [
                recipe
                for draft in extra_drafts
                if draft.category == "main"
                and suits(
                    settings,
                    recipe := Recipe(
                        **draft.model_dump(), diet_fit={d: True for d in settings.diets}
                    ),
                )
            ]
        except AIError as error:
            log.warning("Fallback recipe generation failed: %s", error)
            extra_found = []

        meet_min_rules(extra_found)

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
    repo: Repo,
    ai: RecipeAI | None,
    household_id: str,
    recipes: list[Recipe],
    diets: list[str],
    lang: str = "en",
    learned: dict | None = None,
) -> str | None:
    """Make sure each recipe has been judged against each diet. Returns a problem, if any.

    The AI judges against what each diet means ("low in carbohydrates: no pasta, rice…"),
    not the bare word. Verdicts are stored on the recipe under the word, so each recipe is
    only judged once per diet. Recipes that could not be judged are treated as fitting.
    """
    for recipe in recipes:
        if recipe.diet_fit_version < DIET_FIT_VERSION:
            # Judged on the bare word before: keep allergy checks, judge diets again.
            recipe.diet_fit = {k: v for k, v in recipe.diet_fit.items() if k.startswith("free of ")}
            recipe.diet_fit_version = DIET_FIT_VERSION
            repo.save_recipe(household_id, recipe)
    pending = [recipe for recipe in recipes if needs_verdict(diets, recipe, learned)]
    if not pending or ai is None:
        return None
    words = [w for w in needs_verdict(diets, Recipe(title="-"), learned)]
    described = {
        (w if w.startswith("free of ") else meaning(w, learned).describe): w for w in words
    }
    try:
        for start in range(0, len(pending), DIET_CHECK_BATCH):
            batch = pending[start : start + DIET_CHECK_BATCH]
            verdicts = ai.check_diets(
                [(r.title, [i.name for i in r.ingredients]) for r in batch], list(described)
            )
            for recipe, verdict in zip(batch, verdicts, strict=False):
                if verdict:
                    by_word = {described.get(k, k): v for k, v in verdict.items()}
                    # Only what this recipe had not been judged on yet.
                    new = {k: v for k, v in by_word.items() if k not in recipe.diet_fit}
                    recipe.diet_fit = {**recipe.diet_fit, **new}
                    repo.save_recipe(household_id, recipe)
    except AIError as error:
        log.warning("Could not check recipes against diets: %s", error)
        return i18n.t(lang, "diet_check_failed", error=error)
    return None


def warnings_for(settings: Settings, recipe: Recipe) -> list[str]:
    """Why a recipe should not be planned for this household, in plain words."""
    lang = settings.language
    found = found_in(recipe, settings.allergies, settings.avoid)
    missing = missing_equipment(recipe, settings.equipment)
    return [i18n.t(lang, "contains", food=i18n.allergen(lang, food)) for food in found] + [
        i18n.t(lang, "needs", item=i18n.equipment(lang, item)) for item in missing
    ]


def suits(settings: Settings, recipe: Recipe) -> bool:
    """Whether the planner may pick a recipe: fits the diets, no allergy, no avoided
    food, and nothing needed that the kitchen lacks. Choosing by hand is still free."""
    return fits(settings.planning_needs(), recipe, settings.diet_meanings) and not warnings_for(
        settings, recipe
    )


def all_rules(settings: Settings, slot_count: int) -> list[Rule]:
    """The balanced-week rules from the standards, then the household's own extras."""
    return [*balance.planner_rules(standards.load(), slot_count), *settings.rules]


def _adjusted_rules(rules: list[Rule], kept: list[Recipe]) -> list[Rule]:
    """The rules still to meet once some meals are already decided."""
    adjusted = []
    for rule in rules:
        already = sum(1 for recipe in kept if planner.matches(recipe, rule))
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
    # Meals moved here by "I'm not cooking this" always stay.
    existing = repo.get_plan(household_id, week_id)
    carried = {
        slot: meal
        for slot, meal in (existing.meals if existing else {}).items()
        if meal.carried_from
    }
    kept = {**carried, **(keep or {})}
    slots = [slot for slot in settings.cook_slots() if slot not in kept]
    kept_recipes = [meal.recipe for meal in kept.values()]
    kept_ids = {recipe.id for recipe in kept_recipes}
    notes: list[str] = []

    # Only main dishes are planned; desserts, breakfasts and the rest stay in the library.
    library = [
        r
        for r in localize_library(repo, ai, household_id, repo.list_recipes(household_id))
        if r.category == "main"
    ]
    lang = settings.language
    problem = check_diets(
        repo,
        ai,
        household_id,
        library,
        settings.planning_needs(),
        settings.language,
        settings.diet_meanings,
    )
    if problem:
        notes.append(problem)
    recipes = [
        r for r in library if suits(settings, r) and not r.not_for_us and r.id not in kept_ids
    ]
    recent = recent_weeks(repo, household_id, week_id)
    rules = _adjusted_rules(all_rules(settings, len(settings.cook_slots())), kept_recipes)
    open_settings = settings.model_copy(update={"rules": rules})

    today = local_today(settings)
    pantry = settle_pantry(repo, household_id, today)
    # The household's taste and the food at home decide between recipes the rules allow.
    taste = repo.get_taste(household_id)
    prefer = {
        r.id: pantry_logic.preference(pantry, r.ingredients, today)
        + taste_logic.score(taste, r, today)
        for r in recipes
    }
    limits = [settings.cook_limit(slot) for slot in slots]
    picks = planner.pick_recipes(recipes, len(slots), rules, recent, rng, prefer, limits)
    new_ids: set[str] = set()
    web = web or Web()
    deadline = time.monotonic() + web.search_seconds

    statuses = planner.rule_status(picks, len(slots), rules, recent)
    if ai is not None and (len(picks) < len(slots) or not all(s.ok for s in statuses)):
        try:
            picks, new_ids = _fill_with_suggestions(
                ai,
                web or Web(),
                deadline,
                picks,
                len(slots),
                open_settings,
                [recipe.title for recipe in library] + taste.blocked,
                search_wishes(settings, taste, today),
                max((float("inf") if limit is None else limit) for limit in limits)
                if limits and None not in limits
                else None,
            )
        except AIError as error:
            notes.append(i18n.t(lang, "search_failed", error=error))

    if ai is not None and len(picks) < len(slots) and time.monotonic() >= deadline:
        notes.append(i18n.t(lang, "search_timeout", seconds=web.search_seconds))
    total = len(slots) + len(kept)
    filled = len(picks) + len(kept)
    if filled < total:
        if not library:
            notes.append(i18n.t(lang, "empty_library", filled=filled, total=total))
        else:
            notes.append(i18n.t(lang, "not_filled", filled=filled, total=total))

    # New ideas from the web are written in English: show them in the household's language.
    fresh = [i for i, recipe in enumerate(picks) if recipe.id in new_ids]
    for i, recipe in zip(fresh, in_language(ai, [picks[i] for i in fresh], lang), strict=True):
        picks[i] = recipe
    meals = dict(kept)
    for slot, recipe in planner.assign_slots(picks, slots, limits, rng).items():
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
    check_diets(
        repo,
        ai,
        household_id,
        planned,
        settings.planning_needs(),
        settings.language,
        settings.diet_meanings,
    )
    keep = {
        slot: meal
        for slot, meal in plan.meals.items()
        if suits(settings, meal.recipe) and slot in settings.cook_slots()
    }
    updated = generate_plan(repo, ai, household_id, week_id, rng, web, keep=keep)
    if plan.status == "approved":
        updated.notes.append(i18n.t(settings.language, "approve_again"))
        repo.save_plan(household_id, updated)
    return updated


def set_meal(
    repo: Repo,
    household_id: str,
    week_id: str,
    slot: str,
    recipe_id: str | None,
    portions: int | None,
    chosen: bool = True,
) -> WeekPlan:
    """Put a recipe in a slot, change its portions, or clear the slot.

    A recipe put in by hand (``chosen``) counts towards the household's taste, and the
    one it replaced against it."""
    if slot not in SLOT_KEYS:
        raise NotFound(f"Unknown meal slot: {slot}")
    plan = repo.get_plan(household_id, week_id) or WeekPlan(week_id=week_id)
    existing = plan.meals.get(slot)
    if recipe_id is not None and (existing is None or existing.recipe.id != recipe_id):
        _learn_choice(repo, household_id, existing.recipe if existing else None, recipe_id, chosen)

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
        all_rules(settings, slot_count),
        recent_weeks(repo, household_id, week_id),
    )
    for option in options:
        option.fits_diets = fits(settings.diets, option.recipe, settings.diet_meanings)
        option.not_for_us = option.recipe.not_for_us
        option.warnings = warnings_for(settings, option.recipe)
    # Best suggestions first; everything else follows, flagged but still selectable:
    # main dishes before other types, then fitting the diets, then not already this
    # week, then keeping the rules (the order within each step stays as ranked).
    # Within each step, what the household likes most comes first.
    taste = repo.get_taste(household_id)
    today = local_today(settings)
    liked = {o.recipe.id: taste_logic.score(taste, o.recipe, today) for o in options}
    options.sort(
        key=lambda option: (
            option.recipe.category != "main",
            not option.fits_diets,
            bool(option.warnings),
            option.not_for_us,
            option.already_planned,
            option.last_week,
            not option.keeps_rules,
            -round(liked[option.recipe.id] * 2) / 2,
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
        if option.recipe.category == "main"
        and not option.last_week
        and not option.not_for_us
        and option.fits_diets
        and not option.warnings
        and not option.already_planned
    ]
    if not options:
        raise NotFound("No other recipe in your library fits this meal. Add more recipes.")
    keeping = [option for option in options if option.keeps_rules] or options
    # Options come best first (rules kept, not eaten recently, cooked longest ago); among
    # the best few, the one the household likes most.
    today = local_today(repo.get_settings(household_id))
    taste = repo.get_taste(household_id)
    top = keeping[:5]
    rng.shuffle(top)
    choice = max(top, key=lambda option: taste_logic.score(taste, option.recipe, today))
    return set_meal(repo, household_id, week_id, slot, choice.recipe.id, None, chosen=False)


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
    # Meals already cooked need nothing more; the pantry covers what is at home.
    to_buy = [meal for meal in ordered if not meal.consumed]
    pantry = settle_pantry(repo, household_id, local_today(settings))
    lines = build_grocery_lines(
        [(meal.recipe, meal.portions) for meal in to_buy],
        settings.staples,
        pantry,
        load_packs(),
        settings.language,
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
            needed=line.needed,
            pack=line.pack,
            note=line.note,
            label=line.label,
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

    if plan.status != "approved":
        # The meals that made it to the grocery list: a small "this works".
        taste = repo.get_taste(household_id)
        today = local_today(settings)
        for meal in ordered:
            taste = taste_logic.nudge(taste, meal.recipe, taste_logic.KEPT, today)
        repo.save_taste(household_id, taste)
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


def plan_is_due(settings: Settings, local_now: datetime) -> bool:
    """Whether this week's chosen plan moment (day and hour) has come, in local time."""
    monday = local_now.date() - timedelta(days=local_now.weekday())
    moment = datetime.combine(
        monday + timedelta(days=DAYS.index(settings.plan_day)),
        dt_time(settings.plan_hour),
        tzinfo=local_now.tzinfo,
    )
    return local_now >= moment


def run_weekly_job(
    repo: Repo,
    ai: RecipeAI | None,
    notifier: Notifier,
    app_url: str,
    today: date | None = None,
    rng: random.Random | None = None,
    web: Web | None = None,
    now: datetime | None = None,
    queue: JobQueue | None = None,
) -> dict[str, int]:
    """Draft next week's plan for every household whose chosen day and hour have come.

    The scheduler calls this every hour. A household that already has a plan for next
    week is skipped, so running the job again does not overwrite changes or send a
    second notification; a missed hour is caught up by the next run.
    ``today`` (tests) means the end of that day.
    """
    summary = {"generated": 0, "skipped": 0, "waiting": 0, "failed": 0}
    for household in repo.list_households():
        try:
            settings = repo.get_settings(household.id)
            zone = ZoneInfo(settings.timezone)
            if now is not None:
                local_now = now.astimezone(zone)
            elif today is not None:
                local_now = datetime.combine(today, dt_time(23, 59), tzinfo=zone)
            else:
                local_now = datetime.now(zone)
            if not plan_is_due(settings, local_now):
                summary["waiting"] += 1
                continue
            target = next_week_id(local_now.date())
            existing = repo.get_plan(household.id, target)
            if existing is not None and (not existing.pending or is_generating(existing)):
                summary["skipped"] += 1
                continue
            job = PlanJob(household_id=household.id, week_id=target, notify=True)
            if queue is None:
                mark_generating(repo, household.id, target)
                run_plan_job(repo, ai, web, notifier, app_url, job, rng)
            else:
                start_plan_job(repo, queue, job)
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


# Pantry ---------------------------------------------------------------------------------


def local_today(settings: Settings) -> date:
    return datetime.now(ZoneInfo(settings.timezone)).date()


def _meal_date(week_id: str, slot: str) -> date:
    return date.fromisoformat(week_id) + timedelta(days=DAYS.index(slot.split("_")[0]))


def _bought_for(lang: str, week_id: str, slot: str, recipe: Recipe) -> str:
    day = i18n.day_name(lang, _meal_date(week_id, slot).weekday())
    return i18n.t(lang, "bought_for", day=day, title=recipe.title.lower())


def settle_pantry(repo: Repo, household_id: str, today: date | None = None) -> list[PantryItem]:
    """Take the food of every meal whose day has passed out of the pantry, once.

    Only approved plans count: that is when the food was bought. A meal marked
    "I'm not cooking this" has already left the plan, so it is never taken.
    """
    settings = repo.get_settings(household_id)
    today = today or local_today(settings)
    pantry = repo.get_pantry(household_id)
    changed = False
    this_week = week_id_of(today)
    for week in (*previous_week_ids(this_week, 1), this_week):
        plan = repo.get_plan(household_id, week)
        if plan is None or plan.status != "approved":
            continue
        cooked = [
            meal
            for slot, meal in plan.meals.items()
            if not meal.consumed and _meal_date(week, slot) < today
        ]
        for meal in cooked:
            pantry = pantry_logic.take(pantry, scale_ingredients(meal.recipe, meal.portions))
            meal.consumed = True
        if cooked:
            repo.save_plan(household_id, plan)
            changed = True
    if changed:
        repo.save_pantry(household_id, pantry)
    return pantry


def list_pantry(repo: Repo, household_id: str) -> list[PantryItem]:
    """The pantry, food closest to its use-by first."""
    items = settle_pantry(repo, household_id)
    return sorted(items, key=lambda i: (i.use_by is None, i.use_by or date.max, i.name))


def add_to_pantry(
    repo: Repo, household_id: str, drafts: list[PantryDraft], source: str = "manual"
) -> list[PantryItem]:
    today = local_today(repo.get_settings(household_id))
    new = [
        PantryItem(
            **draft.model_dump(),
            use_by=pantry_logic.use_by(draft.aisle, today),
            source=source,  # type: ignore[arg-type]
        )
        for draft in drafts
    ]
    items = pantry_logic.add(settle_pantry(repo, household_id, today), new)
    repo.save_pantry(household_id, items)
    return list_pantry(repo, household_id)


def pantry_from_text(
    repo: Repo, household_id: str, text: str, ai: RecipeAI | None = None
) -> list[PantryItem]:
    """Typed food such as "2 eggs, half a courgette" is understood without AI. In
    Portuguese, the AI only adds the English names underneath."""
    lang = repo.get_settings(household_id).language
    drafts = [
        PantryDraft(name=name, label=name if lang != "en" else "", quantity=quantity, unit=unit)
        for name, quantity, unit in pantry_logic.parse_text(text)
    ]
    return add_to_pantry(repo, household_id, pantry_names(ai, drafts, lang))


def pantry_names(ai: RecipeAI | None, drafts: list[PantryDraft], lang: str) -> list[PantryDraft]:
    """Food shown in Portuguese: its English name, which matching relies on, from its label."""
    labelled = [d for d in drafts if d.label]
    if lang == "en" or not labelled or ai is None:
        return drafts
    try:
        names = ai.translate_names([d.label for d in labelled], "en")
    except (AIError, AttributeError) as error:
        log.warning("Could not translate food names: %s", error)
        return drafts
    out = []
    english = iter(names)
    for draft in drafts:
        if draft.label:
            name = next(english, draft.name)
            draft = PantryDraft(**{**draft.model_dump(), "name": name, "aisle": "other"})
        out.append(draft)
    return out


def pantry_labels(ai: RecipeAI | None, drafts: list[PantryDraft], lang: str) -> list[PantryDraft]:
    """Food read in English by the AI, labelled in the household's language for checking."""
    if lang == "en" or not drafts or ai is None:
        return drafts
    try:
        labels = ai.translate_names([d.name for d in drafts], lang)
    except (AIError, AttributeError) as error:
        log.warning("Could not translate food names: %s", error)
        return drafts
    return [
        d.model_copy(update={"label": label[:120]})
        for d, label in zip(drafts, labels, strict=False)
    ]


def update_pantry_item(
    repo: Repo, household_id: str, item_id: str, draft: PantryDraft
) -> list[PantryItem]:
    items = settle_pantry(repo, household_id)
    item = next((i for i in items if i.id == item_id), None)
    if item is None:
        raise NotFound("That food is no longer in the pantry")
    item.name, item.label = draft.name, draft.label
    item.quantity, item.unit = draft.quantity, draft.unit
    repo.save_pantry(household_id, items)
    return list_pantry(repo, household_id)


def remove_pantry_item(repo: Repo, household_id: str, item_id: str) -> list[PantryItem]:
    items = [i for i in settle_pantry(repo, household_id) if i.id != item_id]
    repo.save_pantry(household_id, items)
    return list_pantry(repo, household_id)


def put_away(repo: Repo, household_id: str) -> int:
    """Shopping done: everything in the basket goes into the pantry, at the amount bought."""
    settings = repo.get_settings(household_id)
    today = local_today(settings)
    basket = [item for item in repo.list_groceries(household_id) if item.checked]
    if not basket:
        return 0
    new = [
        PantryItem(
            name=item.name,
            label=item.label,
            quantity=item.quantity,
            unit=item.unit,
            aisle=item.aisle,
            use_by=pantry_logic.use_by(item.aisle, today),
            source="shopping",
        )
        for item in basket
    ]
    pantry = pantry_logic.add(settle_pantry(repo, household_id, today), new)
    repo.save_pantry(household_id, pantry)
    repo.delete_groceries(household_id, [item.id for item in basket])
    for week in {item.week_id for item in basket if item.week_id}:
        plan = repo.get_plan(household_id, week)
        if plan is not None and not plan.put_away:
            plan.put_away = True
            repo.save_plan(household_id, plan)
    return len(basket)


class SkipResult(BaseModel):
    plan: WeekPlan  # this week, without the meal
    moved_to: str | None = None  # e.g. "2026-11-23 mon_dinner"
    # Next week is full: choose which of these meals to replace, then call again.
    choose_from: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def skip_meal(
    repo: Repo,
    household_id: str,
    week_id: str,
    slot: str,
    replace_slot: str | None = None,
    today: date | None = None,
) -> SkipResult:
    """ "I'm not cooking this": the food stays in the pantry, the recipe moves to next week.

    It can be said the day after too: food already taken out for that meal goes back.
    Next week, the recipe takes the first empty meal; when every meal is planned, the
    caller is asked which one to replace.
    """
    plan = repo.get_plan(household_id, week_id)
    if plan is None or slot not in plan.meals:
        raise NotFound("There is no meal there to skip")
    settings = repo.get_settings(household_id)
    today = today or local_today(settings)
    meal = plan.meals[slot]
    target_week = next_week_id(date.fromisoformat(week_id))
    target = repo.get_plan(household_id, target_week)
    cook_slots = settings.cook_slots() or ["mon_dinner"]

    if target is None:
        target = WeekPlan(week_id=target_week, pending=True, diets=settings.diets)
        place = cook_slots[0]
    else:
        free = [s for s in cook_slots if s not in target.meals]
        if free:
            place = free[0]
        elif replace_slot in target.meals:
            place = replace_slot
        else:
            return SkipResult(plan=plan, choose_from=list(target.meals))

    # The food: back into the pantry if it was taken out, or in for the first time if the
    # shopping was never put away. Not bought yet (no list made): nothing to keep.
    lang = settings.language
    label = _bought_for(lang, week_id, slot, meal.recipe)
    used = scale_ingredients(meal.recipe, meal.portions)
    pantry = settle_pantry(repo, household_id, today)
    if plan.status == "approved" and (meal.consumed or not plan.put_away):
        staples = set(settings.staples)
        # Bought around when the list was made, not today: fresh food is older than that.
        bought = plan.approved_at.date() if plan.approved_at else today
        food = [
            PantryItem(
                name=i.name,
                label=i.label,
                quantity=i.quantity,
                unit=i.unit,
                aisle=i.aisle,
                use_by=pantry_logic.use_by(i.aisle, bought),
                source="skipped",
                note=label,
            )
            for i in used
            if i.name not in staples
        ]
        pantry = pantry_logic.add(pantry, food)
    else:
        for item in pantry:
            if not item.note and any(pantry_logic.same_food(item.name, i.name) for i in used):
                item.note = label
    repo.save_pantry(household_id, pantry)

    # Fresh food that will not keep until the new day.
    cook_on = _meal_date(target_week, place)
    warnings = []
    for item in pantry:
        if (
            item.use_by
            and item.use_by < cook_on
            and any(pantry_logic.same_food(item.name, i.name) for i in used)
        ):
            food = item.label or item.name
            food = food[:1].upper() + food[1:] if lang == "pt" else food
            day = i18n.day_name(lang, cook_on.weekday())
            warnings.append(i18n.t(lang, "wont_keep", food=food, day=day))

    target.meals[place] = PlanMeal(
        recipe=meal.recipe, portions=meal.portions, carried_from=f"{week_id} {slot}"
    )
    if target.status == "approved":
        target.status = "draft"  # the grocery list needs updating
    repo.save_plan(household_id, target)
    del plan.meals[slot]
    repo.save_plan(household_id, plan)
    return SkipResult(plan=plan, moved_to=f"{target_week} {place}", warnings=warnings)


# Language ----------------------------------------------------------------------------------

TRANSLATE_BATCH = 8


def in_language(ai: RecipeAI | None, recipes: list[Recipe], lang: str) -> list[Recipe]:
    """Copies of the recipes with title, steps and ingredient labels in ``lang``.

    Ingredient names stay English underneath. Recipes already in that language, or that
    cannot be translated (no AI, or it failed), come back unchanged.
    """
    out = list(recipes)
    todo = [i for i, recipe in enumerate(out) if recipe.language != lang]
    if not todo or ai is None:
        return out
    for start in range(0, len(todo), TRANSLATE_BATCH):
        batch = todo[start : start + TRANSLATE_BATCH]
        try:
            results = ai.translate_recipes(
                [(out[i].title, out[i].steps, [g.name for g in out[i].ingredients]) for i in batch],
                lang,
            )
        except (AIError, AttributeError) as error:
            log.warning("Could not translate recipes: %s", error)
            return out
        for index, result in zip(batch, results, strict=False):
            if result is None:
                continue
            title, steps, labels = result
            recipe = out[index].model_copy(deep=True)
            recipe.title, recipe.steps, recipe.language = title[:200] or recipe.title, steps, lang
            for ingredient, label in zip(recipe.ingredients, labels, strict=False):
                ingredient.label = label[:120] if lang != "en" else ""
            out[index] = recipe
    return out


def localize_library(
    repo: Repo, ai: RecipeAI | None, household_id: str, recipes: list[Recipe]
) -> list[Recipe]:
    """Translate saved recipes into the household's language, once, and keep the result."""
    lang = repo.get_settings(household_id).language
    translated = in_language(ai, recipes, lang)
    for before, after in zip(recipes, translated, strict=True):
        if after is not before:
            repo.save_recipe(household_id, after)
    return translated


def english_names(ai: RecipeAI | None, recipe: Recipe) -> Recipe:
    """A recipe written in Portuguese: work out the English name under each ingredient label,
    which matching (allergies, pantry, packs) relies on."""
    labelled = [i for i in recipe.ingredients if i.label]
    if recipe.language == "en" or not labelled or ai is None:
        return recipe
    try:
        names = ai.translate_names([i.label for i in labelled], "en")
    except (AIError, AttributeError) as error:
        log.warning("Could not translate ingredient names: %s", error)
        return recipe
    recipe = recipe.model_copy(deep=True)
    for ingredient, name in zip([i for i in recipe.ingredients if i.label], names, strict=False):
        cleaned = normalize_name(name)
        if cleaned:
            ingredient.name = cleaned
            ingredient.aisle = guess_aisle(cleaned)  # type: ignore[assignment]
    recipe.refresh_macros()
    return recipe


def prepare_for_household(
    repo: Repo, ai: RecipeAI | None, household_id: str, recipe: Recipe
) -> Recipe:
    """Before saving: a recipe written in the household's Portuguese gets English names under
    its ingredients; one in another language is translated into the household's."""
    lang = repo.get_settings(household_id).language
    if recipe.language == lang:
        return english_names(ai, recipe) if lang != "en" else recipe
    return in_language(ai, [recipe], lang)[0]


def draft_for_household(
    repo: Repo, ai: RecipeAI | None, household_id: str, draft: RecipeDraft
) -> RecipeDraft:
    """An imported recipe, shown for checking in the household's language."""
    lang = repo.get_settings(household_id).language
    if draft.language == lang:
        return draft
    translated = in_language(ai, [Recipe(**draft.model_dump())], lang)[0]
    return RecipeDraft.model_validate(translated.model_dump(include=set(RecipeDraft.model_fields)))


# Plans made in the background -------------------------------------------------------------

STALE_AFTER = timedelta(minutes=15)


def is_generating(plan: WeekPlan) -> bool:
    """Being made right now. A job that never finished stops counting after a while."""
    return plan.generating_since is not None and now() - plan.generating_since < STALE_AFTER


def mark_generating(repo: Repo, household_id: str, week_id: str) -> WeekPlan:
    plan = repo.get_plan(household_id, week_id) or WeekPlan(week_id=week_id, pending=True)
    plan.generating_since, plan.generation_error = now(), None
    repo.save_plan(household_id, plan)
    return plan


def start_plan_job(repo: Repo, queue: JobQueue, job: PlanJob) -> WeekPlan:
    """Mark the week as being planned and queue the work. Already running: nothing new."""
    plan = repo.get_plan(job.household_id, job.week_id)
    if plan is not None and is_generating(plan):
        return plan
    if job.mode == "apply_diets" and plan is None:
        raise NotFound("There is no plan for this week yet")
    mark_generating(repo, job.household_id, job.week_id)
    try:
        queue.enqueue(job)
    except QueueError as error:
        failed = repo.get_plan(job.household_id, job.week_id)
        if failed is not None:
            failed.generating_since, failed.generation_error = None, str(error)
            repo.save_plan(job.household_id, failed)
        raise
    return repo.get_plan(job.household_id, job.week_id) or WeekPlan(week_id=job.week_id)


def run_plan_job(
    repo: Repo,
    ai: RecipeAI | None,
    web: Web | None,
    notifier: Notifier | None,
    app_url: str,
    job: PlanJob,
    rng: random.Random | None = None,
) -> None:
    """Make the plan. A failure is kept on the week so the app can say so and offer a retry."""
    rng = rng or random.Random()
    settings = repo.get_settings(job.household_id)
    try:
        if job.mode == "apply_diets":
            apply_diets(repo, ai, job.household_id, job.week_id, rng, web)
        else:
            generate_plan(repo, ai, job.household_id, job.week_id, rng, web)
    except Exception:
        log.exception("Plan job failed for household %s, week %s", job.household_id, job.week_id)
        plan = repo.get_plan(job.household_id, job.week_id)
        if plan is not None:
            plan.generating_since = None
            plan.generation_error = i18n.t(settings.language, "plan_failed")
            repo.save_plan(job.household_id, plan)
        return
    if job.notify and notifier is not None:
        household = next((h for h in repo.list_households() if h.id == job.household_id), None)
        if household is not None:
            invalid = notifier.send(
                household.device_tokens,
                i18n.t(settings.language, "plan_ready_title"),
                i18n.t(settings.language, "plan_ready_body"),
                f"{app_url}/plan/{job.week_id}" if app_url else "",
            )
            repo.remove_device_tokens(household.id, invalid)


# Taste --------------------------------------------------------------------------------------


def _learn_choice(
    repo: Repo, household_id: str, replaced: Recipe | None, recipe_id: str, chosen: bool
) -> None:
    """A meal changed: the one replaced counts against, the one chosen by hand for."""
    today = local_today(repo.get_settings(household_id))
    taste = repo.get_taste(household_id)
    if replaced is not None:
        taste = taste_logic.nudge(taste, replaced, taste_logic.SWAPPED_OUT, today)
    if chosen:
        recipe = repo.get_recipe(household_id, recipe_id)
        if recipe is not None:
            taste = taste_logic.nudge(taste, recipe, taste_logic.CHOSE, today)
    repo.save_taste(household_id, taste)


def search_wishes(settings: Settings, taste: TasteProfile, today: date) -> list[str]:
    """What to add to a web search for this household: time limits and leanings."""
    wishes = []
    if settings.cook_minutes_weekday:
        wishes.append(f"most ready in under {settings.cook_minutes_weekday} minutes")
    likes, dislikes = taste_logic.leanings(taste, today, 3)
    words = [key.split(":", 1)[1] for key in likes]
    if words:
        wishes.append("favouring " + ", ".join(words))
    avoid = [key.split(":", 1)[1] for key in dislikes]
    if avoid:
        wishes.append("not " + ", ".join(avoid))
    return wishes


def set_feedback(
    repo: Repo, household_id: str, recipe_id: str, liked: bool | None, not_for_us: bool | None
) -> Recipe:
    """♥ a recipe (or take it back), or mark it "Not for us": never suggested again."""
    recipe = repo.get_recipe(household_id, recipe_id)
    if recipe is None:
        raise NotFound("Recipe not found")
    today = local_today(repo.get_settings(household_id))
    taste = repo.get_taste(household_id)
    if liked is not None and liked != recipe.liked:
        recipe.liked = liked
        if liked:
            recipe.not_for_us = False
        taste = taste_logic.nudge(taste, recipe, 1.0 if liked else -1.0, today)
    if not_for_us is not None and not_for_us != recipe.not_for_us:
        recipe.not_for_us = not_for_us
        if not_for_us:
            recipe.liked = False
            taste = taste_logic.nudge(taste, recipe, taste_logic.NOT_FOR_US, today)
    repo.save_recipe(household_id, recipe)
    repo.save_taste(household_id, taste)
    return recipe


def not_for_us_meal(
    repo: Repo, household_id: str, week_id: str, slot: str, rng: random.Random
) -> WeekPlan:
    """ "Not for us" on a planned meal: never suggest it again, and swap it now."""
    plan = repo.get_plan(household_id, week_id)
    if plan is None or slot not in plan.meals:
        raise NotFound("There is no meal there")
    recipe = plan.meals[slot].recipe
    if repo.get_recipe(household_id, recipe.id) is not None:
        set_feedback(repo, household_id, recipe.id, None, True)
    else:
        # A new idea from the web that was never saved: remember its title instead.
        taste = repo.get_taste(household_id)
        today = local_today(repo.get_settings(household_id))
        taste = taste_logic.nudge(taste, recipe, taste_logic.NOT_FOR_US, today)
        if recipe.title not in taste.blocked:
            taste.blocked = [*taste.blocked, recipe.title][-200:]
        repo.save_taste(household_id, taste)
    try:
        return swap_meal(repo, household_id, week_id, slot, rng)
    except NotFound:
        return set_meal(repo, household_id, week_id, slot, None, None)


def taste_summary(repo: Repo, household_id: str) -> dict[str, list[str]]:
    """What the app has learned, as traits: {"likes": [...], "dislikes": [...]}."""
    today = local_today(repo.get_settings(household_id))
    likes, dislikes = taste_logic.leanings(repo.get_taste(household_id), today, 6)
    return {"likes": likes, "dislikes": dislikes}


def reset_taste(repo: Repo, household_id: str) -> None:
    repo.save_taste(household_id, TasteProfile())


def _explain(repo: Repo, household_id: str, out: PlanOut, settings: Settings) -> None:
    """ "Why this?" for each meal, in plain words: liked, a favourite kind, or new."""
    lang = settings.language
    today = local_today(settings)
    likes, _ = taste_logic.leanings(repo.get_taste(household_id), today, 6)
    library = {r.id: r for r in repo.list_recipes(household_id)}
    for meal in out.meals.values():
        recipe = library.get(meal.recipe.id, meal.recipe)
        reasons = []
        if recipe.liked:
            reasons.append(i18n.t(lang, "reason_liked"))
        else:
            mine = set(taste_logic.traits(recipe))
            favourite = next((key for key in likes if key in mine), None)
            if favourite:
                what = i18n.word(lang, favourite.split(":", 1)[1])
                reasons.append(i18n.t(lang, "reason_often", what=what))
        if meal.is_new or recipe.last_planned_week is None:
            reasons.append(i18n.t(lang, "reason_new"))
        meal.reasons = reasons


def interpret_diets(ai: RecipeAI | None, settings: Settings) -> Settings:
    """Words the app does not know yet ("low FODMAP", "nordic") get a meaning once, by AI:
    a diet with what fits and any limits, or a cuisine with its language."""
    unknown = [w for w in settings.diets if not is_known(w) and w not in settings.diet_meanings]
    known_now = {w: m for w, m in settings.diet_meanings.items() if w in settings.diets}
    if not unknown or ai is None:
        return settings.model_copy(update={"diet_meanings": known_now})
    try:
        meanings = ai.interpret_diets(unknown)
    except (AIError, AttributeError) as error:
        log.warning("Could not interpret diets %s: %s", unknown, error)
        return settings.model_copy(update={"diet_meanings": known_now})
    return settings.model_copy(update={"diet_meanings": {**known_now, **meanings}})
