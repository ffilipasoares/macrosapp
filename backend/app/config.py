"""Configuration read from environment variables."""

import os
from dataclasses import dataclass, field


def _csv(value: str) -> list[str]:
    return [part.strip().lower() for part in value.split(",") if part.strip()]


@dataclass(frozen=True)
class Config:
    project_id: str = field(
        default_factory=lambda: os.getenv("GOOGLE_CLOUD_PROJECT", "demo-mealplan")
    )
    # Only these Google accounts may sign in. Empty means anyone with an account.
    allowed_emails: list[str] = field(default_factory=lambda: _csv(os.getenv("ALLOWED_EMAILS", "")))
    # Shared secret that Cloud Scheduler sends when it triggers the weekly job.
    job_token: str = field(default_factory=lambda: os.getenv("JOB_TOKEN", ""))
    # "gemini" in production, "fake" for local development, "none" to switch AI off.
    ai_provider: str = field(default_factory=lambda: os.getenv("AI_PROVIDER", "gemini"))
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
    gemini_location: str = field(
        default_factory=lambda: os.getenv("GEMINI_LOCATION", "europe-west1")
    )
    # Public address of the web app, used as the link in push notifications.
    app_url: str = field(default_factory=lambda: os.getenv("APP_URL", ""))
    push_enabled: bool = field(default_factory=lambda: os.getenv("PUSH_ENABLED", "true") == "true")
