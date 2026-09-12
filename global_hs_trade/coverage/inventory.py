"""What this database actually contains, distinct from acquisition possibilities."""
from __future__ import annotations
from collections import defaultdict
from ..storage import Ledger
from ..collection.captures import list_captures


def dataset_status(ledger: Ledger) -> dict:
    rows = ledger.observations()
    fields = ('source_identifier', 'dataset_kind', 'reporter_country', 'recorded_flow',
              'record_kind', 'hs6', 'hs_revision', 'value_currency', 'value_basis', 'value_origin')
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row.get(field) for field in fields)].append(row)
    slices = []
    for key, records in sorted(groups.items(), key=lambda item: str(item[0])):
        slices.append({**dict(zip(fields, key)), 'observations': len(records),
            'observations_with_value': sum(row['value'] is not None for row in records),
            'observations_without_value': sum(row['value'] is None for row in records),
            'first_period': min(row['period'] for row in records),
            'last_period': max(row['period'] for row in records)})
    identities = {party['company_identifier'] for row in rows for party in row['parties']}
    return {'status': 'observations_present' if rows else 'no_observed_records',
        'active_observations': len(rows), 'real_observations': sum(row['dataset_kind']=='real' for row in rows),
        'synthetic_observations': sum(row['dataset_kind']=='synthetic' for row in rows),
        'observations_with_value': sum(row['value'] is not None for row in rows),
        'observations_without_value': sum(row['value'] is None for row in rows),
        'reporter_countries_observed': sorted({row['reporter_country'] for row in rows}),
        'hs6_observed': sorted({row['hs6'] for row in rows}),
        'first_period': min((row['period'] for row in rows), default=None),
        'last_period': max((row['period'] for row in rows), default=None),
        'source_scoped_company_identities': len(identities),
        'global_unique_legal_entities_verified': False, 'coverage_percent': None,
        'coverage_denominator': 'unknown; listed countries are not fully covered countries',
        'national_aggregate_records': len(ledger.baselines()),
        'evidence_captures': len(list_captures(ledger)),
        'upstream_freshness_verified': False, 'slices': slices}
