"""Request dependencies: who is calling and which household they belong to."""

import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request

from app.ai.base import RecipeAI
from app.config import Config
from app.models import Household
from app.notify import Notifier
from app.repo.base import Repo


def get_repo(request: Request) -> Repo:
    return request.app.state.repo


def get_config(request: Request) -> Config:
    return request.app.state.config


def get_notifier(request: Request) -> Notifier:
    return request.app.state.notifier


def get_optional_ai(request: Request) -> RecipeAI | None:
    return request.app.state.ai


def get_ai(request: Request) -> RecipeAI:
    if request.app.state.ai is None:
        raise HTTPException(503, "AI features are switched off on this server")
    return request.app.state.ai


def _bearer(authorization: str | None) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(401, "Sign in required")
    return token.strip()


def current_household(
    request: Request, authorization: Annotated[str | None, Header()] = None
) -> Household:
    """The household of the signed-in user (Firebase ID token in the Authorization header)."""
    token = _bearer(authorization)
    try:
        claims = request.app.state.verify_token(token)
    except Exception as error:
        raise HTTPException(401, "Your session has expired. Sign in again.") from error

    config: Config = request.app.state.config
    email = str(claims.get("email", "")).lower()
    if config.allowed_emails and (
        email not in config.allowed_emails or not claims.get("email_verified", False)
    ):
        raise HTTPException(403, "This account is not allowed to use this app")
    return request.app.state.repo.household_for_user(claims["uid"], email)


def shortcut_household(
    request: Request, authorization: Annotated[str | None, Header()] = None
) -> Household:
    """The household that owns a Shortcut key (used by Siri and the share sheet)."""
    household = request.app.state.repo.household_by_shortcut_token(_bearer(authorization))
    if household is None:
        raise HTTPException(401, "Unknown Shortcut key")
    return household


def scheduler_only(request: Request, x_job_token: Annotated[str | None, Header()] = None) -> None:
    expected = request.app.state.config.job_token
    if not expected or not secrets.compare_digest(expected, x_job_token or ""):
        raise HTTPException(401, "Not allowed")


CurrentHousehold = Annotated[Household, Depends(current_household)]
ShortcutHousehold = Annotated[Household, Depends(shortcut_household)]
RepoDep = Annotated[Repo, Depends(get_repo)]
AIDep = Annotated[RecipeAI, Depends(get_ai)]
OptionalAIDep = Annotated[RecipeAI | None, Depends(get_optional_ai)]
ConfigDep = Annotated[Config, Depends(get_config)]
NotifierDep = Annotated[Notifier, Depends(get_notifier)]
