"""My pantry: the food at home now. Read and written only through these routes."""

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app import services
from app.api.recipes import ai_call, all_files, read_audio, read_images
from app.deps import AIDep, CurrentHousehold, OptionalAIDep, RepoDep
from app.models import PantryDraft, PantryItem

router = APIRouter(prefix="/pantry", tags=["pantry"])


class PantryText(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class PutAwayResult(BaseModel):
    moved: int


@router.get("")
def list_pantry(household: CurrentHousehold, repo: RepoDep) -> list[PantryItem]:
    """Food at home, closest to its use-by first. Meals whose day has passed are taken out."""
    return services.list_pantry(repo, household.id)


@router.post("/text")
def add_text(
    body: PantryText, household: CurrentHousehold, repo: RepoDep, ai: OptionalAIDep
) -> list[PantryItem]:
    """Typed food, e.g. "2 eggs, half a courgette, 200 g spinach". Saved straight away."""
    return services.pantry_from_text(repo, household.id, body.text, ai)


@router.post("/read/images")
async def read_photos(
    household: CurrentHousehold,
    ai: AIDep,
    repo: RepoDep,
    files: list[UploadFile] | None = File(None),
    file: UploadFile | None = File(None),
) -> list[PantryDraft]:
    """Food seen in photos of the fridge or cupboards. Not saved: check it first."""
    images = await read_images(all_files(files, file))
    drafts = ai_call(lambda: ai.pantry_from_images(images))
    return services.pantry_labels(ai, drafts, repo.get_settings(household.id).language)


@router.post("/read/audio")
async def read_voice(
    household: CurrentHousehold, ai: AIDep, repo: RepoDep, file: UploadFile = File(...)
) -> list[PantryDraft]:
    """Food said out loud. Not saved: check it first."""
    data, mime_type = await read_audio(file)
    drafts = ai_call(lambda: ai.pantry_from_audio(data, mime_type))
    return services.pantry_labels(ai, drafts, repo.get_settings(household.id).language)


@router.post("/items")
def add_items(
    drafts: list[PantryDraft], household: CurrentHousehold, repo: RepoDep, ai: OptionalAIDep
) -> list[PantryItem]:
    """Save checked food, e.g. what a photo showed."""
    if len(drafts) > 100:
        raise HTTPException(422, "At most 100 items at a time")
    # Labels may have been corrected while checking: work out the English names again.
    lang = repo.get_settings(household.id).language
    return services.add_to_pantry(repo, household.id, services.pantry_names(ai, drafts, lang))


@router.put("/items/{item_id}")
def update_item(
    item_id: str,
    draft: PantryDraft,
    household: CurrentHousehold,
    repo: RepoDep,
    ai: OptionalAIDep,
) -> list[PantryItem]:
    draft = services.pantry_names(ai, [draft], repo.get_settings(household.id).language)[0]
    try:
        return services.update_pantry_item(repo, household.id, item_id, draft)
    except services.NotFound as error:
        raise HTTPException(404, str(error)) from error


@router.delete("/items/{item_id}")
def remove_item(item_id: str, household: CurrentHousehold, repo: RepoDep) -> list[PantryItem]:
    return services.remove_pantry_item(repo, household.id, item_id)


@router.post("/put-away")
def put_away(household: CurrentHousehold, repo: RepoDep) -> PutAwayResult:
    """Shopping done: everything in the basket moves into the pantry."""
    return PutAwayResult(moved=services.put_away(repo, household.id))
