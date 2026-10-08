"""Bounded queue reconciliation and cooperative cancellation with worker leases."""
from datetime import datetime, timedelta, timezone
import os
import uuid

from sqlalchemy import func, select, update
from runtime import store


def setting(name, default):
    return max(1, int(os.getenv(name, str(default))))


def claim(job_id):
    with store.engine.begin() as connection:
        store.scheduler_lock(connection)
        row = connection.execute(select(store.jobs).where(store.jobs.c.id == job_id)).mappings().first()
        if not row or row["status"] != "queued":
            return None
        running = select(func.count()).select_from(store.jobs).where(store.jobs.c.status == "running")
        if connection.execute(running).scalar() >= setting("KIDSPARK_MAX_RUNNING_JOBS", 2):
            return None
        if connection.execute(running.where(store.jobs.c.session_id == row["session_id"])).scalar():
            return None
        job = dict(row["snapshot"])
        job.update(status="running", lease=uuid.uuid4().hex,
                   attempts=int(job.get("attempts", 0)) + 1, error=None)
        connection.execute(update(store.jobs).where(store.jobs.c.id == job_id).values(
            status="running", snapshot=job, updated_at=store.now()))
        return {**row, "snapshot": job}


def reconcile():
    """Re-dispatch queued jobs; fence dead workers before any resumable retry."""
    if os.getenv("KIDSPARK_WORKER_MODE", "local") == "disabled":
        return
    from build3d.jobs import safe_dispatch
    timestamp = datetime.now(timezone.utc)
    stale = (timestamp - timedelta(seconds=setting("KIDSPARK_JOB_LEASE_SECONDS", 180))).isoformat()
    retry = (timestamp - timedelta(seconds=60)).isoformat()
    dispatch = []
    with store.engine.begin() as connection:
        store.scheduler_lock(connection)
        for row in connection.execute(select(store.jobs).where(
                store.jobs.c.status == "running", store.jobs.c.updated_at < stale)).mappings():
            job = dict(row["snapshot"])
            uncertain = connection.execute(select(func.count()).select_from(store.checkpoints).where(
                store.checkpoints.c.job_id == row["id"], store.checkpoints.c.state != "complete")).scalar()
            can_resume = (job.get("checkpoint_version") == 1 and not uncertain
                          and job.get("attempts", 1) < setting("KIDSPARK_MAX_JOB_ATTEMPTS", 3))
            job.update(status="queued" if can_resume else "error", lease=None,
                       stage="Resuming saved progress" if can_resume else "Needs attention",
                       error=None if can_resume else "recovery_required",
                       message="Resuming from saved progress." if can_resume else
                       "Processing was interrupted. Saved results are safe; an operator must check the previous request before retrying.")
            connection.execute(update(store.jobs).where(store.jobs.c.id == row["id"]).values(
                status=job["status"], snapshot=job, updated_at=store.now()))
        running_sessions = set(connection.execute(select(store.jobs.c.session_id).where(
            store.jobs.c.status == "running")).scalars())
        slots = max(0, setting("KIDSPARK_MAX_RUNNING_JOBS", 2) - len(running_sessions))
        for row in connection.execute(select(store.jobs).where(store.jobs.c.status == "queued").order_by(
                store.jobs.c.updated_at).limit(setting("KIDSPARK_MAX_PENDING_JOBS", 20))).mappings():
            job = dict(row["snapshot"])
            if slots <= 0 or row["session_id"] in running_sessions:
                continue
            if job.get("last_dispatched_at", "") > retry:
                continue
            if job.get("dispatch_attempts", 0) >= 10:
                job.update(status="error", error="dispatch_failed", stage="Needs attention",
                           message="The processing service could not start. Your lesson is saved; please contact the project team.")
            else:
                job["last_dispatched_at"] = store.now()
                job["dispatch_attempts"] = job.get("dispatch_attempts", 0) + 1
                dispatch.append(row["id"])
                slots -= 1
            connection.execute(update(store.jobs).where(store.jobs.c.id == row["id"]).values(
                status=job["status"], snapshot=job))
    for job_id in dispatch:
        safe_dispatch(job_id)


def cancel(job_id, session_id):
    with store.engine.begin() as connection:
        store.scheduler_lock(connection)
        row = connection.execute(select(store.jobs).where(
            store.jobs.c.id == job_id, store.jobs.c.session_id == session_id)).mappings().first()
        if not row:
            raise ValueError("Job not found")
        job = dict(row["snapshot"])
        if row["status"] in {"running", "queued"}:
            job.update(status="cancelled", stage="Cancelled", lease=None,
                       message="Stopped locally. A request already sent to an external provider may still finish and incur a charge.")
            connection.execute(update(store.jobs).where(store.jobs.c.id == job_id).values(
                status="cancelled", snapshot=job, updated_at=store.now()))
        return job


def retryable(connection, job):
    if job.get("checkpoint_version") != 1 or job.get("attempts", 0) >= setting("KIDSPARK_MAX_JOB_ATTEMPTS", 3):
        return False
    return not connection.execute(select(func.count()).select_from(store.checkpoints).where(
        store.checkpoints.c.job_id == job["job_id"], store.checkpoints.c.state != "complete")).scalar()


def resume(job_id, session_id):
    from build3d.jobs import safe_dispatch
    with store.engine.begin() as connection:
        store.scheduler_lock(connection)
        row = connection.execute(select(store.jobs).where(
            store.jobs.c.id == job_id, store.jobs.c.session_id == session_id)).mappings().first()
        if not row or row["status"] not in {"error", "cancelled"}:
            raise ValueError("Only stopped jobs can be resumed.")
        job = dict(row["snapshot"])
        if not retryable(connection, job):
            raise ValueError("An operator must check this job before another provider request is made.")
        pending = select(func.count()).select_from(store.jobs).where(store.jobs.c.status.in_(["queued", "running"]))
        if connection.execute(pending.where(store.jobs.c.session_id == session_id)).scalar():
            raise ValueError("This lesson already has a job in progress.")
        if connection.execute(pending).scalar() >= setting("KIDSPARK_MAX_PENDING_JOBS", 20):
            raise ValueError("The queue is full. Please try again shortly.")
        job.update(status="queued", lease=None, error=None, stage="Resuming saved progress",
                   message="Resuming from saved progress", last_dispatched_at="", dispatch_attempts=0)
        connection.execute(update(store.jobs).where(store.jobs.c.id == job_id).values(
            status="queued", snapshot=job, updated_at=store.now()))
    safe_dispatch(job_id)
    return job
