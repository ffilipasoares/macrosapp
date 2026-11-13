"""Weekly plans: generate, adjust, approve."""

import random

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import services
from app.core.weeks import parse_week_id
from app.deps import CurrentHousehold, OptionalAIDep, RepoDep
from app.models import Alternative, PlanOut

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


@router.post("/{week_id}/generate")
def generate(
    week_id: str, household: CurrentHousehold, repo: RepoDep, ai: OptionalAIDep
) -> PlanOut:
    plan = services.generate_plan(repo, ai, household.id, _week(week_id), random.Random())
    return services.plan_out(repo, household.id, plan)


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


@router.get("/{week_id}/meals/{slot}/alternatives")
def alternatives(
    week_id: str, slot: str, household: CurrentHousehold, repo: RepoDep
) -> list[Alternative]:
    try:
        return services.meal_alternatives(repo, household.id, _week(week_id), slot)
    except services.NotFound as error:
        raise HTTPException(404, str(error)) from error


@router.post("/{week_id}/approve")
def approve(week_id: str, household: CurrentHousehold, repo: RepoDep) -> ApproveResult:
    try:
        plan, count = services.approve_plan(repo, household.id, _week(week_id))
    except services.NotFound as error:
        raise HTTPException(404, str(error)) from error
    return ApproveResult(plan=services.plan_out(repo, household.id, plan), grocery_items=count)
