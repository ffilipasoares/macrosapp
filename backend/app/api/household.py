"""Account, settings, grocery adds and push registration for the signed-in household."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import services
from app.deps import CurrentHousehold, RepoDep
from app.models import GroceryItem, Settings

router = APIRouter(tags=["household"])


class Me(BaseModel):
    household_id: str
    email: str
    shortcut_token: str
    push_devices: int


class ItemText(BaseModel):
    text: str = Field(min_length=1, max_length=300)


class CheckedChange(BaseModel):
    checked: bool


class DeviceToken(BaseModel):
    token: str = Field(min_length=10, max_length=4096)


@router.get("/me")
def me(household: CurrentHousehold) -> Me:
    return Me(
        household_id=household.id,
        email=household.owner_email,
        shortcut_token=household.shortcut_token,
        push_devices=len(household.device_tokens),
    )


@router.get("/settings")
def get_settings(household: CurrentHousehold, repo: RepoDep) -> Settings:
    return repo.get_settings(household.id)


@router.put("/settings")
def save_settings(settings: Settings, household: CurrentHousehold, repo: RepoDep) -> Settings:
    repo.save_settings(household.id, settings)
    return settings


@router.get("/groceries")
def list_groceries(household: CurrentHousehold, repo: RepoDep) -> list[GroceryItem]:
    return sorted(repo.list_groceries(household.id), key=lambda item: (item.aisle, item.name))


@router.post("/groceries", status_code=201)
def add_groceries(body: ItemText, household: CurrentHousehold, repo: RepoDep) -> list[GroceryItem]:
    """Add typed items. The server picks the aisle; ticking and deleting happen in Firestore."""
    return services.add_items_from_text(repo, household.id, body.text, "manual")


# The app normally ticks and removes items straight in Firestore, for live sync and
# offline use. These routes are its fallback when that connection cannot be made.


@router.patch("/groceries/{item_id}", status_code=204)
def set_checked(
    item_id: str, body: CheckedChange, household: CurrentHousehold, repo: RepoDep
) -> None:
    if not repo.set_grocery_checked(household.id, item_id, body.checked):
        raise HTTPException(404, "That item is no longer on the list")


@router.delete("/groceries/{item_id}", status_code=204)
def delete_item(item_id: str, household: CurrentHousehold, repo: RepoDep) -> None:
    repo.delete_groceries(household.id, [item_id])


@router.post("/groceries/clear-checked", status_code=204)
def clear_checked(household: CurrentHousehold, repo: RepoDep) -> None:
    """Remove everything already in the basket."""
    ticked = [item.id for item in repo.list_groceries(household.id) if item.checked]
    repo.delete_groceries(household.id, ticked)


@router.post("/devices", status_code=204)
def register_device(body: DeviceToken, household: CurrentHousehold, repo: RepoDep) -> None:
    repo.add_device_token(household.id, body.token)
