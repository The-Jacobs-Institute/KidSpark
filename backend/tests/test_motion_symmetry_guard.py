import ast
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("plane, expected", [(None, False), (8.0, True), (6.0, False)])
def test_missing_symmetry_is_not_a_crash_or_a_validated_plane(plane, expected):
    # Extract the pure validator because importing the notebook engine runs a build.
    path = Path(__file__).resolve().parents[1] / "bricksmart" / "row_column_engine.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "validate_motion_connected_structural_subassembly")
    namespace = {"SYMMETRY_CENTER_PLANE": plane}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)
    result = namespace[function.name](
        {"validation": {
            "require_connector_to_anchor_lock": False,
            "require_connector_to_subassembly_lock": False,
            "require_internal_subassembly_locking": False,
            "require_centered_on_symmetry_axis": True,
        }},
        SimpleNamespace(position=(7, 0, 0), size=(2, 2, 2), block_id=1),
        [],
        {},
    )
    assert result["centered_on_symmetry_axis"] is expected
    assert result["valid"] is expected
