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
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-3.5-flash"))
    gemini_location: str = field(default_factory=lambda: os.getenv("GEMINI_LOCATION", "global"))
    # Public address of the web app, used as the link in push notifications.
    app_url: str = field(default_factory=lambda: os.getenv("APP_URL", ""))
    # Firebase Storage bucket (e.g. "PROJECT.firebasestorage.app") for copies of web photos.
    # Empty means web photos are shown from their original address instead.
    storage_bucket: str = field(default_factory=lambda: os.getenv("STORAGE_BUCKET", ""))
    # How long plan generation may search the web. Through Firebase Hosting a request
    # must finish within 60 seconds, so the default is 50. When the app calls Cloud Run
    # directly (web/.env: VITE_API_URL), set it higher, e.g. 100.
    web_search_seconds: float = field(
        default_factory=lambda: float(os.getenv("WEB_SEARCH_SECONDS", "50"))
    )
    # Web addresses allowed to call the API directly, comma-separated. Defaults to APP_URL.
    cors_origins: list[str] = field(
        default_factory=lambda: [
            origin.strip().rstrip("/")
            for origin in (os.getenv("CORS_ORIGINS") or os.getenv("APP_URL", "")).split(",")
            if origin.strip()
        ]
    )
    push_enabled: bool = field(default_factory=lambda: os.getenv("PUSH_ENABLED", "true") == "true")
    # Plans are made in the background through this Cloud Tasks queue, e.g.
    # "projects/PROJECT/locations/europe-west1/queues/plans", which calls the backend at
    # TASKS_URL (its Cloud Run address, not the web.app one). Without them, a plan is
    # made within the request, as before.
    tasks_queue: str = field(default_factory=lambda: os.getenv("TASKS_QUEUE", ""))
    tasks_url: str = field(default_factory=lambda: os.getenv("TASKS_URL", "").rstrip("/"))
