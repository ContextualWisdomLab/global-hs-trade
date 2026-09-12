from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_sqlite_execute_does_not_build_query_strings_with_concatenation():
    offenders: list[str] = []
    for relative in [
        'global_hs_trade/storage.py',
        'global_hs_trade/collection/captures.py',
    ]:
        path = ROOT / relative
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != 'execute' or not node.args:
                continue
            if isinstance(node.args[0], ast.BinOp):
                offenders.append(f'{relative}:{node.lineno}')
    assert offenders == [], f'dynamically concatenated SQL passed to execute(): {offenders}'
