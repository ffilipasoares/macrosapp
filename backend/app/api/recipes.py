"""Recipe library, plus the AI ways of getting a recipe in."""

from collections.abc import Callable

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from app import services
from app.ai.base import AIError, RecipeAI
from app.deps import AIDep, CurrentHousehold, OptionalAIDep, RepoDep, WebDep
from app.images import keep_own_copy
from app.links import LinkContent, LinkError
from app.models import Recipe, RecipeDraft

router = APIRouter(prefix="/recipes", tags=["recipes"])

MAX_IMAGES = 10
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # Gemini accepts up to about 20 MB sent inline
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
VIDEO_TYPES = {"video/mp4", "video/quicktime", "video/webm", "video/x-m4v", "video/3gpp"}
# Recorded in the browser (Safari: audio/mp4, Chrome: audio/webm) or a voice memo (m4a).
AUDIO_TYPES = {
    "audio/mp4": "audio/mp4",
    "audio/m4a": "audio/mp4",
    "audio/x-m4a": "audio/mp4",
    "audio/aac": "audio/aac",
    "audio/mpeg": "audio/mpeg",
    "audio/mp3": "audio/mpeg",
    "audio/wav": "audio/wav",
    "audio/x-wav": "audio/wav",
    "audio/webm": "audio/webm",
    "audio/ogg": "audio/ogg",
    "audio/flac": "audio/flac",
}


class TextImport(BaseModel):
    text: str = Field(min_length=10, max_length=20000)


class LinkImport(BaseModel):
    url: str = Field(min_length=8, max_length=2000)


def _mime(file: UploadFile) -> str:
    return (file.content_type or "").lower().split(";")[0].strip()


async def read_images(files: list[UploadFile]) -> list[tuple[bytes, str]]:
    if not files:
        raise HTTPException(422, "Add at least one image")
    if len(files) > MAX_IMAGES:
        raise HTTPException(413, f"Send at most {MAX_IMAGES} images for one recipe")
    images, total = [], 0
    for file in files:
        mime_type = _mime(file)
        if mime_type not in IMAGE_TYPES:
            raise HTTPException(415, "Send JPEG, PNG, WebP or HEIC images")
        data = await file.read(MAX_UPLOAD_BYTES + 1)
        total += len(data)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(
                413, "The images add up to more than 20 MB. Send fewer or smaller ones."
            )
        images.append((data, mime_type))
    return images


async def read_video(file: UploadFile) -> tuple[bytes, str]:
    mime_type = _mime(file)
    if mime_type not in VIDEO_TYPES:
        raise HTTPException(415, "Send an MP4 or MOV video")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            413, "The video is larger than 20 MB. Send a shorter clip or a screenshot."
        )
    return data, mime_type


async def read_audio(file: UploadFile) -> tuple[bytes, str]:
    mime_type = AUDIO_TYPES.get(_mime(file))
    if mime_type is None:
        raise HTTPException(415, "Send an M4A, MP3, WAV or WebM recording")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if not data:
        raise HTTPException(422, "The recording is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "The recording is larger than 20 MB. Keep it under 10 minutes.")
    return data, mime_type


def ai_call[T](work: Callable[[], T]) -> T:
    try:
        return work()
    except AIError as error:
        raise HTTPException(422, str(error)) from error


def import_link(ai: RecipeAI, read_link: Callable[[str], LinkContent], url: str) -> RecipeDraft:
    try:
        content = read_link(url)
    except LinkError as error:
        raise HTTPException(422, str(error)) from error
    try:
        draft = ai.recipe_from_text(content.text, source_url=content.url)
    except AIError as error:
        if content.kind == "tiktok" and "No recipe" in str(error):
            raise HTTPException(
                422,
                "This TikTok's caption doesn't include the recipe. Save the video "
                "(Share, then Save video) and send the video instead.",
            ) from error
        raise HTTPException(422, str(error)) from error
    draft.source_url = draft.source_url or content.url
    draft.image_url = draft.image_url or content.image_url
    return draft


def get_link_reader(request: Request) -> Callable[[str], LinkContent]:
    return request.app.state.read_link


def all_files(files: list[UploadFile] | None, file: UploadFile | None) -> list[UploadFile]:
    """Accept images sent as several "files" fields, or as a single "file" field."""
    return [*(files or []), *([file] if file else [])]


@router.get("")
def list_recipes(household: CurrentHousehold, repo: RepoDep, ai: OptionalAIDep) -> list[Recipe]:
    # Recipes not yet in the household's language are translated once, here.
    recipes = services.localize_library(repo, ai, household.id, repo.list_recipes(household.id))
    return sorted(recipes, key=lambda recipe: recipe.title.lower())


@router.post("", status_code=201)
def create_recipe(
    draft: RecipeDraft,
    household: CurrentHousehold,
    repo: RepoDep,
    web: WebDep,
    ai: OptionalAIDep,
) -> Recipe:
    recipe = services.prepare_for_household(repo, ai, household.id, Recipe(**draft.model_dump()))
    services.fill_nutrition(ai, recipe)
    # A photo from a web page or TikTok is copied, so it keeps working.
    keep_own_copy(web.images, web.read_image, household.id, recipe)
    repo.save_recipe(household.id, recipe)
    return recipe


@router.get("/{recipe_id}")
def get_recipe(recipe_id: str, household: CurrentHousehold, repo: RepoDep) -> Recipe:
    recipe = repo.get_recipe(household.id, recipe_id)
    if recipe is None:
        raise HTTPException(404, "Recipe not found")
    return recipe


@router.put("/{recipe_id}")
def update_recipe(
    recipe_id: str,
    draft: RecipeDraft,
    household: CurrentHousehold,
    repo: RepoDep,
    web: WebDep,
    ai: OptionalAIDep,
) -> Recipe:
    existing = repo.get_recipe(household.id, recipe_id)
    if existing is None:
        raise HTTPException(404, "Recipe not found")
    # Saving an edit counts as reviewing it.
    recipe = existing.model_copy(update={**draft.model_dump(), "needs_review": False})
    recipe = Recipe.model_validate(recipe.model_dump())
    recipe = services.prepare_for_household(repo, ai, household.id, recipe)
    services.fill_nutrition(ai, recipe, previous=existing)
    # A changed recipe may no longer fit a diet it was checked against.
    if (recipe.title, [i.name for i in recipe.ingredients]) != (
        existing.title,
        [i.name for i in existing.ingredients],
    ):
        recipe.diet_fit = {}
    if recipe.image_url != existing.image_url:
        keep_own_copy(web.images, web.read_image, household.id, recipe)
    repo.save_recipe(household.id, recipe)
    return recipe


@router.post("/{recipe_id}/macros")
def recalculate_macros(
    recipe_id: str, household: CurrentHousehold, repo: RepoDep, ai: AIDep
) -> Recipe:
    """Estimate the nutrition of every ingredient again."""
    try:
        return services.recalculate_macros(repo, ai, household.id, recipe_id)
    except services.NotFound as error:
        raise HTTPException(404, str(error)) from error


@router.delete("/{recipe_id}", status_code=204)
def delete_recipe(recipe_id: str, household: CurrentHousehold, repo: RepoDep) -> None:
    repo.delete_recipe(household.id, recipe_id)


# The import endpoints return a draft and save nothing: the user reviews it first.


@router.post("/import/image")
async def import_images(
    household: CurrentHousehold,
    ai: AIDep,
    repo: RepoDep,
    files: list[UploadFile] | None = File(None),
    file: UploadFile | None = File(None),
) -> RecipeDraft:
    """One recipe from one or more screenshots, in the order they are sent."""
    images = await read_images(all_files(files, file))
    draft = ai_call(lambda: ai.recipe_from_images(images))
    return services.draft_for_household(repo, ai, household.id, draft)


@router.post("/import/video")
async def import_video(
    household: CurrentHousehold,
    ai: AIDep,
    repo: RepoDep,
    file: UploadFile = File(...),
    caption: str = Form("", max_length=5000),
) -> RecipeDraft:
    data, mime_type = await read_video(file)
    draft = ai_call(lambda: ai.recipe_from_video(data, mime_type, caption))
    return services.draft_for_household(repo, ai, household.id, draft)


@router.post("/import/audio")
async def import_audio(
    household: CurrentHousehold, ai: AIDep, repo: RepoDep, file: UploadFile = File(...)
) -> RecipeDraft:
    """A recipe said out loud: recorded in the app, or a voice memo."""
    data, mime_type = await read_audio(file)
    draft = ai_call(lambda: ai.recipe_from_audio(data, mime_type))
    return services.draft_for_household(repo, ai, household.id, draft)


@router.post("/import/link")
def import_link_route(
    body: LinkImport, household: CurrentHousehold, ai: AIDep, request: Request, repo: RepoDep
) -> RecipeDraft:
    draft = import_link(ai, get_link_reader(request), body.url)
    return services.draft_for_household(repo, ai, household.id, draft)


@router.post("/import/text")
def import_text(
    body: TextImport, household: CurrentHousehold, ai: AIDep, repo: RepoDep
) -> RecipeDraft:
    draft = ai_call(lambda: ai.recipe_from_text(body.text))
    return services.draft_for_household(repo, ai, household.id, draft)
