"""The household's taste, learned from what it does. Pure functions.

Every action nudges a score for the recipe and, more gently, for its traits (main
protein, tags, quick). Scores halve every two months, so recent actions count most.
The planner uses the total as a tie-breaker, after every rule.
"""

from datetime import date
from typing import Any

from app.models import TasteProfile

HALF_LIFE_DAYS = 60
TRAIT_SHARE = 0.3  # how much of an action spills over to the recipe's traits
QUICK_MINUTES = 30

# How strongly each action counts for the recipe itself.
CHOSE = 1.0  # chose it by hand for a meal
SWAPPED_OUT = -1.0  # replaced it, by hand or with the swap button
KEPT = 0.2  # it stayed in a plan that was approved
LIKED = 2.0  # ♥
NOT_FOR_US = -3.0


def traits(recipe: Any) -> list[str]:
    keys = [f"protein:{recipe.protein}"] if recipe.protein and recipe.protein != "other" else []
    keys += [f"tag:{tag}" for tag in recipe.tags[:6]]
    if recipe.prep_minutes and recipe.prep_minutes <= QUICK_MINUTES and "tag:quick" not in keys:
        keys.append("tag:quick")
    return keys


def _now(profile: TasteProfile, key: str, today: date) -> float:
    if key not in profile.scores:
        return 0.0
    score, since = profile.scores[key]
    return score * 0.5 ** (max(0, (today - since).days) / HALF_LIFE_DAYS)


def nudge(profile: TasteProfile, recipe: Any, weight: float, today: date) -> TasteProfile:
    """Record an action on a recipe: ``weight`` for it, a share of that for its traits."""
    profile = profile.model_copy(deep=True)
    changes = {f"recipe:{recipe.id}": weight}
    for key in traits(recipe):
        changes[key] = changes.get(key, 0.0) + weight * TRAIT_SHARE
    for key, change in changes.items():
        value = max(-10.0, min(10.0, _now(profile, key, today) + change))
        profile.scores[key] = (round(value, 4), today)
    return profile


def score(profile: TasteProfile, recipe: Any, today: date) -> float:
    total = _now(profile, f"recipe:{recipe.id}", today)
    total += sum(_now(profile, key, today) for key in traits(recipe))
    if recipe.liked:
        total += LIKED
    return round(total, 4)


def leanings(profile: TasteProfile, today: date, count: int = 4) -> tuple[list[str], list[str]]:
    """Traits liked most and least, e.g. (["protein:fish", "tag:quick"], ["protein:lamb"])."""
    values = [
        (key, _now(profile, key, today)) for key in profile.scores if not key.startswith("recipe:")
    ]
    likes = [k for k, v in sorted(values, key=lambda kv: -kv[1]) if v >= 0.25][:count]
    dislikes = [k for k, v in sorted(values, key=lambda kv: kv[1]) if v <= -0.25][:count]
    return likes, dislikes
