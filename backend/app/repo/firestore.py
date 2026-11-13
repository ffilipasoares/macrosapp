"""Firestore storage.

Layout (everything a household owns sits under its document):

    users/{uid}                          -> {household_id, email}
    households/{id}                      -> members, shortcut_token, device_tokens
    households/{id}/config/settings
    households/{id}/recipes/{recipe_id}
    households/{id}/plans/{week_id}
    households/{id}/groceries/{item_id}  (the web app also reads and writes these directly)
"""

import secrets

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from app.models import GroceryItem, Household, Recipe, Settings, WeekPlan

_BATCH_LIMIT = 400


class FirestoreRepo:
    def __init__(self, client: firestore.Client) -> None:
        self.db = client

    def _household(self, household_id: str) -> firestore.DocumentReference:
        return self.db.collection("households").document(household_id)

    # Households -----------------------------------------------------------

    def household_for_user(self, uid: str, email: str) -> Household:
        user_ref = self.db.collection("users").document(uid)
        user = user_ref.get()
        if user.exists:
            snapshot = self._household(user.get("household_id")).get()
            if snapshot.exists:
                return Household(id=snapshot.id, **snapshot.to_dict())

        household = Household(
            members=[uid], owner_email=email, shortcut_token=secrets.token_urlsafe(24)
        )
        batch = self.db.batch()
        batch.set(self._household(household.id), household.model_dump(mode="json", exclude={"id"}))
        batch.set(user_ref, {"household_id": household.id, "email": email})
        batch.commit()
        return household

    def household_by_shortcut_token(self, token: str) -> Household | None:
        query = (
            self.db.collection("households")
            .where(filter=FieldFilter("shortcut_token", "==", token))
            .limit(1)
        )
        for snapshot in query.stream():
            return Household(id=snapshot.id, **snapshot.to_dict())
        return None

    def list_households(self) -> list[Household]:
        return [
            Household(id=snapshot.id, **snapshot.to_dict())
            for snapshot in self.db.collection("households").stream()
        ]

    def add_device_token(self, household_id: str, token: str) -> None:
        self._household(household_id).update({"device_tokens": firestore.ArrayUnion([token])})

    def remove_device_tokens(self, household_id: str, tokens: list[str]) -> None:
        if tokens:
            self._household(household_id).update({"device_tokens": firestore.ArrayRemove(tokens)})

    # Settings -------------------------------------------------------------

    def _settings_ref(self, household_id: str) -> firestore.DocumentReference:
        return self._household(household_id).collection("config").document("settings")

    def get_settings(self, household_id: str) -> Settings:
        snapshot = self._settings_ref(household_id).get()
        return Settings(**snapshot.to_dict()) if snapshot.exists else Settings()

    def save_settings(self, household_id: str, settings: Settings) -> None:
        self._settings_ref(household_id).set(settings.model_dump(mode="json"))

    # Recipes --------------------------------------------------------------

    def _recipes(self, household_id: str) -> firestore.CollectionReference:
        return self._household(household_id).collection("recipes")

    def list_recipes(self, household_id: str) -> list[Recipe]:
        return [Recipe(**{**s.to_dict(), "id": s.id}) for s in self._recipes(household_id).stream()]

    def get_recipe(self, household_id: str, recipe_id: str) -> Recipe | None:
        snapshot = self._recipes(household_id).document(recipe_id).get()
        return Recipe(**{**snapshot.to_dict(), "id": snapshot.id}) if snapshot.exists else None

    def save_recipe(self, household_id: str, recipe: Recipe) -> None:
        self._recipes(household_id).document(recipe.id).set(recipe.model_dump(mode="json"))

    def delete_recipe(self, household_id: str, recipe_id: str) -> None:
        self._recipes(household_id).document(recipe_id).delete()

    # Plans ----------------------------------------------------------------

    def get_plan(self, household_id: str, week_id: str) -> WeekPlan | None:
        snapshot = self._household(household_id).collection("plans").document(week_id).get()
        return WeekPlan(**snapshot.to_dict()) if snapshot.exists else None

    def save_plan(self, household_id: str, plan: WeekPlan) -> None:
        # The week id is the document id, so saving the same week twice overwrites.
        self._household(household_id).collection("plans").document(plan.week_id).set(
            plan.model_dump(mode="json")
        )

    # Groceries ------------------------------------------------------------

    def _groceries(self, household_id: str) -> firestore.CollectionReference:
        return self._household(household_id).collection("groceries")

    def list_groceries(self, household_id: str) -> list[GroceryItem]:
        return [
            GroceryItem(**{**s.to_dict(), "id": s.id})
            for s in self._groceries(household_id).stream()
        ]

    def add_groceries(self, household_id: str, items: list[GroceryItem]) -> None:
        collection = self._groceries(household_id)
        for start in range(0, len(items), _BATCH_LIMIT):
            batch = self.db.batch()
            for item in items[start : start + _BATCH_LIMIT]:
                batch.set(collection.document(item.id), item.model_dump(mode="json"))
            batch.commit()

    def delete_plan_groceries(self, household_id: str, week_id: str) -> None:
        query = self._groceries(household_id).where(filter=FieldFilter("week_id", "==", week_id))
        refs = [s.reference for s in query.stream() if s.get("source") == "plan"]
        for start in range(0, len(refs), _BATCH_LIMIT):
            batch = self.db.batch()
            for ref in refs[start : start + _BATCH_LIMIT]:
                batch.delete(ref)
            batch.commit()
