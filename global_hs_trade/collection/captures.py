"""Offline evidence import; a digest proves integrity, not source authenticity."""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit

from ..sources import hmrc, comtrade
from ..storage import Ledger, canonical
from ..trade.model import utc_timestamp

MAX_CAPTURE_BYTES = 16 * 1024 * 1024


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError('non-finite numbers are not permitted in captures')
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, float):
        raise ValueError('capture decimal numbers must be exact decimal strings, not binary floats')
    return value


def payload_digest(payload: Any) -> str:
    encoded = json.dumps(_json_safe(payload), ensure_ascii=False, sort_keys=True,
                         separators=(',', ':'), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def seal_capture(envelope: dict) -> dict:
    result = _json_safe(envelope)
    result['payload_sha256'] = payload_digest(result['payload'])
    return result


def _ensure_schema(ledger: Ledger) -> bool:
    if ledger.read_only:
        names = {row[0] for row in ledger.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN ('captures','capture_observations')")}
        return names == {'captures', 'capture_observations'}
    statements = '''
        CREATE TABLE IF NOT EXISTS captures (
            capture_identifier TEXT PRIMARY KEY,
            source_identifier TEXT NOT NULL REFERENCES sources(source_identifier),
            captured_at TEXT NOT NULL, envelope TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS capture_observations (
            capture_identifier TEXT NOT NULL REFERENCES captures(capture_identifier),
            source_identifier TEXT NOT NULL,
            source_record_identifier TEXT NOT NULL,
            source_version INTEGER NOT NULL,
            PRIMARY KEY(capture_identifier, source_identifier, source_record_identifier, source_version),
            FOREIGN KEY(source_identifier, source_record_identifier, source_version)
                REFERENCES observations(source_identifier, source_record_identifier, source_version));
    '''
    # executescript would commit an unrelated caller transaction, even during a read.
    for statement in statements.split(';'):
        if statement.strip():
            ledger.connection.execute(statement)
    return True


def _validate(envelope: Any) -> dict:
    if not isinstance(envelope, dict):
        raise ValueError('capture must be an object')
    if type(envelope.get('schema_version')) is not int or envelope['schema_version'] != 1:
        raise ValueError('unsupported capture schema version')
    value = _json_safe(envelope)
    encoded = canonical(value)
    if len(encoded.encode()) > MAX_CAPTURE_BYTES:
        raise ValueError('capture exceeds the 16 MiB evidence limit; split explicitly')
    for field in ['source_identifier', 'source_url', 'selection_scope']:
        if not isinstance(value.get(field), str) or not value[field].strip() or len(value[field]) > 8192:
            raise ValueError('capture requires a bounded ' + field)
    url = urlsplit(value['source_url'])
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.fragment:
        raise ValueError('capture source_url must be an HTTPS source URL without credentials or fragment')
    value['captured_at'] = utc_timestamp(value.get('captured_at')) if value.get('captured_at') else None
    if value['captured_at'] is None:
        raise ValueError('capture requires an explicit captured_at timestamp')
    if value.get('representation') not in {'source_json', 'selected_fields_transcription'}:
        raise ValueError('unsupported capture representation')
    if value['representation'] == 'selected_fields_transcription' and not value.get('transcription_note'):
        raise ValueError('selected-field captures require a transcription_note')
    if 'payload' not in value or payload_digest(value['payload']) != value.get('payload_sha256'):
        raise ValueError('capture payload digest mismatch')
    adapter = value.get('adapter')
    if adapter == 'hmrc_trade':
        if value['source_identifier'] != 'hmrc-traders' or url.netloc != 'api.uktradeinfo.com' or url.path != '/Trade':
            raise ValueError('HMRC capture has a mismatching source binding')
    elif adapter == 'comtrade_preview':
        if (value['source_identifier'] != 'un-comtrade' or url.netloc != 'comtradeapi.un.org'
                or not url.path.startswith('/public/v1/preview/C/')):
            raise ValueError('Comtrade capture has a mismatching source binding')
    elif adapter == 'normalized_observations':
        if value['source_identifier'] in {'hmrc-traders', 'un-comtrade'}:
            raise ValueError('official feeds require their source-native parser')
        if not isinstance(value['payload'], list):
            raise ValueError('normalized capture payload must be a list')
        for row in value['payload']:
            if (not isinstance(row, dict) or row.get('source_identifier') != value['source_identifier']
                    or row.get('source_url') != value['source_url']):
                raise ValueError('observation does not match capture source binding')
    else:
        raise ValueError('unsupported capture adapter')
    return value


def _summary(identifier: str, envelope: dict) -> dict:
    fields = ['source_identifier', 'source_url', 'captured_at', 'representation', 'adapter',
              'selection_scope', 'transcription_note', 'payload_sha256', 'annotations']
    return {'capture_identifier': identifier, **{key: envelope.get(key) for key in fields},
            'authenticity_verified': False, 'population_completeness': 'not_asserted',
            'digest_scope': 'canonical JSON with decimal numbers encoded as strings; not original download bytes'}


def import_capture(ledger: Ledger, envelope: dict) -> dict:
    value = _validate(envelope)
    source = ledger._right(value['source_identifier'], 'internal_analysis')
    identifier = payload_digest(value)
    adapter = value['adapter']
    if adapter == 'hmrc_trade':
        rows = hmrc.parse_page(value['payload'], value.get('source_version', 1))
    elif adapter == 'comtrade_preview':
        rows = comtrade.parse_page(value['payload'])
    else:
        rows = value['payload']
    if adapter == 'comtrade_preview':
        prepared_baselines = ledger._prepare_baselines(rows)
        prepared_ingest = failures = None
    else:
        prepared_ingest, failures = ledger._prepare_ingest(rows)
        prepared_baselines = None
    # Schema setup is separate from the short import transaction and contains no capture.
    with ledger.connection:
        _ensure_schema(ledger)
    with ledger.connection:
        ledger.connection.execute('INSERT OR IGNORE INTO captures VALUES (?,?,?,?)',
            (identifier, value['source_identifier'], value['captured_at'], canonical(value)))
        if adapter == 'comtrade_preview':
            saved = ledger._write_baselines(prepared_baselines,commit=False)
            receipt = {'inserted': 0, 'replayed': 0, 'rejected': 0,
                       'national_records_saved': saved, 'company_records_added': 0}
        else:
            receipt = ledger._write_ingest(prepared_ingest,failures,commit=False)
            links = []
            # Only an exact accepted version can gain provenance; a conflicting row cannot.
            for _, normalized, digest in prepared_ingest:
                key = (normalized['source_identifier'], normalized['source_record_identifier'], normalized['source_version'])
                found = ledger.connection.execute('SELECT content_hash FROM observations WHERE '
                    'source_identifier=? AND source_record_identifier=? AND source_version=?', key).fetchone()
                if found is not None and found[0] == digest:
                    links.append((identifier, *key))
            ledger.connection.executemany('INSERT OR IGNORE INTO capture_observations VALUES (?,?,?,?)', links)
            receipt['company_records_added'] = receipt['inserted']
        receipt.update({'capture_identifier': identifier, 'source_identifier': source['source_identifier'],
            'status': 'imported_with_rejections' if receipt['rejected'] else 'imported',
            'live_network_request': False, 'population_completeness': 'not_asserted',
            'authenticity_verified': False})
        ledger.record_run(receipt,commit=False)
    return receipt


def list_captures(ledger: Ledger, source_identifier: str | None = None) -> list[dict]:
    if not _ensure_schema(ledger):
        return []
    if source_identifier is not None:
        ledger._right(source_identifier, 'internal_analysis')
    if source_identifier is None:
        rows = ledger.connection.execute(
            'SELECT capture_identifier, envelope FROM captures ORDER BY captured_at, capture_identifier')
    else:
        rows = ledger.connection.execute(
            'SELECT capture_identifier, envelope FROM captures WHERE source_identifier=? '
            'ORDER BY captured_at, capture_identifier', (source_identifier,))
    result = []
    for row in rows:
        envelope = json.loads(row['envelope'])
        ledger._right(envelope['source_identifier'], 'internal_analysis')
        result.append(_summary(row['capture_identifier'], envelope))
    return result


def provenance(ledger: Ledger, source_identifier: str, record_identifier: str, version: int | None = None) -> list[dict]:
    ledger._right(source_identifier, 'internal_analysis')
    if not _ensure_schema(ledger):
        return []
    if version is None:
        version = ledger.connection.execute('SELECT MAX(source_version) FROM observations WHERE '
            'source_identifier=? AND source_record_identifier=?', (source_identifier, record_identifier)).fetchone()[0]
    if version is None:
        return []
    rows = ledger.connection.execute('SELECT c.capture_identifier, c.envelope FROM captures c '
        'JOIN capture_observations o ON c.capture_identifier=o.capture_identifier '
        'WHERE o.source_identifier=? AND o.source_record_identifier=? AND o.source_version=? '
        'ORDER BY c.captured_at,c.capture_identifier', (source_identifier, record_identifier, version))
    return [_summary(row['capture_identifier'], json.loads(row['envelope'])) for row in rows]


def capture_reference_index(ledger: Ledger, source_identifiers: set[str] | None = None) -> dict[tuple[str, str, int], list[str]]:
    if not _ensure_schema(ledger):
        return {}
    result: dict[tuple[str, str, int], list[str]] = {}
    for row in ledger.connection.execute('SELECT * FROM capture_observations ORDER BY capture_identifier'):
        if source_identifiers is not None and row['source_identifier'] not in source_identifiers:
            continue
        ledger._right(row['source_identifier'], 'internal_analysis')
        key = (row['source_identifier'], row['source_record_identifier'], row['source_version'])
        result.setdefault(key, []).append(row['capture_identifier'])
    return result
