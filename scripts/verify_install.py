"""Build and verify the installed wheel outside the source checkout, without network."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import venv
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], cwd: Path) -> str:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError(f'command failed: {command!r}\n{result.stdout}\n{result.stderr}')
    return result.stdout


def main() -> int:
    with TemporaryDirectory(prefix='global-hs-install-') as temporary:
        workspace = Path(temporary)
        wheels = workspace / 'wheels'
        wheels.mkdir()
        run([sys.executable, '-W', 'error', '-c',
             'import sys; from setuptools.build_meta import build_wheel; build_wheel(sys.argv[1])',
             str(wheels)], ROOT)
        built = list(wheels.glob('*.whl'))
        if len(built) != 1:
            raise ValueError('expected exactly one wheel')
        with ZipFile(built[0]) as archive:
            if 'global_hs_trade/coverage/countries.json' not in archive.namelist():
                raise ValueError('wheel is missing its country reference data')
            licenses = [name for name in archive.namelist() if name.endswith('.dist-info/licenses/LICENSE')]
            if len(licenses) != 1 or archive.read(licenses[0]) != (ROOT / 'LICENSE').read_bytes():
                raise ValueError('wheel did not preserve the repository license')
        environment = workspace / 'venv'
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        run([str(python), '-I', '-m', 'pip', '--disable-pip-version-check', 'install',
             '--no-index', '--no-deps', str(built[0])], workspace)
        database = workspace / 'synthetic.sqlite'
        run([sys.executable, str(ROOT / 'scripts/create_demo.py'), '--db', str(database)], workspace)
        query = json.loads(run([str(python), '-I', '-m', 'global_hs_trade', 'query', '--db', str(database),
                               '--hs6', '090111', '--role', 'exporter', '--flow', 'X'], workspace))
        if (query['status'] != 'observed_records' or len(query['statistics']) != 1
                or query['statistics'][0]['observed_value'] != '10000'
                or query['statistics'][0]['dataset_kind'] != 'synthetic'
                or query['complete_company_coverage'] is not False):
            raise ValueError('installed package returned unexpected synthetic statistics')
        run([str(python), '-I', '-m', 'global_hs_trade', 'coverage', '--country', 'BR', '--flow', 'X'], workspace)
        print(json.dumps({'status': 'PASS', 'wheel': built[0].name,
                          'isolated_installation': True, 'network_required': False,
                          'license_preserved': True, 'synthetic_query_verified': True}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
