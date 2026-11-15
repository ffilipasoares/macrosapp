"""Data shapes shared by the API, the core logic and storage."""

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.diet import tidy
from app.core.ingredients import guess_aisle, normalize_name, normalize_unit
from app.core.nutrition import recipe_totals
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


class IngredientNutrition(BaseModel):
    """An estimate for one ingredient: the weight of one unit, and macros per 100 g."""

    grams_per_unit: float | None = Field(default=None, ge=0, le=10000)
    kcal_per_100g: float = Field(ge=0, le=1000)
    protein_per_100g: float = Field(ge=0, le=100)
    carbs_per_100g: float = Field(ge=0, le=100)
    fat_per_100g: float = Field(ge=0, le=100)


class Macros(BaseModel):
    """Totals for the whole recipe as written. The app divides them into portions."""

    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float
    weight_g: float
    missing: list[str] = Field(default_factory=list)


class Ingredient(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    quantity: float | None = Field(default=None, ge=0)
    unit: str = Field(default="", max_length=20)
    aisle: Aisle = "other"
    nutrition: IngredientNutrition | None = None

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
    # A photo: uploaded to Firebase Storage by the app, or taken from the recipe's web page.
    image_url: str | None = Field(default=None, max_length=2000)
    original_language: str = "en"
    # Worked out from the ingredients every time a recipe is built; never set by hand.
    macros: Macros | None = None

    @model_validator(mode="after")
    def _work_out_macros(self) -> "RecipeDraft":
        self.refresh_macros()
        return self

    def refresh_macros(self) -> None:
        totals = recipe_totals(self.ingredients)
        self.macros = Macros(**totals) if totals else None

    @field_validator("image_url")
    @classmethod
    def _web_image(cls, value: str | None) -> str | None:
        if value and not value.startswith(("https://", "http://")):
            raise ValueError("image_url must be a web address")
        return value or None

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
    # Whether the recipe fits each diet it was checked against, e.g. {"mediterranean": true}.
    diet_fit: dict[str, bool] = Field(default_factory=dict)


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


class ReferencePortion(BaseModel):
    """What "one portion" means when showing macros."""

    kind: Literal["serving", "grams"] = "serving"
    grams: int = Field(default=400, ge=50, le=2000)


class Settings(BaseModel):
    slots: dict[str, SlotSetting] = Field(default_factory=default_slots)
    rules: list[Rule] = Field(default_factory=list)
    staples: list[str] = Field(default_factory=list)
    repeat_window_weeks: int = Field(default=2, ge=0, le=8)
    max_repeat_ratio: float = Field(default=0.2, ge=0, le=1)
    timezone: str = "Europe/Lisbon"
    reference_portion: ReferencePortion = Field(default_factory=ReferencePortion)
    # Free text, several allowed, e.g. ["mediterranean", "high-protein"].
    # Vegetarian, vegan and pescatarian also rule out foods.
    diets: list[str] = Field(default_factory=list, max_length=6)

    @model_validator(mode="before")
    @classmethod
    def _one_diet_becomes_a_list(cls, data: object) -> object:
        # Settings saved before several diets were possible had a single "diet".
        if isinstance(data, dict) and "diet" in data and not data.get("diets"):
            data = {**data, "diets": [data["diet"]] if data["diet"] else []}
        return data

    @field_validator("diets")
    @classmethod
    def _tidy_diets(cls, value: list[str]) -> list[str]:
        diets = tidy(value)
        if any(len(diet) > 60 for diet in diets):
            raise ValueError("a diet is at most 60 characters")
        return diets

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
    # The diets the plan was made for; None for plans made before diets existed.
    diets: list[str] | None = None


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
