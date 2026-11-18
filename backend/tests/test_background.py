import base64
import json
from datetime import timedelta

from fastapi.testclient import TestClient

from app import services
from app.ai.fake import FakeRecipeAI
from app.config import Config
from app.main import create_app
from app.models import now
from app.notify import LogNotifier
from app.repo.memory import MemoryRepo
from app.tasks import CloudTasksQueue, PlanJob, QueueError

AUTH = {"Authorization": "Bearer ana"}
JOB = {"X-Job-Token": "job-secret"}
WEEK = "2026-11-16"


class RecordingQueue:
    def __init__(self, fail=False):
        self.jobs, self.fail = [], fail

    def enqueue(self, job):
        if self.fail:
            raise QueueError("Could not queue the plan (error 403).")
        self.jobs.append(job)


def make(queue):
    repo = MemoryRepo()
    client = TestClient(
        create_app(
            config=Config(push_enabled=False, job_token="job-secret"),
            repo=repo,
            ai=FakeRecipeAI(),
            notifier=LogNotifier(),
            verify_token=lambda t: {"uid": t, "email": "a@example.com", "email_verified": True},
            queue=queue,
        )
    )
    for n in range(8):
        body = {"title": f"Dish {n}", "ingredients": [{"name": "carrot", "quantity": 1}]}
        client.post("/api/recipes", json=body, headers=AUTH)
    household_id = client.get("/api/me", headers=AUTH).json()["household_id"]
    return client, repo, household_id


def test_generating_answers_at_once_and_the_job_makes_the_plan():
    queue = RecordingQueue()
    client, repo, household_id = make(queue)
    first = client.post(f"/api/plans/{WEEK}/generate", headers=AUTH)
    assert first.status_code == 200
    plan = first.json()
    assert plan["generating_since"] and plan["meals"] == {}
    # Asking again while it runs queues nothing more.
    client.post(f"/api/plans/{WEEK}/generate", headers=AUTH)
    assert len(queue.jobs) == 1
    job = queue.jobs[0]
    assert (job.household_id, job.week_id, job.mode) == (household_id, WEEK, "generate")
    # Cloud Tasks calls the job route, which needs the job token.
    assert client.post("/api/jobs/plan", json=job.model_dump()).status_code == 401
    assert client.post("/api/jobs/plan", json=job.model_dump(), headers=JOB).status_code == 200
    done = client.get(f"/api/plans/{WEEK}", headers=AUTH).json()
    assert done["meals"] and done["generating_since"] is None


def test_a_failed_job_is_kept_on_the_week_and_can_be_retried(monkeypatch):
    queue = RecordingQueue()
    client, repo, household_id = make(queue)
    client.post(f"/api/plans/{WEEK}/generate", headers=AUTH)

    def broken(*args, **kwargs):
        raise RuntimeError("Gemini is down")

    monkeypatch.setattr(services, "generate_plan", broken)
    client.post("/api/jobs/plan", json=queue.jobs[0].model_dump(), headers=JOB)
    plan = client.get(f"/api/plans/{WEEK}", headers=AUTH).json()
    assert plan["generating_since"] is None
    assert (
        plan["generation_error"] == "The plan could not be made this time. Try again in a minute."
    )
    client.post(f"/api/plans/{WEEK}/generate", headers=AUTH)
    assert len(queue.jobs) == 2


def test_a_job_that_never_finished_does_not_block_a_new_one():
    queue = RecordingQueue()
    client, repo, household_id = make(queue)
    client.post(f"/api/plans/{WEEK}/generate", headers=AUTH)
    plan = repo.get_plan(household_id, WEEK)
    plan.generating_since = now() - timedelta(minutes=20)
    repo.save_plan(household_id, plan)
    client.post(f"/api/plans/{WEEK}/generate", headers=AUTH)
    assert len(queue.jobs) == 2


def test_when_the_queue_refuses_the_app_says_so():
    client, repo, household_id = make(RecordingQueue(fail=True))
    response = client.post(f"/api/plans/{WEEK}/generate", headers=AUTH)
    assert response.status_code == 503
    assert repo.get_plan(household_id, WEEK).generation_error.startswith("Could not queue")


def test_the_weekly_job_queues_one_plan_per_household_and_notifies_when_done():
    queue = RecordingQueue()
    client, repo, household_id = make(queue)
    client.post("/api/devices", json={"token": "device-token-123"}, headers=AUTH)
    from datetime import date

    notifier = LogNotifier()
    result = services.run_weekly_job(repo, None, notifier, "", date(2026, 11, 13), queue=queue)
    assert result["generated"] == 1 and notifier.sent == []
    job = queue.jobs[0]
    assert job.week_id == WEEK and job.notify
    # A second hourly run while it is still being made does nothing.
    services.run_weekly_job(repo, None, notifier, "", date(2026, 11, 13), queue=queue)
    assert len(queue.jobs) == 1
    services.run_plan_job(repo, None, None, notifier, "", job)
    assert len(notifier.sent) == 1 and repo.get_plan(household_id, WEEK).meals


def test_cloud_tasks_gets_the_job_for_the_backend_with_the_token():
    sent = {}

    class Session:
        def post(self, url, json, timeout):
            sent.update(url=url, task=json)
            return type("Response", (), {"status_code": 200, "text": ""})()

    queue = CloudTasksQueue(
        "projects/p/locations/europe-west1/queues/plans", "https://api.run.app", "tok"
    )
    queue._session = Session()
    queue.enqueue(PlanJob(household_id="h1", week_id=WEEK))
    assert (
        sent["url"]
        == "https://cloudtasks.googleapis.com/v2/projects/p/locations/europe-west1/queues/plans/tasks"
    )
    request = sent["task"]["task"]["httpRequest"]
    assert request["url"] == "https://api.run.app/api/jobs/plan"
    assert request["headers"]["X-Job-Token"] == "tok"
    assert json.loads(base64.b64decode(request["body"])) == {
        "household_id": "h1",
        "week_id": WEEK,
        "mode": "generate",
        "notify": False,
    }
