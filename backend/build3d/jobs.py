"""Durable jobs with deterministic identities and isolated worker execution."""
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

from sqlalchemy import func, select
from runtime import store

ROOT = Path(__file__).resolve().parents[2]
GENERATED_ROOT = ROOT / "work" / "build_jobs"


def enqueue(kind, session_id, payload):
    material = json.dumps([session_id, kind, payload], sort_keys=True, default=str)
    job_id = sha256(material.encode()).hexdigest()[:32]
    existing = snapshot(job_id)
    if existing:
        return existing
    job = {"job_id": job_id, "session_id": session_id, "status": "queued",
           "stage": "Queued", "progress": 0, "message": "Waiting to start",
           "events": [], "result": None, "error": None, "created_at": store.now(), "checkpoint_version": 1}
    with store.write() as connection:
        store.scheduler_lock(connection)
        existing_row = connection.execute(select(store.jobs.c.snapshot).where(store.jobs.c.id == job_id)).first()
        if existing_row:
            return existing_row[0]
        pending = select(func.count()).select_from(store.jobs).where(store.jobs.c.status.in_(["queued", "running"]))
        if connection.execute(pending.where(store.jobs.c.session_id == session_id)).scalar():
            raise ValueError("This lesson already has a job in progress. Wait or cancel it before starting another.")
        from runtime.recovery import setting
        if connection.execute(pending).scalar() >= setting("KIDSPARK_MAX_PENDING_JOBS", 20):
            raise ValueError("The processing queue is full. Your lesson is saved; please try again shortly.")
        # Native conflict handling keeps the insert in the outer transaction.
        # A first-write SAVEPOINT can commit early under SQLite's legacy mode.
        if connection.dialect.name == "sqlite":
            from sqlalchemy.dialects.sqlite import insert
        elif connection.dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert
        else:
            raise ValueError("Use SQLite locally or PostgreSQL for shared runtime storage.")
        inserted = connection.execute(insert(store.jobs).values(
            id=job_id, session_id=session_id, kind=kind, status="queued",
            payload=payload, snapshot=job, updated_at=store.now(),
        ).on_conflict_do_nothing(index_elements=["id"]))
        if inserted.rowcount != 1:
            return connection.execute(select(store.jobs.c.snapshot).where(
                store.jobs.c.id == job_id)).scalar_one()
    store.after_commit(lambda: safe_dispatch(job_id))
    return job


def safe_dispatch(job_id):
    try:
        dispatch(job_id)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Worker dispatch failed for %s", job_id)


def dispatch(job_id):
    mode = os.getenv("KIDSPARK_WORKER_MODE", "local")
    if mode == "disabled":
        return
    if mode == "cloud":
        from google.cloud import run_v2
        client = run_v2.JobsClient()
        client.run_job(request=run_v2.RunJobRequest(
            name=os.environ["KIDSPARK_WORKER_JOB"],
            overrides=run_v2.RunJobRequest.Overrides(container_overrides=[
                run_v2.RunJobRequest.Overrides.ContainerOverride(args=["python", "-m", "runtime.worker", job_id])
            ]),
        ))
        return
    log_dir = ROOT / "work" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / f"{job_id}.log").open("ab") as log:
        subprocess.Popen([sys.executable, "-m", "runtime.worker", job_id], cwd=ROOT,
                         stdout=log, stderr=log,
                         creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)


def snapshot(job_id):
    with store.engine.connect() as connection:
        row = connection.execute(select(store.jobs.c.snapshot).where(store.jobs.c.id == job_id)).first()
        if not row:
            return None
        job = dict(row[0])
        if job["status"] in {"error", "cancelled"}:
            from runtime.recovery import retryable
            job["retryable"] = retryable(connection, job)
        return job


def start_model_preview_job(context, session_id):
    return enqueue("model", session_id, {"context": context})


def start_segments_job(context, rodin_task_uuid, rodin_files, session_id):
    return enqueue("segments", session_id, {"context": context, "rodin_task_uuid": rodin_task_uuid,
                                           "rodin_files": rodin_files})


def start_document_job(story_text, context, build_plan, session_id):
    return enqueue("documents", session_id, {"story_text": story_text, "context": context,
                                             "build_plan": build_plan})


def start_build_job(*args, **kwargs):
    raise ValueError("Use the teacher-reviewed staged workflow.")
