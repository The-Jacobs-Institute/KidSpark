"""Legacy domain unit tests use a test-only session mapping.

Standalone API tests exercise the real durable store and request-local scope.
"""
import pytest


@pytest.fixture(autouse=True)
def isolated_domain_sessions(monkeypatch):
    from agents import orchestrator
    monkeypatch.setattr(orchestrator, "_sessions", {})
