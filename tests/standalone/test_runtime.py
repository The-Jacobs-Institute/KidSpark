"""Local persistence, transaction, and external-call isolation regressions."""
import uuid

import pytest
from sqlalchemy import select

from build3d import jobs
from runtime import store


@pytest.fixture(autouse=True)
def database(monkeypatch, tmp_path):
    from sqlalchemy import create_engine
    engine = create_engine(f"sqlite:///{tmp_path / 'runtime.sqlite'}")
    monkeypatch.setattr(store, "engine", engine)
    store.initialize()
    yield
    engine.dispose()


def test_job_dispatch_waits_for_commit_and_is_idempotent(monkeypatch):
    dispatched = []
    monkeypatch.setattr(jobs, "dispatch", dispatched.append)
    sid = str(uuid.uuid4())
    with store.unit_of_work():
        first = jobs.enqueue("model", sid, {"context": {"object": "bridge"}})
        assert dispatched == []
    second = jobs.enqueue("model", sid, {"context": {"object": "bridge"}})
    assert first["job_id"] == second["job_id"]
    assert dispatched == [first["job_id"]]


def test_rollback_never_dispatches_or_leaves_orphan_job(monkeypatch):
    dispatched = []
    monkeypatch.setattr(jobs, "dispatch", dispatched.append)
    with pytest.raises(ValueError), store.unit_of_work():
        job = jobs.enqueue("model", str(uuid.uuid4()), {"context": {}})
        raise ValueError("session revision conflict")
    assert dispatched == []
    assert jobs.snapshot(job["job_id"]) is None


def test_dispatch_failure_preserves_queued_intent(monkeypatch):
    def unavailable(job_id):
        raise OSError("worker unavailable")
    monkeypatch.setattr(jobs, "dispatch", unavailable)
    with store.unit_of_work():
        job = jobs.enqueue("model", str(uuid.uuid4()), {"context": {}})
    assert jobs.snapshot(job["job_id"])["status"] == "queued"


def test_worker_claim_executes_external_boundary_once(monkeypatch):
    from build3d import pipeline
    from runtime.worker import execute
    calls = []
    monkeypatch.setattr(jobs, "dispatch", lambda _: None)
    def generate(context, directory, progress):
        calls.append(context)
        return {"rodin": {"task_uuid": "local-test"}}
    monkeypatch.setattr(pipeline, "create_rodin_preview", generate)
    job = jobs.enqueue("model", str(uuid.uuid4()), {"context": {"object": "bridge"}})
    execute(job["job_id"])
    execute(job["job_id"])
    assert len(calls) == 1
    assert jobs.snapshot(job["job_id"])["status"] == "complete"


def test_session_compare_and_swap_prevents_lost_update():
    sid = str(uuid.uuid4())
    store.insert_session({"session_id": sid}, "owner")
    assert store.save_session(sid, "owner", 0, {"session_id": sid, "value": 1})
    assert not store.save_session(sid, "owner", 0, {"session_id": sid, "value": 2})
    assert store.load_session(sid, "owner")["state"]["value"] == 1
    assert store.load_session(sid, "another-owner") is None
