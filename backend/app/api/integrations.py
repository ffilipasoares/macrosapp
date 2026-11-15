"""Callers that are not the web app: Apple Shortcuts and Cloud Scheduler."""

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import BaseModel, Field

from app import services
from app.api.recipes import (
    LinkImport,
    ai_call,
    all_files,
    get_link_reader,
    import_link,
    read_audio,
    read_images,
    read_video,
)
from app.deps import (
    AIDep,
    ConfigDep,
    NotifierDep,
    OptionalAIDep,
    RepoDep,
    ShortcutHousehold,
    scheduler_only,
)
from app.models import Recipe, RecipeDraft
from app.repo.base import Repo

router = APIRouter(tags=["integrations"])


class SiriItem(BaseModel):
    item: str = Field(min_length=1, max_length=300)


class Spoken(BaseModel):
    """``message`` is what Siri reads back."""

    message: str


def _save_for_review(repo: Repo, household_id: str, draft: RecipeDraft) -> Spoken:
    recipe = Recipe(**draft.model_dump(), needs_review=True)
    repo.save_recipe(household_id, recipe)
    return Spoken(message=f"Saved {recipe.title}. Check it in the app.")


@router.post("/shortcuts/grocery")
def siri_add(body: SiriItem, household: ShortcutHousehold, repo: RepoDep) -> Spoken:
    """ "Hey Siri, add to groceries": add what was dictated to the list."""
    added = services.add_items_from_text(repo, household.id, body.item, "siri")
    if not added:
        return Spoken(message="That is already on your list.")
    return Spoken(message=f"Added {', '.join(item.name for item in added)} to your groceries.")


@router.post("/shortcuts/recipe-image")
async def share_recipe_images(
    household: ShortcutHousehold,
    repo: RepoDep,
    ai: AIDep,
    files: list[UploadFile] | None = File(None),
    file: UploadFile | None = File(None),
) -> Spoken:
    """Share sheet: read one or more screenshots and save the recipe, flagged for review."""
    images = await read_images(all_files(files, file))
    draft = ai_call(lambda: ai.recipe_from_images(images))
    return _save_for_review(repo, household.id, draft)


@router.post("/shortcuts/recipe-video")
async def share_recipe_video(
    household: ShortcutHousehold,
    repo: RepoDep,
    ai: AIDep,
    file: UploadFile = File(...),
    caption: str = Form("", max_length=5000),
) -> Spoken:
    """Share sheet: watch a saved cooking video and save the recipe, flagged for review."""
    data, mime_type = await read_video(file)
    draft = ai_call(lambda: ai.recipe_from_video(data, mime_type, caption))
    return _save_for_review(repo, household.id, draft)


@router.post("/shortcuts/recipe-audio")
async def share_recipe_audio(
    household: ShortcutHousehold, repo: RepoDep, ai: AIDep, file: UploadFile = File(...)
) -> Spoken:
    """Share sheet or "Hey Siri": a spoken recipe, saved for review."""
    data, mime_type = await read_audio(file)
    draft = ai_call(lambda: ai.recipe_from_audio(data, mime_type))
    return _save_for_review(repo, household.id, draft)


@router.post("/shortcuts/recipe-link")
def share_recipe_link(
    body: LinkImport, household: ShortcutHousehold, repo: RepoDep, ai: AIDep, request: Request
) -> Spoken:
    """Share sheet: read a TikTok caption or recipe page and save it, flagged for review."""
    draft = import_link(ai, get_link_reader(request), body.url)
    return _save_for_review(repo, household.id, draft)


@router.post("/jobs/weekly-plan", dependencies=[Depends(scheduler_only)])
def weekly_plan(
    repo: RepoDep, ai: OptionalAIDep, notifier: NotifierDep, config: ConfigDep
) -> dict[str, int]:
    """Called by Cloud Scheduler every Friday."""
    return services.run_weekly_job(repo, ai, notifier, config.app_url)
