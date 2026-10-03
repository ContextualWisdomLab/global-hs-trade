from decimal import Decimal
import pytest
from .helpers import mod, row

def sample_envelopes():
    # These are independently generated synthetic cases, not redistributed vendor rows.
    definitions = [
        ('DE SUPPLIER', 'supplier', 'DE', 'VN', 'M', '851770', None),
        ('US IMPORTER', 'importer', 'US', 'US', 'M', '680299', None),
        ('TW SUPPLIER', 'supplier', 'TW', 'US', 'M', '681099', None),
        ('PE IMPORTER', 'importer', 'PE', 'PE', 'M', '843143', '101.22'),
        ('CO IMPORTER', 'importer', 'CO', 'CO', 'M', '850940', '85008'),
        ('CO EXPORTER', 'exporter', 'CO', 'CO', 'X', '060319', '1304.75'),
        ('EC EXPORTER', 'exporter', 'EC', 'EC', 'X', '200891', '2400'),
        ('GB TRADER', 'importer', None, 'GB', 'M', '090111', None),
    ]
    for index, (name, role, country, reporter, flow, hs, amount) in enumerate(definitions):
        url = f'https://example.org/global-hs-trade/synthetic-case/{index}'
        item = row(source_identifier='demo-synthetic', source_record_identifier=f'case-{index}',
            reporter_country=reporter, recorded_flow=flow, hs_code=hs, hs_revision='UNKNOWN',
            value=amount, value_origin='missing' if amount is None else 'reported',
            value_currency=None if amount is None else 'USD', value_basis='UNKNOWN' if amount is None else 'FOB',
            net_weight_kg=None, gross_weight_kg=None, quantity=None, quantity_unit=None,
            origin_country=None, dispatch_country=None, destination_country=None, partner_country=None,
            parties=[{'role':role, 'legal_name':'SYNTHETIC '+name, 'country_code':country,
                      'external_identifier':f'entity-{index}'}], source_url=url)
        if index in {1, 2}:
            item.update(record_kind='bill_of_lading', gross_weight_kg=str(19580 if index == 1 else 19400))
        if index == 3:
            item['parties'].append({'role':'forwarder','legal_name':'SYNTHETIC FREIGHT AGENT',
                                   'country_code':None,'external_identifier':'agent'})
        if index == 5:
            item['partner_country'] = 'VE'
            item['parties'].append({'role':'buyer','legal_name':'SYNTHETIC UNKNOWN BUYER',
                                   'country_code':None,'external_identifier':'buyer'})
        if index == 6:
            item.update(quantity='1800', quantity_unit='KILOGRAMO BRUTO')
        if index == 7:
            item['record_kind'] = 'trader_presence'
        payload = [item]
        yield {'schema_version':1,'source_identifier':'demo-synthetic','source_url':url,
               'captured_at':'2026-01-01T00:00:00+00:00','representation':'selected_fields_transcription',
               'adapter':'normalized_observations','selection_scope':'One generated synthetic regression case.',
               'transcription_note':'SYNTHETIC test data; no real trade assertion.',
               'payload':payload,'payload_sha256':mod('collection.captures').payload_digest(payload)}


@pytest.fixture
def sample_ledger(tmp_path):
    with mod('storage').Ledger(tmp_path/'observations.sqlite') as ledger:
        for spec in mod('coverage.catalog').builtin_sources():
            ledger.register_source(spec)
        for envelope in sample_envelopes():
            outcome=mod('collection.captures').import_capture(ledger,envelope)
            assert outcome['rejected']==0
        yield ledger


def test_sample_receipts_are_not_global_coverage(sample_ledger):
    status=mod('coverage.inventory').dataset_status(sample_ledger)
    assert status['active_observations']==8
    assert status['observations_with_value']==4
    assert status['synthetic_observations']==8
    assert status['real_observations']==0
    assert status['coverage_percent'] is None
    assert status['evidence_captures']==8

@pytest.mark.parametrize('company,hs,role,amount',[
    ('PE IMPORTER','843143','importer','101.22'),
    ('CO IMPORTER','850940','importer','85008'),
    ('CO EXPORTER','060319','exporter','1304.75'),
    ('EC EXPORTER','200891','exporter','2400'),
])
def test_money_matches_selected_source_field(sample_ledger,company,hs,role,amount):
    rows=sample_ledger.stats(company=company,hs6=hs,role=role)
    assert len(rows)==1
    assert rows[0]['observed_value']==amount
    assert rows[0]['value_basis']=='FOB' and rows[0]['value_currency']=='USD'


def test_agent_not_misattributed_as_exporter(sample_ledger):
    assert sample_ledger.stats(company='FREIGHT AGENT',role='exporter')==[]


def test_buyer_country_not_inferred_from_destination(sample_ledger):
    row=sample_ledger.stats(company='UNKNOWN BUYER',role='buyer')[0]
    assert row['company_country'] is None
    assert row['partner_country']=='VE'


def test_positive_gross_quantity_not_claimed_zero_netweight(sample_ledger):
    row=sample_ledger.stats(company='EC EXPORTER',role='exporter')[0]
    assert row['net_weight_kg'] is None and row['gross_weight_kg'] is None
    assert Decimal(row['quantity'])==1800 and row['quantity_unit']=='KILOGRAMO BRUTO'


def test_presence_sample_cannot_be_amount_or_shipment_count(sample_ledger):
    row=sample_ledger.stats(hs6='090111')[0]
    assert row['observed_value'] is None and row['presence_observations']==1
    assert row['customs_lines']==0 and row['bill_of_lading_observations']==0


def test_all_sample_rows_have_reproducible_provenance(sample_ledger):
    for row in sample_ledger.observations():
        refs=mod('collection.captures').provenance(sample_ledger,row['source_identifier'],row['source_record_identifier'],row['source_version'])
        assert len(refs)==1 and refs[0]['authenticity_verified'] is False


def test_source_updates_replay_without_duplicate_trade(sample_ledger):
    for envelope in sample_envelopes():
        outcome=mod('collection.captures').import_capture(sample_ledger,envelope)
        assert outcome['inserted']==0 and outcome['replayed']==1
    assert len(sample_ledger.observations())==8
