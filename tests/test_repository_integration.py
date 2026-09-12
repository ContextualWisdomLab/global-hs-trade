import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

from .helpers import mod

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'create_demo.py'


def demo_module():
    assert SCRIPT.is_file(), 'the repository needs a reproducible synthetic demo builder'
    spec = importlib.util.spec_from_file_location('create_demo', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_demo_builder_contains_only_synthetic_source(tmp_path):
    target = tmp_path / 'demo.sqlite'
    receipt = demo_module().build_demo(target)
    assert receipt['inserted'] == 24 and receipt['network_called'] is False
    with mod('storage').Ledger(target) as ledger:
        status = mod('coverage.inventory').dataset_status(ledger)
        assert status['active_observations'] == status['synthetic_observations'] == 24
        assert status['real_observations'] == status['national_aggregate_records'] == 0
        assert status['coverage_percent'] is None
        assert all('SYNTHETIC' in party['legal_name'] for row in ledger.observations() for party in row['parties'])
        assert {source['source_identifier'] for source in ledger.sources()} == {'demo-synthetic'}


def test_demo_builder_never_overwrites_existing_file(tmp_path):
    target = tmp_path / 'existing.sqlite'
    target.write_bytes(b'preserve existing customer data')
    with pytest.raises(FileExistsError):
        demo_module().build_demo(target)
    assert target.read_bytes() == b'preserve existing customer data'


def test_demo_builder_reproducible_observations(tmp_path):
    module = demo_module()
    targets = [tmp_path / 'a.sqlite', tmp_path / 'b.sqlite']
    for target in targets:
        module.build_demo(target)
    with mod('storage').Ledger(targets[0]) as first, mod('storage').Ledger(targets[1]) as second:
        assert first.observations() == second.observations()
        assert first.stats() == second.stats()


def test_demo_rows_have_linked_synthetic_evidence(tmp_path):
    target = tmp_path / 'demo.sqlite'
    demo_module().build_demo(target)
    with mod('storage').Ledger(target) as ledger:
        for row in ledger.observations():
            evidence = mod('collection.captures').provenance(ledger, row['source_identifier'], row['source_record_identifier'])
            assert len(evidence) == 1 and evidence[0]['authenticity_verified'] is False
            assert 'SYNTHETIC' in evidence[0]['transcription_note']


def test_demo_failure_does_not_publish_partial_database(tmp_path, monkeypatch):
    module = demo_module()
    def fail(*args, **kwargs):
        raise ValueError('intentional rejected capture')
    monkeypatch.setattr(module, 'import_capture', fail)
    target = tmp_path / 'demo.sqlite'
    with pytest.raises(ValueError, match='intentional'):
        module.build_demo(target)
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_demo_rejections_do_not_publish_partial_database(tmp_path, monkeypatch):
    module = demo_module()
    monkeypatch.setattr(module, 'import_capture', lambda *a, **k: {'rejected': 1, 'inserted': 0})
    target = tmp_path / 'demo.sqlite'
    with pytest.raises(ValueError, match='rejected'):
        module.build_demo(target)
    assert not target.exists()


def test_demo_cli_and_offline_query(tmp_path):
    demo_module()
    target = tmp_path / 'demo.sqlite'
    built = subprocess.run([sys.executable, str(SCRIPT), '--db', str(target)], cwd=tmp_path,
                           capture_output=True, text=True, timeout=20)
    assert built.returncode == 0, built.stderr
    assert json.loads(built.stdout)['inserted'] == 24
    queried = subprocess.run([sys.executable, '-m', 'global_hs_trade', 'query', '--db', str(target),
                              '--company-country', 'BR', '--role', 'exporter', '--flow', 'X'],
                             cwd=ROOT, capture_output=True, text=True, timeout=20)
    assert queried.returncode == 0, queried.stderr
    output = json.loads(queried.stdout)
    assert output['status'] == 'observed_records' and output['complete_company_coverage'] is False
    assert all(row['dataset_kind'] == 'synthetic' for row in output['statistics'])


def test_demo_cli_existing_output_returns_actionable_error(tmp_path):
    demo_module()
    target = tmp_path / 'demo.sqlite'
    target.write_text('keep', encoding='utf-8')
    result = subprocess.run([sys.executable, str(SCRIPT), '--db', str(target)], cwd=tmp_path,
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 2
    assert json.loads(result.stderr)['status'] == 'error'
    assert target.read_text(encoding='utf-8') == 'keep'


def test_mit_license_preserved_from_existing_repository():
    import hashlib
    content = (ROOT / 'LICENSE').read_bytes()
    blob = b'blob ' + str(len(content)).encode() + b'\0' + content
    assert hashlib.sha1(blob).hexdigest() == 'b3160d62e0d16afc0cea1a0174a2da19e5d3bdd3'


def test_installed_package_smoke_verifier_is_available():
    assert (ROOT / 'scripts' / 'verify_install.py').is_file(), 'CI needs isolated installation verification'


def test_ci_runs_without_write_permissions_or_secrets():
    workflow = ROOT / '.github' / 'workflows' / 'ci.yml'
    assert workflow.is_file(), 'the repository needs a product CI workflow'
    text = workflow.read_text(encoding='utf-8')
    assert 'contents: read' in text and 'persist-credentials: false' in text
    assert 'pull_request_target' not in text and 'secrets.' not in text
    assert 'python scripts/check.py' in text and 'python scripts/verify_install.py' in text
    import re
    actions = re.findall(r'uses: ([^\s]+)', text)
    assert len(actions) == 2
    assert all(re.fullmatch(r'actions/[a-z-]+@[0-9a-f]{40}', action) for action in actions)
