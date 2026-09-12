from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _is_dynamic_sql(node: ast.AST, dynamic_names: set[str]) -> bool:
    if isinstance(node, ast.Name):
        return node.id in dynamic_names
    if isinstance(node, ast.JoinedStr):
        return True
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return node.func.attr == 'format'
    if isinstance(node, ast.BinOp):
        return not all(isinstance(value, ast.Constant) for value in (node.left, node.right))
    return False


def test_sqlite_execute_does_not_build_query_strings_with_concatenation():
    offenders: list[str] = []
    for relative in [
        'global_hs_trade/storage.py',
        'global_hs_trade/collection/captures.py',
    ]:
        path = ROOT / relative
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        dynamic_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = node.value
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if value is not None and _is_dynamic_sql(value, dynamic_names):
                    dynamic_names.update(
                        target.id for target in targets if isinstance(target, ast.Name)
                    )
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != 'execute' or not node.args:
                continue
            if _is_dynamic_sql(node.args[0], dynamic_names):
                offenders.append(f'{relative}:{node.lineno}')
    assert offenders == [], f'dynamically concatenated SQL passed to execute(): {offenders}'


def test_dynamic_sql_classifier_covers_common_string_construction():
    expressions = [
        "f'SELECT {column}'",
        "'SELECT {}'.format(column)",
        "'SELECT ' + column",
        "query",
    ]
    assert all(
        _is_dynamic_sql(ast.parse(expression, mode='eval').body, {'query'})
        for expression in expressions
    )
    assert not _is_dynamic_sql(ast.parse("'CREATE TABLE fixed(value TEXT)'", mode='eval').body, set())
