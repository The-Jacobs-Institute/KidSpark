from pathlib import Path
from build3d import pipeline


def test_strict_recovery_uses_preview_grid_and_stops_on_pass(monkeypatch):
    calls = []
    def planner(**kwargs):
        calls.append(kwargs)
        passed = len(calls) == 2
        return {'build_status': 'PASS' if passed else 'PLANNER_TIMEOUT', 'final_claim_valid': passed}
    monkeypatch.setattr(pipeline, 'run_validated_planner', planner)
    result = pipeline._validate_with_local_recovery(
        context={}, obj_path=Path('model.obj'), segment_rows=[], job_dir=Path('run'),
        notebook_outputs={'voxel_size': 14})
    assert [c['context']['voxelization']['grid_size'] for c in calls] == [14, 12]
    assert all(c['timeout_seconds'] == 90 for c in calls)
    assert result['final_claim_valid']
    assert calls[0]['job_dir'] != calls[1]['job_dir']


def test_runtime_error_does_not_trigger_pointless_grid_retries(monkeypatch):
    calls = []
    def planner(**kwargs):
        calls.append(kwargs)
        return {'build_status': 'VALIDATED_PLANNER_ERROR', 'final_claim_valid': False}
    monkeypatch.setattr(pipeline, 'run_validated_planner', planner)
    result = pipeline._validate_with_local_recovery(
        context={}, obj_path=None, segment_rows=[], job_dir=Path('run'), notebook_outputs={})
    assert len(calls) == 1
    assert not result['final_claim_valid']


def test_inventory_recovery_reduces_target_without_stale_semantics():
    context = {'artifact_label': 'Airplane', 'parts': [
        {'part_name': 'Propeller', 'movement': 'spinning'},
        {'part_name': 'Body', 'movement': 'static'}],
        'build_constraints': {'semantic_segment_targets': ['old cargo', 'old tail']}}
    recovered = pipeline._automatic_model_recovery_context(context, {
        'validated_planner': {'build_status': 'NEEDS_SIMPLER_MODEL', 'shortages': {'standard_2x2x2': 4}}}, 1)
    assert recovered['build_constraints']['max_validated_blocks'] == 16
    assert 'old cargo' not in recovered['build_constraints']['semantic_segment_targets']
    assert '20 to 16' not in recovered['rodin_prompt']
    assert pipeline._should_auto_recover_model(context, {'validated_planner': {
        'build_status': 'PLANNER_TIMEOUT', 'final_claim_valid': False}})


def test_model_recovery_uses_latest_feedback_and_stops(monkeypatch, tmp_path):
    results = []
    feedback = []
    def segment(**kwargs):
        number = len(results)
        result = {'context': {}, 'rodin': {}, 'bang': {}, 'build_plan': {
            'validated_planner': {'build_status': 'PASS' if number == 2 else 'NEEDS_SIMPLER_MODEL',
                                  'final_claim_valid': number == 2, 'reason': str(number)}}}
        results.append(result)
        return result
    def recover(context, plan, attempt_number):
        feedback.append(plan['validated_planner']['reason'])
        return {}
    monkeypatch.setattr(pipeline, '_run_segmentation_attempt', segment)
    monkeypatch.setattr(pipeline, '_automatic_model_recovery_context', recover)
    monkeypatch.setattr(pipeline, 'create_rodin_preview', lambda *args: {
        'context': {}, 'rodin': {'task_uuid': 'test', 'files': []}})
    result = pipeline.create_segments_and_build_plan({}, 'test', [], tmp_path, lambda *args: None)
    assert feedback == ['0', '1']
    assert len(results) == 3
    assert result['build_plan']['validated_planner']['final_claim_valid']
