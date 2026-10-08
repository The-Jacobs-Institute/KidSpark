"""Recovery never replays an uncertain paid call or revives cancelled output."""
from datetime import datetime, timedelta, timezone
import uuid

import pytest
from sqlalchemy import create_engine, update
from build3d import jobs
from runtime import checkpoints, recovery, store


@pytest.fixture(autouse=True)
def database(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'jobs.sqlite'}")
    monkeypatch.setattr(store, "engine", engine)
    monkeypatch.setattr(jobs, "dispatch", lambda _: None)
    monkeypatch.setenv("KIDSPARK_WORKER_MODE", "local")
    store.initialize()
    yield
    engine.dispose()


def job():
    return jobs.enqueue("model", str(uuid.uuid4()), {"context": {}})


def expire(job_id):
    with store.engine.begin() as connection:
        connection.execute(update(store.jobs).where(store.jobs.c.id == job_id).values(
            updated_at=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()))


def test_completed_paid_submission_is_reused():
    value = job()
    claimed = recovery.claim(value["job_id"])
    calls = []
    with checkpoints.for_job(value["job_id"], claimed["snapshot"]["lease"]):
        for _ in range(2):
            assert checkpoints.call("rodin", {"prompt": "bridge"}, lambda: calls.append(1) or {"uuid": "paid-task"}) == {"uuid": "paid-task"}
    assert calls == [1]


def test_uncertain_request_never_replays():
    value = job()
    recovery.claim(value["job_id"])
    def interrupted():
        raise TimeoutError("lost response")
    with checkpoints.for_job(value["job_id"]):
        with pytest.raises(TimeoutError):
            checkpoints.call("rodin", {}, interrupted)
        with pytest.raises(checkpoints.UncertainSubmission):
            checkpoints.call("rodin", {}, lambda: pytest.fail("paid call repeated"))
    expire(value["job_id"])
    recovery.reconcile()
    assert jobs.snapshot(value["job_id"])["status"] == "error"
    assert jobs.snapshot(value["job_id"])["retryable"] is False
    with pytest.raises(ValueError):
        recovery.resume(value["job_id"], value["session_id"])


def test_stale_worker_resumes_with_new_lease_and_bounded_attempts(monkeypatch):
    monkeypatch.setenv("KIDSPARK_MAX_JOB_ATTEMPTS", "2")
    value = job()
    first = recovery.claim(value["job_id"])
    expire(value["job_id"])
    recovery.reconcile()
    assert jobs.snapshot(value["job_id"])["status"] == "queued"
    second = recovery.claim(value["job_id"])
    assert second["snapshot"]["lease"] != first["snapshot"]["lease"]
    with checkpoints.for_job(value["job_id"], first["snapshot"]["lease"]), pytest.raises(RuntimeError):
        checkpoints.call("old-worker", {}, lambda: pytest.fail("stale worker called provider"))
    expire(value["job_id"])
    recovery.reconcile()
    assert jobs.snapshot(value["job_id"])["status"] == "error"


def test_legacy_uncheckpointed_job_does_not_autoreplay():
    value = job()
    recovery.claim(value["job_id"])
    saved = jobs.snapshot(value["job_id"])
    saved.pop("checkpoint_version")
    with store.engine.begin() as connection:
        connection.execute(update(store.jobs).where(store.jobs.c.id == value["job_id"]).values(snapshot=saved))
    expire(value["job_id"])
    recovery.reconcile()
    assert jobs.snapshot(value["job_id"])["error"] == "recovery_required"


def test_running_and_queue_limits(monkeypatch):
    monkeypatch.setenv("KIDSPARK_MAX_RUNNING_JOBS", "1")
    monkeypatch.setenv("KIDSPARK_MAX_PENDING_JOBS", "2")
    first, second = job(), job()
    assert recovery.claim(first["job_id"])
    assert recovery.claim(second["job_id"]) is None
    with pytest.raises(ValueError, match="queue is full"):
        job()
    with pytest.raises(ValueError, match="already has a job"):
        jobs.enqueue("documents", first["session_id"], {})
    recovery.cancel(first["job_id"], first["session_id"])
    assert recovery.claim(second["job_id"])


def test_cancellation_cannot_be_overwritten_by_worker(monkeypatch):
    from build3d import pipeline
    from runtime.worker import execute
    value = job()
    def provider(*args):
        recovery.cancel(value["job_id"], value["session_id"])
        return {"unexpected": "must not become complete"}
    monkeypatch.setattr(pipeline, "create_rodin_preview", provider)
    execute(value["job_id"])
    assert jobs.snapshot(value["job_id"])["status"] == "cancelled"
    assert jobs.snapshot(value["job_id"])["result"] is None


def test_resume_keeps_same_job_and_checkpoints():
    value = job()
    recovery.cancel(value["job_id"], value["session_id"])
    resumed = recovery.resume(value["job_id"], value["session_id"])
    assert resumed["job_id"] == value["job_id"]
    assert resumed["status"] == "queued"
    with pytest.raises(ValueError):
        recovery.cancel(value["job_id"], "another-lesson")


def test_reconcile_queue_does_not_spend_retries_when_capacity_full(monkeypatch):
    monkeypatch.setenv("KIDSPARK_MAX_RUNNING_JOBS", "1")
    first, second = job(), job()
    recovery.claim(first["job_id"])
    for _ in range(12):
        recovery.reconcile()
    queued = jobs.snapshot(second["job_id"])
    assert queued["status"] == "queued"
    assert queued.get("dispatch_attempts", 0) == 0
