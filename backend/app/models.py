"""Data shapes shared by the API, the core logic and storage."""

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.ingredients import guess_aisle, normalize_name, normalize_unit
from app.core.weeks import SLOT_KEYS

Aisle = Literal[
    "produce",
    "meat_fish",
    "dairy_eggs",
    "bakery",
    "pantry",
    "frozen",
    "drinks",
    "household",
    "other",
]

# Dinners on Monday to Thursday double as the next day's lunch by default.
_DEFAULT_PORTIONS = {
    "mon_dinner": 4,
    "tue_dinner": 4,
    "wed_dinner": 4,
    "thu_dinner": 4,
    "fri_dinner": 2,
    "sat_lunch": 2,
    "sat_dinner": 2,
    "sun_lunch": 2,
    "sun_dinner": 2,
}


def new_id() -> str:
    return uuid4().hex


def now() -> datetime:
    return datetime.now(UTC)


class Ingredient(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    quantity: float | None = Field(default=None, ge=0)
    unit: str = Field(default="", max_length=20)
    aisle: Aisle = "other"

    @field_validator("name")
    @classmethod
    def _canonical_name(cls, value: str) -> str:
        normalized = normalize_name(value)
        if not normalized:
            raise ValueError("ingredient name is empty")
        return normalized

    @field_validator("unit", mode="before")
    @classmethod
    def _canonical_unit(cls, value: str | None) -> str:
        return normalize_unit(value)

    @model_validator(mode="after")
    def _fill_aisle(self) -> "Ingredient":
        # When nobody chose an aisle, work it out from the name.
        if self.aisle == "other":
            self.aisle = guess_aisle(self.name)  # type: ignore[assignment]
        return self


class RecipeDraft(BaseModel):
    """A recipe before it is saved: what the user types or the AI extracts."""

    title: str = Field(min_length=1, max_length=200)
    servings: int = Field(default=2, ge=1, le=50)
    ingredients: list[Ingredient] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    protein: str = "other"
    tags: list[str] = Field(default_factory=list)
    prep_minutes: int | None = Field(default=None, ge=0, le=1440)
    source_url: str | None = None
    original_language: str = "en"

    @field_validator("protein", mode="before")
    @classmethod
    def _lower_protein(cls, value: str | None) -> str:
        return (value or "other").strip().lower() or "other"

    @field_validator("tags", mode="before")
    @classmethod
    def _lower_tags(cls, value: list[str] | None) -> list[str]:
        seen: list[str] = []
        for tag in value or []:
            cleaned = str(tag).strip().lower()
            if cleaned and cleaned not in seen:
                seen.append(cleaned)
        return seen


class Recipe(RecipeDraft):
    id: str = Field(default_factory=new_id)
    created_at: datetime = Field(default_factory=now)
    last_planned_week: str | None = None
    needs_review: bool = False


class SlotSetting(BaseModel):
    cook: bool = False
    portions: int = Field(default=2, ge=1, le=30)


class Rule(BaseModel):
    """ "At least 2 chicken meals" is kind="min", count=2, tag="chicken"."""

    kind: Literal["min", "max"] = "min"
    count: int = Field(ge=0, le=14)
    tag: str = Field(min_length=1, max_length=40)

    @field_validator("tag")
    @classmethod
    def _lower_tag(cls, value: str) -> str:
        return value.strip().lower()


def default_slots() -> dict[str, SlotSetting]:
    return {
        key: SlotSetting(cook=key in _DEFAULT_PORTIONS, portions=_DEFAULT_PORTIONS.get(key, 2))
        for key in SLOT_KEYS
    }


class Settings(BaseModel):
    slots: dict[str, SlotSetting] = Field(default_factory=default_slots)
    rules: list[Rule] = Field(default_factory=list)
    staples: list[str] = Field(default_factory=list)
    repeat_window_weeks: int = Field(default=2, ge=0, le=8)
    max_repeat_ratio: float = Field(default=0.2, ge=0, le=1)
    timezone: str = "Europe/Lisbon"

    @model_validator(mode="after")
    def _complete_slots(self) -> "Settings":
        self.slots = {key: self.slots.get(key, SlotSetting()) for key in SLOT_KEYS}
        self.staples = sorted({normalize_name(s) for s in self.staples if normalize_name(s)})
        return self

    def cook_slots(self) -> list[str]:
        return [key for key in SLOT_KEYS if self.slots[key].cook]


class PlanMeal(BaseModel):
    """One planned meal. The recipe is copied in so later edits don't change past weeks."""

    recipe: Recipe
    portions: int = Field(ge=1, le=30)
    is_new: bool = False


class WeekPlan(BaseModel):
    week_id: str
    status: Literal["draft", "approved"] = "draft"
    meals: dict[str, PlanMeal] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=now)
    approved_at: datetime | None = None


class RuleStatus(BaseModel):
    label: str
    ok: bool
    count: int
    target: int


class PlanOut(WeekPlan):
    rule_status: list[RuleStatus] = Field(default_factory=list)
    open_slots: list[str] = Field(default_factory=list)


class Alternative(BaseModel):
    recipe: Recipe
    keeps_rules: bool


class GroceryItem(BaseModel):
    id: str = Field(default_factory=new_id)
    name: str = Field(min_length=1, max_length=120)
    quantity: float | None = None
    unit: str = ""
    aisle: Aisle = "other"
    checked: bool = False
    source: Literal["plan", "manual", "siri"] = "manual"
    week_id: str | None = None
    recipes: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=now)


class Household(BaseModel):
    id: str = Field(default_factory=new_id)
    members: list[str] = Field(default_factory=list)
    owner_email: str = ""
    shortcut_token: str = ""
    device_tokens: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=now)
