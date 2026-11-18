"""Weekly plans: generate, adjust, approve."""

import random

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import services
from app.core.weeks import parse_week_id
from app.deps import CurrentHousehold, OptionalAIDep, QueueDep, RepoDep, WebDep
from app.models import Alternative, PlanOut
from app.tasks import PlanJob, QueueError

router = APIRouter(prefix="/plans", tags=["plans"])


class MealChange(BaseModel):
    recipe_id: str | None = None
    portions: int | None = Field(default=None, ge=1, le=30)


class ApproveResult(BaseModel):
    plan: PlanOut
    grocery_items: int


def _week(week_id: str) -> str:
    try:
        return parse_week_id(week_id).isoformat()
    except ValueError as error:
        raise HTTPException(422, "A week is identified by the date of its Monday") from error


@router.get("/{week_id}")
def get_plan(week_id: str, household: CurrentHousehold, repo: RepoDep) -> PlanOut | None:
    """The plan for a week, or null when none has been made yet."""
    plan = repo.get_plan(household.id, _week(week_id))
    return services.plan_out(repo, household.id, plan) if plan else None


def _start(repo, queue, household_id: str, week_id: str, mode: str) -> PlanOut:
    """Queue the plan and answer at once. The app shows "Planning your week…" while
    ``generating_since`` is set, and asks again until the new plan is there."""
    job = PlanJob(household_id=household_id, week_id=week_id, mode=mode)  # type: ignore[arg-type]
    try:
        plan = services.start_plan_job(repo, queue, job)
    except services.NotFound as error:
        raise HTTPException(404, str(error)) from error
    except QueueError as error:
        raise HTTPException(503, str(error)) from error
    return services.plan_out(repo, household_id, plan)


@router.post("/{week_id}/generate")
def generate(week_id: str, household: CurrentHousehold, repo: RepoDep, queue: QueueDep) -> PlanOut:
    """Make a new plan for the week, in the background."""
    return _start(repo, queue, household.id, _week(week_id), "generate")


@router.put("/{week_id}/meals/{slot}")
def set_meal(
    week_id: str, slot: str, change: MealChange, household: CurrentHousehold, repo: RepoDep
) -> PlanOut:
    try:
        plan = services.set_meal(
            repo, household.id, _week(week_id), slot, change.recipe_id, change.portions
        )
    except services.NotFound as error:
        raise HTTPException(404, str(error)) from error
    return services.plan_out(repo, household.id, plan)


@router.post("/{week_id}/apply-diets")
def apply_diets(
    week_id: str, household: CurrentHousehold, repo: RepoDep, queue: QueueDep
) -> PlanOut:
    """Update an existing plan for the current diets, keeping the meals that fit; in the
    background."""
    return _start(repo, queue, household.id, _week(week_id), "apply_diets")


class MealMove(BaseModel):
    to_slot: str


@router.post("/{week_id}/meals/{slot}/move")
def move(
    week_id: str, slot: str, body: MealMove, household: CurrentHousehold, repo: RepoDep
) -> PlanOut:
    """Drag and drop a meal onto another day: the two swap, each day keeping its portions."""
    try:
        plan = services.move_meal(repo, household.id, _week(week_id), slot, body.to_slot)
    except services.NotFound as error:
        raise HTTPException(404, str(error)) from error
    return services.plan_out(repo, household.id, plan)


@router.post("/{week_id}/meals/{slot}/swap")
def swap(week_id: str, slot: str, household: CurrentHousehold, repo: RepoDep) -> PlanOut:
    """Swap a meal in one tap for another recipe that keeps the rules."""
    try:
        plan = services.swap_meal(repo, household.id, _week(week_id), slot, random.Random())
    except services.NotFound as error:
        raise HTTPException(404, str(error)) from error
    return services.plan_out(repo, household.id, plan)


class SkipRequest(BaseModel):
    # When next week is full, the meal there to replace (from a previous answer).
    replace_slot: str | None = None


@router.post("/{week_id}/meals/{slot}/skip")
def skip(
    week_id: str, slot: str, body: SkipRequest, household: CurrentHousehold, repo: RepoDep
) -> services.SkipResult:
    """ "I'm not cooking this": keep the food in the pantry, move the recipe to next week."""
    try:
        return services.skip_meal(repo, household.id, _week(week_id), slot, body.replace_slot)
    except services.NotFound as error:
        raise HTTPException(404, str(error)) from error


@router.get("/{week_id}/meals/{slot}/alternatives")
def alternatives(
    week_id: str, slot: str, household: CurrentHousehold, repo: RepoDep
) -> list[Alternative]:
    try:
        return services.meal_alternatives(repo, household.id, _week(week_id), slot)
    except services.NotFound as error:
        raise HTTPException(404, str(error)) from error


@router.post("/{week_id}/approve")
def approve(
    week_id: str, household: CurrentHousehold, repo: RepoDep, web: WebDep, ai: OptionalAIDep
) -> ApproveResult:
    try:
        plan, count = services.approve_plan(repo, household.id, _week(week_id), web, ai)
    except services.NotFound as error:
        raise HTTPException(404, str(error)) from error
    return ApproveResult(plan=services.plan_out(repo, household.id, plan), grocery_items=count)
