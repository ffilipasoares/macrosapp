"""In-memory storage for tests."""

import secrets
from collections import defaultdict

from app.models import GroceryItem, Household, Recipe, Settings, WeekPlan


class MemoryRepo:
    def __init__(self) -> None:
        self.households: dict[str, Household] = {}
        self.user_household: dict[str, str] = {}
        self.settings: dict[str, Settings] = {}
        self.recipes: dict[str, dict[str, Recipe]] = defaultdict(dict)
        self.plans: dict[str, dict[str, WeekPlan]] = defaultdict(dict)
        self.groceries: dict[str, dict[str, GroceryItem]] = defaultdict(dict)

    def household_for_user(self, uid: str, email: str) -> Household:
        if uid not in self.user_household:
            household = Household(
                members=[uid], owner_email=email, shortcut_token=secrets.token_urlsafe(24)
            )
            self.households[household.id] = household
            self.user_household[uid] = household.id
        return self.households[self.user_household[uid]]

    def household_by_shortcut_token(self, token: str) -> Household | None:
        return next(
            (
                h
                for h in self.households.values()
                if secrets.compare_digest(h.shortcut_token, token)
            ),
            None,
        )

    def list_households(self) -> list[Household]:
        return list(self.households.values())

    def add_device_token(self, household_id: str, token: str) -> None:
        tokens = self.households[household_id].device_tokens
        if token not in tokens:
            tokens.append(token)

    def remove_device_tokens(self, household_id: str, tokens: list[str]) -> None:
        household = self.households[household_id]
        household.device_tokens = [t for t in household.device_tokens if t not in tokens]

    def get_settings(self, household_id: str) -> Settings:
        return self.settings.get(household_id, Settings()).model_copy(deep=True)

    def save_settings(self, household_id: str, settings: Settings) -> None:
        self.settings[household_id] = settings.model_copy(deep=True)

    def list_recipes(self, household_id: str) -> list[Recipe]:
        return [r.model_copy(deep=True) for r in self.recipes[household_id].values()]

    def get_recipe(self, household_id: str, recipe_id: str) -> Recipe | None:
        recipe = self.recipes[household_id].get(recipe_id)
        return recipe.model_copy(deep=True) if recipe else None

    def save_recipe(self, household_id: str, recipe: Recipe) -> None:
        self.recipes[household_id][recipe.id] = recipe.model_copy(deep=True)

    def delete_recipe(self, household_id: str, recipe_id: str) -> None:
        self.recipes[household_id].pop(recipe_id, None)

    def get_plan(self, household_id: str, week_id: str) -> WeekPlan | None:
        plan = self.plans[household_id].get(week_id)
        return plan.model_copy(deep=True) if plan else None

    def save_plan(self, household_id: str, plan: WeekPlan) -> None:
        self.plans[household_id][plan.week_id] = plan.model_copy(deep=True)

    def list_groceries(self, household_id: str) -> list[GroceryItem]:
        return [g.model_copy() for g in self.groceries[household_id].values()]

    def add_groceries(self, household_id: str, items: list[GroceryItem]) -> None:
        for item in items:
            self.groceries[household_id][item.id] = item.model_copy()

    def delete_plan_groceries(self, household_id: str, week_id: str) -> None:
        store = self.groceries[household_id]
        for item_id in [i for i, g in store.items() if g.source == "plan" and g.week_id == week_id]:
            del store[item_id]
