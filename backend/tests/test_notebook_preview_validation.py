from types import SimpleNamespace

import pytest

from agents import orchestrator
from build3d.pipeline import _merge_validated_outputs, _promote_compact_notebook_physicalization


@pytest.mark.parametrize("connected", [True, False])
def test_budget_compliant_preview_does_not_override_timeout(connected):
    context = {"parts": [{"movement": "spinning"}]}
    notebook = {
        "block_count": 21,
        "segment_count": 3,
        "instruction_steps": [{"image_path": "actual-notebook.png"}],
        "validation": {
            "is_fully_connected": connected,
            "component_count": 1 if connected else 2,
            "connector_candidate_count": 1,
        },
    }
    failed = {
        "build_status": "PLANNER_TIMEOUT",
        "reason": "Search exceeded its time budget.",
        "final_claim_valid": False,
        "instruction_steps": [],
    }
    result = _promote_compact_notebook_physicalization(context, notebook, failed)
    assert result["build_status"] == "PLANNER_TIMEOUT"
    assert result["reason"] == failed["reason"]
    assert result["final_claim_valid"] is False
    assert result["true_build_step_count"] == 0
    assert result["preview_ready"] is True
    merged = _merge_validated_outputs(notebook, result)
    assert merged["instruction_steps"] == notebook["instruction_steps"]
    assert not merged["validation"]["final_claim_valid"]
    with pytest.raises(ValueError, match="not approvable"):
        orchestrator._require_validated_build_result({"build_plan": {"validated_planner": result}})


def test_strict_success_is_unchanged():
    validated = {"build_status": "COMPLETE", "final_claim_valid": True, "true_build_step_count": 14}
    assert _promote_compact_notebook_physicalization({}, {}, validated) is validated
    orchestrator._require_validated_build_result({"build_plan": {"validated_planner": validated}})


def test_legacy_promoted_result_cannot_bypass_document_gate(monkeypatch):
    legacy = {"build_status": "NOTEBOOK_CSP_REVIEW_READY", "final_claim_valid": True}
    session = SimpleNamespace(storybook_text="A story", build_result={"build_plan": {"validated_planner": legacy}})
    monkeypatch.setitem(orchestrator._sessions, "legacy-preview-test", session)
    with pytest.raises(ValueError, match="not approvable"):
        orchestrator.start_session_documents("legacy-preview-test")
