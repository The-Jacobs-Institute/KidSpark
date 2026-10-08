"""Small transactional store, isolated from the read-only curriculum database.

Session writes use optimistic concurrency. Jobs are persisted before dispatch so
a failed process launch does not erase a teacher's request.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import JSON, Column, Integer, MetaData, String, Table, create_engine, select, update

Path("work").mkdir(exist_ok=True)
engine = create_engine(
    os.getenv("KIDSPARK_APP_DATABASE_URL", "sqlite:///work/kidspark.sqlite"),
    pool_pre_ping=True,
)
metadata = MetaData()
_transaction = ContextVar("workflow_transaction", default=None)
_callbacks = ContextVar("commit_callbacks", default=None)


@contextmanager
def unit_of_work():
    """Commit session and dispatch intent together, then launch the worker."""
    callbacks = []
    with engine.begin() as connection:
        token = _transaction.set(connection)
        callback_token = _callbacks.set(callbacks)
        try:
            yield
        finally:
            _transaction.reset(token)
            _callbacks.reset(callback_token)
    for callback in callbacks:
        callback()


@contextmanager
def write():
    connection = _transaction.get()
    if connection is not None:
        yield connection
    else:
        with engine.begin() as connection:
            yield connection


def after_commit(callback):
    callbacks = _callbacks.get()
    if callbacks is None:
        callback()
    else:
        callbacks.append(callback)
sessions = Table(
    "teacher_session", metadata,
    Column("id", String, primary_key=True),
    Column("owner", String, nullable=False, index=True),
    Column("revision", Integer, nullable=False, default=0),
    Column("state", JSON, nullable=False),
    Column("updated_at", String, nullable=False),
)
jobs = Table(
    "workflow_job", metadata,
    Column("id", String, primary_key=True),
    Column("session_id", String, nullable=False, index=True),
    Column("kind", String, nullable=False),
    Column("status", String, nullable=False, index=True),
    Column("payload", JSON, nullable=False),
    Column("snapshot", JSON, nullable=False),
    Column("updated_at", String, nullable=False),
)
controls = Table(
    "workflow_control", metadata,
    Column("id", String, primary_key=True),
    Column("revision", Integer, nullable=False, default=0),
)
checkpoints = Table(
    "workflow_checkpoint", metadata,
    Column("id", String, primary_key=True),
    Column("job_id", String, nullable=False, index=True),
    Column("state", String, nullable=False),
    Column("result", JSON, nullable=True),
)
schema_versions = Table(
    "application_schema_version", metadata,
    Column("version", Integer, primary_key=True),
    Column("applied_at", String, nullable=False),
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def initialize() -> None:
    """Bootstrap local SQLite; shared PostgreSQL requires an explicit migration."""
    if os.getenv("K_SERVICE") or os.getenv("CLOUD_RUN_JOB"):
        if engine.dialect.name != "postgresql" or not os.getenv("KIDSPARK_ARTIFACT_BUCKET"):
            raise RuntimeError("Cloud execution requires PostgreSQL application storage and a private artifact bucket.")
        if os.getenv("K_SERVICE") and (os.getenv("KIDSPARK_WORKER_MODE") != "cloud" or not os.getenv("KIDSPARK_WORKER_JOB")):
            raise RuntimeError("Cloud web service requires the dedicated Cloud Run worker job.")
    if engine.dialect.name != "sqlite":
        with engine.connect() as connection:
            version = connection.execute(select(schema_versions.c.version)).scalar()
            if version != 1:
                raise RuntimeError("Run python -m runtime.migrate before starting the application.")
        return
    migrate()


def migrate() -> None:
    """Additive application schema v1, including upgrades from the local prototype."""
    metadata.create_all(engine)
    with engine.begin() as connection:
        if connection.dialect.name == "sqlite":
            from sqlalchemy.dialects.sqlite import insert
        elif connection.dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert
        else:
            raise RuntimeError("Use SQLite or PostgreSQL for application storage.")
        connection.execute(insert(controls).values(id="scheduler", revision=0).on_conflict_do_nothing())
        connection.execute(insert(schema_versions).values(version=1, applied_at=now()).on_conflict_do_nothing())


def scheduler_lock(connection):
    """Serialize capacity checks/claims on both SQLite and PostgreSQL."""
    connection.execute(update(controls).where(controls.c.id == "scheduler").values(
        revision=controls.c.revision + 1))


def load_session(session_id: str, owner: str):
    with engine.connect() as connection:
        return connection.execute(select(sessions).where(
            sessions.c.id == session_id, sessions.c.owner == owner,
        )).mappings().first()


def insert_session(state: dict, owner: str) -> None:
    with engine.begin() as connection:
        connection.execute(sessions.insert().values(
            id=state["session_id"], owner=owner, revision=0, state=state, updated_at=now(),
        ))


def save_session(session_id: str, owner: str, revision: int, state: dict) -> bool:
    with write() as connection:
        result = connection.execute(update(sessions).where(
            sessions.c.id == session_id, sessions.c.owner == owner,
            sessions.c.revision == revision,
        ).values(state=state, revision=revision + 1, updated_at=now()))
        return result.rowcount == 1
