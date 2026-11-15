"""Recipe library, plus the AI ways of getting a recipe in."""

from collections.abc import Callable

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from app.ai.base import AIError, RecipeAI
from app.deps import AIDep, CurrentHousehold, RepoDep
from app.links import LinkContent, LinkError
from app.models import Recipe, RecipeDraft

router = APIRouter(prefix="/recipes", tags=["recipes"])

MAX_IMAGES = 10
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # Gemini accepts up to about 20 MB sent inline
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
VIDEO_TYPES = {"video/mp4", "video/quicktime", "video/webm", "video/x-m4v", "video/3gpp"}


class TextImport(BaseModel):
    text: str = Field(min_length=10, max_length=20000)


class LinkImport(BaseModel):
    url: str = Field(min_length=8, max_length=2000)


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=200)
    count: int = Field(default=4, ge=1, le=6)


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
    return draft


def get_link_reader(request: Request) -> Callable[[str], LinkContent]:
    return request.app.state.read_link


def all_files(files: list[UploadFile] | None, file: UploadFile | None) -> list[UploadFile]:
    """Accept images sent as several "files" fields, or as a single "file" field."""
    return [*(files or []), *([file] if file else [])]


@router.get("")
def list_recipes(household: CurrentHousehold, repo: RepoDep) -> list[Recipe]:
    return sorted(repo.list_recipes(household.id), key=lambda recipe: recipe.title.lower())


@router.post("", status_code=201)
def create_recipe(draft: RecipeDraft, household: CurrentHousehold, repo: RepoDep) -> Recipe:
    recipe = Recipe(**draft.model_dump())
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
    recipe_id: str, draft: RecipeDraft, household: CurrentHousehold, repo: RepoDep
) -> Recipe:
    existing = repo.get_recipe(household.id, recipe_id)
    if existing is None:
        raise HTTPException(404, "Recipe not found")
    # Saving an edit counts as reviewing it.
    recipe = existing.model_copy(update={**draft.model_dump(), "needs_review": False})
    recipe = Recipe.model_validate(recipe.model_dump())
    repo.save_recipe(household.id, recipe)
    return recipe


@router.delete("/{recipe_id}", status_code=204)
def delete_recipe(recipe_id: str, household: CurrentHousehold, repo: RepoDep) -> None:
    repo.delete_recipe(household.id, recipe_id)


# The import endpoints return a draft and save nothing: the user reviews it first.


@router.post("/import/image")
async def import_images(
    household: CurrentHousehold,
    ai: AIDep,
    files: list[UploadFile] | None = File(None),
    file: UploadFile | None = File(None),
) -> RecipeDraft:
    """One recipe from one or more screenshots, in the order they are sent."""
    images = await read_images(all_files(files, file))
    return ai_call(lambda: ai.recipe_from_images(images))


@router.post("/import/video")
async def import_video(
    household: CurrentHousehold,
    ai: AIDep,
    file: UploadFile = File(...),
    caption: str = Form("", max_length=5000),
) -> RecipeDraft:
    data, mime_type = await read_video(file)
    return ai_call(lambda: ai.recipe_from_video(data, mime_type, caption))


@router.post("/import/link")
def import_link_route(
    body: LinkImport, household: CurrentHousehold, ai: AIDep, request: Request
) -> RecipeDraft:
    return import_link(ai, get_link_reader(request), body.url)


@router.post("/import/text")
def import_text(body: TextImport, household: CurrentHousehold, ai: AIDep) -> RecipeDraft:
    return ai_call(lambda: ai.recipe_from_text(body.text))


@router.post("/search")
def search(
    body: SearchRequest, household: CurrentHousehold, repo: RepoDep, ai: AIDep
) -> list[RecipeDraft]:
    titles = [recipe.title for recipe in repo.list_recipes(household.id)]
    return ai_call(lambda: ai.search_recipes(body.query, body.count, titles))
