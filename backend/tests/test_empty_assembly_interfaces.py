import ast
from pathlib import Path
import pandas as pd
import json
import pytest


def test_empty_contacts_have_schema_but_no_fabricated_edges(tmp_path):
    path = Path(__file__).resolve().parents[1] / 'bricksmart' / 'row_column_engine.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == 'required_assembly_interfaces')
    namespace = {'OUTPUT_DIR': tmp_path, 'json': json}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), 'exec'), namespace)
    result, required = namespace[function.name](pd.DataFrame(), [1])
    assert result.empty
    assert required == set()
    assert {'segment_a', 'segment_b', 'contact_area', 'interface_id', 'assembly_edge_role'} <= set(result.columns)
    with pytest.raises(RuntimeError, match='NO_STRUCTURAL_CONTACTS'):
        namespace[function.name](pd.DataFrame(), [1, 2])
    assert json.loads((tmp_path / 'structural_contact_preflight.json').read_text())['status'] == 'NO_STRUCTURAL_CONTACTS'
