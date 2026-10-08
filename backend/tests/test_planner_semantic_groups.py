import numpy as np
import pytest
from build3d.notebook_outputs import load_obj_segments
from build3d.validated_planner_adapter import _group_planner_obj
from build3d.validated_planner_adapter import _normalize_result


def test_grouping_preserves_geometry_and_separates_movement(tmp_path):
    obj = tmp_path / 'source.obj'
    obj.write_text('v 0 0 0\nv 1 0 0\nv 0 1 0\nv 0 0 1\n'
                   'o rotor\nf 1 2 3\no body\nf 1 2 4\no trim\nf 1 3 4\n')
    rows = [{'label': 'propeller', 'movement': 'spinning', 'source_segment_ids': [1]},
            {'label': 'body', 'movement': 'static', 'source_segment_ids': [2, 3]}]
    grouped, mapped = _group_planner_obj(obj, rows, tmp_path)
    vertices, segments = load_obj_segments(grouped)
    original_vertices, original_segments = load_obj_segments(obj)
    assert np.array_equal(vertices, original_vertices)
    assert [face for segment in segments for face in segment.faces] == [
        face for segment in original_segments for face in segment.faces]
    assert len(segments) == 2
    assert mapped[0]['movement'] == 'spinning'
    assert mapped[1]['source_segment_ids'] == [2]
    assert mapped[1]['original_source_segment_ids'] == [2, 3]
    assert rows[1]['source_segment_ids'] == [2, 3]


@pytest.mark.parametrize('groups', [[[1], [1, 2]], [[1]], [[1, 2], []]])
def test_grouping_rejects_duplicate_missing_or_empty_regions(tmp_path, groups):
    obj = tmp_path / 'source.obj'
    obj.write_text('v 0 0 0\nv 1 0 0\nv 0 1 0\no a\nf 1 2 3\no b\nf 3 2 1\n')
    with pytest.raises(ValueError):
        _group_planner_obj(obj, [{'source_segment_ids': group} for group in groups], tmp_path)


def test_disconnected_preflight_is_recoverable_but_never_valid(tmp_path):
    (tmp_path / 'structural_contact_preflight.json').write_text('{"status": "NO_STRUCTURAL_CONTACTS"}')
    result = _normalize_result({'engine_returncode': 1, 'final_claim_valid': False}, tmp_path)
    assert result['build_status'] == 'NEEDS_SIMPLER_MODEL'
    assert not result['final_claim_valid']


def test_ledger_mismatch_cannot_be_approved(tmp_path):
    (tmp_path / 'inventory_validation.json').write_text(
        '{"valid": false, "ledger_mismatches": {"rotation_block": {"ledger_committed": 1, "recount": 0}}}')
    result = _normalize_result({'engine_returncode': 1, 'final_claim_valid': False}, tmp_path)
    assert result['build_status'] == 'VALIDATED_PLANNER_ERROR'
    assert 'ledger' in result['reason']
    assert not result['final_claim_valid']
