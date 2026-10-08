"""Public access must not permit cross-browser lesson access."""
import os
os.environ["KIDSPARK_APP_DATABASE_URL"] = "sqlite:///work/test-sessions.sqlite"
os.environ["KIDSPARK_WORKER_MODE"] = "disabled"

from fastapi.testclient import TestClient
from api.main import app

HEADERS = {"X-KidSpark-Request": "1"}


import pytest


@pytest.fixture(autouse=True)
def isolated_database(monkeypatch, tmp_path):
    from sqlalchemy import create_engine
    from runtime import store
    engine = create_engine(f"sqlite:///{tmp_path / 'sessions.sqlite'}")
    monkeypatch.setattr(store, "engine", engine)
    monkeypatch.setenv("KIDSPARK_WORKER_MODE", "disabled")
    yield
    engine.dispose()


def test_private_anonymous_session_survives_client_recreation():
    with TestClient(app) as client:
        response = client.post("/api/v1/sessions", headers=HEADERS)
        assert response.status_code == 201
        sid = response.json()["session_id"]
        cookies = dict(client.cookies)
        assert client.get(f"/api/v1/sessions/{sid}").status_code == 200
    with TestClient(app) as stranger:
        assert stranger.get(f"/api/v1/sessions/{sid}").status_code == 404
    with TestClient(app) as resumed:
        resumed.cookies.update(cookies)
        assert resumed.get(f"/api/v1/sessions/{sid}").status_code == 200


def test_reject_cross_site_and_empty_upload():
    with TestClient(app) as client:
        assert client.post("/api/v1/sessions").status_code == 403
        sid = client.post("/api/v1/sessions", headers=HEADERS).json()["session_id"]
        assert client.post(f"/api/v1/sessions/{sid}/upload", headers=HEADERS).status_code == 422
        assert client.post(f"/api/v1/sessions/{sid}/confirm-planning", headers=HEADERS).status_code == 409


def test_missing_validation_is_not_approved():
    import pytest
    from agents.orchestrator import _require_validated_build_result
    with pytest.raises(ValueError):
        _require_validated_build_result({"build_plan": {}})


def test_provider_failure_keeps_story_draft(monkeypatch):
    from api import main
    monkeypatch.setattr(main, "provider_configured", lambda: False)
    with TestClient(app) as client:
        sid = client.post("/api/v1/sessions", headers=HEADERS).json()["session_id"]
        response = client.post(f"/api/v1/sessions/{sid}/upload", headers=HEADERS,
                               data={"text": "A saved story about building a bridge."})
        assert response.status_code == 503
        saved = client.get(f"/api/v1/sessions/{sid}").json()
        assert saved["storybook_text"] == "A saved story about building a bridge."
        assert saved["phase"] == "story_upload"


def test_artifact_scope_and_path_traversal():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    with TestClient(app) as client:
        sid = client.post("/api/v1/sessions", headers=HEADERS).json()["session_id"]
        directory = root / "work" / "build_jobs" / sid
        directory.mkdir(parents=True, exist_ok=True)
        sample = directory / "sample.pdf"
        sample.write_bytes(b"%PDF-1.4 local test")
        route = f"/api/v1/sessions/{sid}/artifact"
        try:
            assert client.get(route, params={"path": str(sample)}).status_code == 200
            assert client.get(route, params={"path": str(root / 'README.md')}).status_code == 404
            with TestClient(app) as stranger:
                assert stranger.get(route, params={"path": str(sample)}).status_code == 404
        finally:
            sample.unlink()
            directory.rmdir()


def test_revision_persists_constraints_and_clears_previous_build():
    from hashlib import sha256
    from runtime import store
    with TestClient(app) as client:
        state = client.post("/api/v1/sessions", headers=HEADERS).json()
        sid = state["session_id"]
        identity = sha256(client.cookies.get("kidspark_session").encode()).hexdigest()
        state.update(phase="build_plan", model_preview_result={"context": {"rodin_prompt": "A bridge"}},
                     segment_job_id="old-segments", document_job_id="old-documents",
                     build_result={"build_plan": {}}, document_result={"old": True})
        assert store.save_session(sid, identity, 0, state)
        response = client.post(f"/api/v1/sessions/{sid}/model-preview/refine", headers=HEADERS,
                               json={"refinement": "Widen the supports", "max_validated_blocks": 24,
                                     "max_semantic_segments": 3})
        assert response.status_code == 200, response.text
        revised = client.get(f"/api/v1/sessions/{sid}").json()
        assert revised["phase"] == "model_preview"
        assert revised["build_constraints"]["max_validated_blocks"] == 24
        assert revised["build_constraints"]["max_semantic_segments"] == 3
        for field in ("segment_job_id", "document_job_id", "build_result", "document_result"):
            assert revised[field] is None
        assert client.get(f"/api/v1/sessions/{sid}/segments").status_code == 404


def test_missing_instruction_sequence_cannot_be_confirmed():
    from hashlib import sha256
    from runtime import store
    with TestClient(app) as client:
        state = client.post("/api/v1/sessions", headers=HEADERS).json()
        sid = state["session_id"]
        identity = sha256(client.cookies.get("kidspark_session").encode()).hexdigest()
        state.update(phase="build_plan", build_result={"build_plan": {
            "validated_planner": {"final_claim_valid": True}}})
        assert store.save_session(sid, identity, 0, state)
        response = client.post(f"/api/v1/sessions/{sid}/confirm-build-plan", headers=HEADERS)
        assert response.status_code == 409
        assert "sequence is missing" in response.json()["detail"]


def test_document_revision_preserves_build_and_requires_new_approval():
    from hashlib import sha256
    from build3d import jobs
    from runtime import store
    from sqlalchemy import update
    with TestClient(app) as client:
        state = client.post("/api/v1/sessions", headers=HEADERS).json()
        sid = state["session_id"]
        identity = sha256(client.cookies.get("kidspark_session").encode()).hexdigest()
        previous = jobs.enqueue("documents", sid, {"old": True})
        previous.update(status="complete", result={"lesson_package": {"teacher_plan": {"title": "Bridge"}},
            "document_bundle": {"all_valid": True}})
        with store.engine.begin() as connection:
            connection.execute(update(store.jobs).where(store.jobs.c.id == previous["job_id"]).values(
                status="complete", snapshot=previous))
        plan = {"validated_planner": {"final_claim_valid": True, "instruction_steps": [{"step_number": 1}]}}
        state.update(phase="complete", storybook_text="A bridge story", build_result={"context": {"artifact_label": "bridge"}, "build_plan": plan},
            document_job_id=previous["job_id"], document_result=previous["result"])
        store.save_session(sid, identity, 0, state)
        response = client.post(f"/api/v1/sessions/{sid}/documents/refine", headers=HEADERS,
            json={"notes": "Use shorter student sentences and add a reflection question."})
        assert response.status_code == 200, response.text
        saved = client.get(f"/api/v1/sessions/{sid}").json()
        assert saved["phase"] == "lesson_bundle"
        assert saved["document_result"] is None
        assert saved["build_result"]["build_plan"] == plan
        assert saved["document_job_id"] != previous["job_id"]
        assert saved["document_history"][0]["job_id"] == previous["job_id"]
        assert client.post(f"/api/v1/sessions/{sid}/confirm-documents", headers=HEADERS).status_code == 409


def test_job_controls_are_owner_scoped():
    from build3d import jobs
    with TestClient(app) as client:
        sid = client.post("/api/v1/sessions", headers=HEADERS).json()["session_id"]
        job = jobs.enqueue("model", sid, {"context": {}})
        route = f"/api/v1/sessions/{sid}/jobs/{job['job_id']}/cancel"
        with TestClient(app) as stranger:
            assert stranger.post(route, headers=HEADERS).status_code == 404
        assert client.post(route, headers=HEADERS).json()["status"] == "cancelled"


def test_connection_review_blocks_assessment_approval_until_current_job_reviewed(monkeypatch):
    from agents import orchestrator as workflow
    from models.schemas import SessionState, SessionPhase
    from runtime.context import bind_session
    state = SessionState(session_id="review-test", phase=SessionPhase.segments_connectors,
        segment_job_id="current-build")
    result = {"build_plan": {"validated_planner": {"final_claim_valid": True},
        "validation": {"connector_review_required": True}}}
    monkeypatch.setattr(workflow, "get_session_segments", lambda _: {"status": "complete", "result": result})
    monkeypatch.setattr(workflow, "_segment_job_matches_current_model", lambda *_: True)
    with bind_session(state):
        for review in ({}, {"job_id": "previous-build"}):
            state.connector_review = review
            with pytest.raises(ValueError, match="Review the moving parts"):
                workflow.confirm_session_segments(state.session_id)
            assert state.phase == SessionPhase.segments_connectors
        state.connector_review = {"job_id": "current-build", "notes": "Reviewed"}
        workflow.confirm_session_segments(state.session_id)
        assert state.phase == SessionPhase.build_plan
