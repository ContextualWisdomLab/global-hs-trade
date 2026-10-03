"""Build a reproducible, synthetic-only demo without replacing an existing file."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from global_hs_trade.collection.captures import import_capture, payload_digest
from global_hs_trade.coverage.catalog import builtin_sources
from global_hs_trade.storage import Ledger

SOURCE_URL = 'https://example.org/global-hs-trade/synthetic'
TIMESTAMP = '2026-01-01T00:00:00+00:00'
LANES = (
    ('BR', 'DE', '090111'), ('DE', 'US', '870323'), ('CN', 'MX', '850440'),
    ('VN', 'JP', '640399'), ('IN', 'GB', '300490'), ('TR', 'FR', '610910'),
    ('ZA', 'NL', '080510'), ('AU', 'CN', '260111'), ('CA', 'US', '440710'),
    ('CL', 'KR', '740311'), ('ID', 'IN', '151190'), ('EG', 'IT', '520100'),
)


def demo_records() -> list[dict]:
    records = []
    for index, (origin, destination, hs6) in enumerate(LANES, 1):
        parties = [
            {'role': 'exporter', 'legal_name': f'SYNTHETIC {origin} Exporter {index}',
             'country_code': origin, 'external_identifier': f'exporter-{index}'},
            {'role': 'importer', 'legal_name': f'SYNTHETIC {destination} Importer {index}',
             'country_code': destination, 'external_identifier': f'importer-{index}'},
        ]
        for flow, reporter, partner in [('X', origin, destination), ('M', destination, origin)]:
            records.append({
                'source_identifier': 'demo-synthetic',
                'source_record_identifier': f'SYNTHETIC-{index:02d}-{flow}',
                'source_version': 1, 'period': '2026-01',
                'reporter_country': reporter, 'recorded_flow': flow,
                'record_kind': 'customs_line', 'date_basis': 'synthetic_month',
                'hs_code': hs6, 'hs_revision': 'UNKNOWN', 'hs_code_origin': 'user_inferred',
                'value': str(index * 10000), 'value_currency': 'USD',
                'value_basis': 'FOB', 'value_origin': 'reported',
                'net_weight_kg': str(index * 1000), 'gross_weight_kg': None,
                'quantity': None, 'quantity_unit': None,
                'partner_country': partner,
                'partner_basis': 'destination' if flow == 'X' else 'origin',
                'origin_country': origin, 'dispatch_country': origin,
                'destination_country': destination, 'parties': parties,
                'event_status': 'active', 'document_key': None,
                'source_url': SOURCE_URL, 'retrieved_at': TIMESTAMP,
            })
    return records


def build_demo(target: Path) -> dict:
    target = Path(target)
    # lexists also rejects a dangling symlink. The final hard link closes the TOCTOU gap.
    if os.path.lexists(target):
        raise FileExistsError(f'refusing to replace existing path: {target}')
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = demo_records()
    envelope = {
        'schema_version': 1, 'source_identifier': 'demo-synthetic',
        'source_url': SOURCE_URL, 'captured_at': TIMESTAMP,
        'representation': 'selected_fields_transcription', 'adapter': 'normalized_observations',
        'selection_scope': '24 synthetic customs observations across 12 fictional trade lanes.',
        'transcription_note': 'SYNTHETIC generated fixtures; no real company, source download or trade claim.',
        'payload': payload, 'payload_sha256': payload_digest(payload),
    }
    with TemporaryDirectory(prefix='.global-hs-demo-', dir=target.parent) as temporary:
        staged = Path(temporary) / 'demo.sqlite'
        with Ledger(staged) as ledger:
            policy = next(spec for spec in builtin_sources() if spec['source_identifier'] == 'demo-synthetic')
            ledger.register_source(policy)
            receipt = import_capture(ledger, envelope)
            if receipt['rejected']:
                raise ValueError('synthetic demo contains rejected observations')
            ledger.connection.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        # Both paths are on the same filesystem; link fails rather than replacing any target.
        os.link(staged, target)
    return {'status': 'created', 'database': str(target), 'dataset_kind': 'synthetic',
            'inserted': receipt['inserted'], 'network_called': False,
            'complete_company_coverage': False}


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=Path('var/synthetic.sqlite'))
    arguments = parser.parse_args(arguments)
    try:
        print(json.dumps(build_demo(arguments.db), ensure_ascii=False))
        return 0
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(json.dumps({'status': 'error', 'message': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
