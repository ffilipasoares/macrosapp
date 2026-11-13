"""Callers that are not the web app: Apple Shortcuts and Cloud Scheduler."""

from fastapi import APIRouter, Depends, UploadFile
from pydantic import BaseModel, Field

from app import services
from app.api.recipes import extract_from_image, read_image
from app.deps import (
    AIDep,
    ConfigDep,
    NotifierDep,
    OptionalAIDep,
    RepoDep,
    ShortcutHousehold,
    scheduler_only,
)
from app.models import Recipe

router = APIRouter(tags=["integrations"])


class SiriItem(BaseModel):
    item: str = Field(min_length=1, max_length=300)


class Spoken(BaseModel):
    """``message`` is what Siri reads back."""

    message: str


@router.post("/shortcuts/grocery")
def siri_add(body: SiriItem, household: ShortcutHousehold, repo: RepoDep) -> Spoken:
    """ "Hey Siri, add to groceries": add what was dictated to the list."""
    added = services.add_items_from_text(repo, household.id, body.item, "siri")
    if not added:
        return Spoken(message="That is already on your list.")
    return Spoken(message=f"Added {', '.join(item.name for item in added)} to your groceries.")


@router.post("/shortcuts/recipe-image")
async def share_recipe(
    file: UploadFile, household: ShortcutHousehold, repo: RepoDep, ai: AIDep
) -> Spoken:
    """Share sheet: read a screenshot and save the recipe, flagged for review in the app."""
    data, mime_type = await read_image(file)
    draft = extract_from_image(ai, data, mime_type)
    recipe = Recipe(**draft.model_dump(), needs_review=True)
    repo.save_recipe(household.id, recipe)
    return Spoken(message=f"Saved {recipe.title}. Check it in the app.")


@router.post("/jobs/weekly-plan", dependencies=[Depends(scheduler_only)])
def weekly_plan(
    repo: RepoDep, ai: OptionalAIDep, notifier: NotifierDep, config: ConfigDep
) -> dict[str, int]:
    """Called by Cloud Scheduler every Friday."""
    return services.run_weekly_job(repo, ai, notifier, config.app_url)
