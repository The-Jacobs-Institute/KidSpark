"""Persist paid-call outcomes; uncertain submissions are never blindly replayed."""
from contextlib import contextmanager
from contextvars import ContextVar
from hashlib import sha256
import json

from sqlalchemy import select, update
from runtime import store

_job = ContextVar("checkpoint_job", default=None)


class UncertainSubmission(RuntimeError):
    """A previous request may have reached the provider but has no saved response."""


@contextmanager
def for_job(job_id, lease=None):
    token = _job.set((job_id, lease))
    try:
        yield
    finally:
        _job.reset(token)


def call(operation, inputs, invoke):
    execution = _job.get()
    if execution is None:
        return invoke()
    job_id, lease = execution
    key = sha256(json.dumps([job_id, operation, inputs], sort_keys=True, default=str).encode()).hexdigest()
    with store.engine.begin() as connection:
        store.scheduler_lock(connection)
        active = connection.execute(select(store.jobs).where(store.jobs.c.id == job_id)).mappings().first()
        if not active or active["status"] != "running" or (lease and active["snapshot"].get("lease") != lease):
            raise RuntimeError("Job is no longer running")
        previous = connection.execute(select(store.checkpoints).where(store.checkpoints.c.id == key)).mappings().first()
        if previous:
            if previous["state"] == "complete":
                return previous["result"]
            raise UncertainSubmission("Provider response is unknown; operator reconciliation is required.")
        connection.execute(store.checkpoints.insert().values(id=key, job_id=job_id, state="submitted"))
    result = invoke()
    with store.engine.begin() as connection:
        connection.execute(update(store.checkpoints).where(store.checkpoints.c.id == key).values(
            state="complete", result=result))
    return result
