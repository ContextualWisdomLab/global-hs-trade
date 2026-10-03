"""Run this synchronous test suite without inheriting host plugin configuration."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys


def test_environment(parent: dict[str, str]) -> dict[str, str]:
    result = dict(parent)
    # Machine-wide plugin discovery must not silently change the project's test dependencies.
    result.pop('PYTEST_ADDOPTS', None)
    result.pop('PYTEST_PLUGINS', None)
    result['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
    result['PYTHONWARNINGS'] = 'error'
    return result


def main(arguments: list[str]) -> int:
    return subprocess.run([sys.executable, '-m', 'pytest', '-q', '-W', 'error', *arguments],
        cwd=Path(__file__).resolve().parents[1], env=test_environment(dict(os.environ)), check=False).returncode


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
