"""Application factory. Everything the app depends on can be swapped in tests."""

import logging
from collections.abc import Callable

from fastapi import FastAPI

from app.ai.base import RecipeAI
from app.api import household, integrations, plans, recipes
from app.config import Config
from app.notify import FcmNotifier, LogNotifier, Notifier
from app.repo.base import Repo

logging.basicConfig(level=logging.INFO)


def _init_firebase(config: Config) -> None:
    import firebase_admin

    if not firebase_admin._apps:
        firebase_admin.initialize_app(options={"projectId": config.project_id})


def _default_repo(config: Config) -> Repo:
    from google.cloud import firestore

    from app.repo.firestore import FirestoreRepo

    return FirestoreRepo(firestore.Client(project=config.project_id))


def _default_ai(config: Config) -> RecipeAI | None:
    if config.ai_provider == "gemini":
        from app.ai.gemini import GeminiRecipeAI

        return GeminiRecipeAI(config.project_id, config.gemini_location, config.gemini_model)
    if config.ai_provider == "fake":
        from app.ai.fake import FakeRecipeAI

        return FakeRecipeAI()
    return None


def _default_verify_token(config: Config) -> Callable[[str], dict]:
    from firebase_admin import auth

    _init_firebase(config)
    return auth.verify_id_token


def create_app(
    config: Config | None = None,
    repo: Repo | None = None,
    ai: RecipeAI | None = None,
    notifier: Notifier | None = None,
    verify_token: Callable[[str], dict] | None = None,
    use_default_ai: bool = True,
) -> FastAPI:
    config = config or Config()
    app = FastAPI(title="Meal Planner API", version="0.1.0")

    app.state.config = config
    app.state.repo = repo or _default_repo(config)
    app.state.ai = ai if ai is not None or not use_default_ai else _default_ai(config)
    app.state.verify_token = verify_token or _default_verify_token(config)
    if notifier is None:
        if config.push_enabled:
            _init_firebase(config)
            notifier = FcmNotifier()
        else:
            notifier = LogNotifier()
    app.state.notifier = notifier

    for router in (recipes.router, plans.router, household.router, integrations.router):
        app.include_router(router, prefix="/api")

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app
