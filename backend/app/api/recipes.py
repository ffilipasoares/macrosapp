"""Recipe library, plus the three AI ways of getting a recipe in."""

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.ai.base import AIError, RecipeAI
from app.deps import AIDep, CurrentHousehold, RepoDep
from app.models import Recipe, RecipeDraft

router = APIRouter(prefix="/recipes", tags=["recipes"])

MAX_IMAGE_BYTES = 8 * 1024 * 1024
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}


class TextImport(BaseModel):
    text: str = Field(min_length=10, max_length=20000)


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=200)
    count: int = Field(default=4, ge=1, le=6)


async def read_image(file: UploadFile) -> tuple[bytes, str]:
    mime_type = (file.content_type or "").lower()
    if mime_type not in IMAGE_TYPES:
        raise HTTPException(415, "Send a JPEG, PNG, WebP or HEIC image")
    data = await file.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "The image is larger than 8 MB")
    return data, mime_type


def extract_from_image(ai: RecipeAI, data: bytes, mime_type: str) -> RecipeDraft:
    try:
        return ai.recipe_from_image(data, mime_type)
    except AIError as error:
        raise HTTPException(422, str(error)) from error


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
async def import_image(file: UploadFile, household: CurrentHousehold, ai: AIDep) -> RecipeDraft:
    data, mime_type = await read_image(file)
    return extract_from_image(ai, data, mime_type)


@router.post("/import/text")
def import_text(body: TextImport, household: CurrentHousehold, ai: AIDep) -> RecipeDraft:
    try:
        return ai.recipe_from_text(body.text)
    except AIError as error:
        raise HTTPException(422, str(error)) from error


@router.post("/search")
def search(
    body: SearchRequest, household: CurrentHousehold, repo: RepoDep, ai: AIDep
) -> list[RecipeDraft]:
    titles = [recipe.title for recipe in repo.list_recipes(household.id)]
    try:
        return ai.search_recipes(body.query, body.count, titles)
    except AIError as error:
        raise HTTPException(422, str(error)) from error
