"""Request-local compatibility boundary for the migrated domain orchestrator.

No teacher state lives in a process-global dictionary. The API loads a durable
record, binds it for domain calls, and saves it with a revision check.
"""
from contextlib import contextmanager
from contextvars import ContextVar

_state = ContextVar("teacher_state", default=None)


class SessionScope:
    def __getitem__(self, key):
        session = _state.get()
        if session is None or session.session_id != key:
            raise KeyError(key)
        return session

    def get(self, key):
        try:
            return self[key]
        except KeyError:
            return None

    def __setitem__(self, key, value):
        raise RuntimeError("Create sessions through the durable API store.")


@contextmanager
def bind_session(session):
    token = _state.set(session)
    try:
        yield session
    finally:
        _state.reset(token)
