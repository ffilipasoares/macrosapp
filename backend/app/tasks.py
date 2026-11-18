"""Plans are made in the background: the request only queues the work.

In production a Cloud Tasks queue calls the backend's job route, which can run for
minutes (Firebase Hosting would stop a request after one). Locally and in tests the
work runs straight away, within the request.
"""

import base64
import json
import logging
from collections.abc import Callable
from typing import Literal, Protocol

from pydantic import BaseModel

log = logging.getLogger(__name__)


class PlanJob(BaseModel):
    household_id: str
    week_id: str
    mode: Literal["generate", "apply_diets"] = "generate"
    notify: bool = False  # tell the household when it is ready (the weekly job)


class JobQueue(Protocol):
    def enqueue(self, job: PlanJob) -> None: ...


class QueueError(Exception):
    pass


class InlineQueue:
    """Runs the job at once, in the request. For local use and tests."""

    def __init__(self, runner: Callable[[PlanJob], None]) -> None:
        self.runner = runner

    def enqueue(self, job: PlanJob) -> None:
        self.runner(job)


class CloudTasksQueue:
    """Adds an HTTP task that calls POST {target}/api/jobs/plan with the job token."""

    def __init__(self, queue: str, target_url: str, job_token: str) -> None:
        self.queue, self.target_url, self.job_token = queue, target_url, job_token
        self._session = None

    def _authorized(self):
        if self._session is None:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession

            credentials, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            self._session = AuthorizedSession(credentials)
        return self._session

    def enqueue(self, job: PlanJob) -> None:
        body = base64.b64encode(json.dumps(job.model_dump()).encode()).decode()
        task = {
            "task": {
                # Long enough for the slowest plan; Cloud Run's own timeout must allow it too.
                "dispatchDeadline": "900s",
                "httpRequest": {
                    "httpMethod": "POST",
                    "url": f"{self.target_url}/api/jobs/plan",
                    "headers": {"Content-Type": "application/json", "X-Job-Token": self.job_token},
                    "body": body,
                },
            }
        }
        try:
            response = self._authorized().post(
                f"https://cloudtasks.googleapis.com/v2/{self.queue}/tasks", json=task, timeout=20
            )
        except Exception as error:  # network or credentials
            raise QueueError(f"Could not queue the plan: {error}") from error
        if response.status_code >= 300:
            log.error("Cloud Tasks refused the task: %s %s", response.status_code, response.text)
            raise QueueError(f"Could not queue the plan (error {response.status_code}).")
