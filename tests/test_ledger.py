from copy import deepcopy
from decimal import Decimal
import pytest
from tests.helpers import mod,row,source

@pytest.fixture
def ledger(tmp_path):
    db=mod('storage').Ledger(tmp_path/'test.sqlite')
    db.register_source(source())
    yield db
    db.close()

def test_ingest_and_idempotent_replay(ledger):
    assert ledger.ingest([row()])['inserted']==1
    assert ledger.ingest([row()])['replayed']==1
    assert len(ledger.observations())==1

def test_retrieval_time_does_not_break_idempotence(ledger):
    ledger.ingest([row()])
    assert ledger.ingest([row(retrieved_at='2026-09-12T01:00:00Z')])['replayed']==1

def test_same_version_conflict_is_visible(ledger):
    ledger.ingest([row()])
    result=ledger.ingest([row(value='99')])
    assert result['rejected']==1
    assert len(ledger.issues())==1
    assert ledger.observations()[0]['value']=='1234.56'

def test_revision_replaces_not_sums(ledger):
    ledger.ingest([row(),row(source_version=2,value='10')])
    records=ledger.stats()
    assert len(records)==1
    assert records[0]['observed_value']=='10'

def test_latest_cancelled_does_not_resurrect_old_record(ledger):
    ledger.ingest([row(),row(source_version=2,event_status='cancelled')])
    assert ledger.stats()==[]

def test_no_data_is_no_rows_not_zero(ledger):
    assert ledger.stats(hs6='870323')==[]

def test_currency_not_mixed(ledger):
    ledger.ingest([row(),row(source_record_identifier='euro',value_currency='EUR')])
    assert len(ledger.stats())==2

def test_basis_not_mixed(ledger):
    ledger.ingest([row(),row(source_record_identifier='cif',value_basis='CIF')])
    assert len(ledger.stats())==2

def test_revision_not_mixed(ledger):
    ledger.ingest([row(),row(source_record_identifier='old',hs_revision='HS2017')])
    assert len(ledger.stats())==2

def test_value_estimates_not_mixed_with_observed(ledger):
    ledger.ingest([row(),row(source_record_identifier='estimate',value_origin='estimated')])
    assert len(ledger.stats())==2

def test_missing_money_keeps_null(ledger):
    ledger.ingest([row(value=None,value_origin='missing')])
    stat=ledger.stats()[0]
    assert stat['observed_value'] is None
    assert stat['missing_value_observations']==1

def test_precise_sum(ledger):
    ledger.ingest([row(value='0.1'),row(source_record_identifier='b',value='0.2')])
    assert ledger.stats()[0]['observed_value']=='0.3'

def test_presence_not_shipment(ledger):
    ledger.ingest([row(record_kind='trader_presence',value=None,value_origin='missing',net_weight_kg=None)])
    stat=ledger.stats()[0]
    assert stat['presence_observations']==1
    assert stat['customs_lines']==0 and stat['bill_of_lading_observations']==0

def test_sources_not_blindly_combined(ledger):
    ledger.register_source(source('other'))
    ledger.ingest([row(),row(source_identifier='other')])
    assert len(ledger.stats())==2

def test_real_and_synthetic_not_combined(ledger):
    ledger.register_source(source('real','real'))
    ledger.ingest([row(),row(source_identifier='real')])
    assert {s['dataset_kind'] for s in ledger.stats()}=={'synthetic','real'}

def test_unknown_source_quarantined(ledger):
    assert ledger.ingest([row(source_identifier='unregistered')])['rejected']==1

def test_partial_batch_is_reported(ledger):
    outcome=ledger.ingest([row(),row(source_record_identifier='bad',hs_code='wrong')])
    assert outcome['inserted']==1 and outcome['rejected']==1

def test_raw_export_denied(ledger,tmp_path):
    ledger.ingest([row()])
    with pytest.raises(PermissionError):ledger.export_rows('test-source',tmp_path/'leak.jsonl')
    assert not (tmp_path/'leak.jsonl').exists()

def test_aggregate_export_denied(ledger,tmp_path):
    ledger.register_source(source('restricted',export=False))
    with pytest.raises(PermissionError):ledger.export_stats('restricted',tmp_path/'out.json')

def test_verified_cross_source_duplicate_report(ledger):
    ledger.register_source(source('other'))
    document={'namespace':'BR:customs','identifier':'DECL-1','line_identifier':'1','verified':True}
    r=row(document_key=document)
    # Registry identity is the same, unlike source-local identifiers.
    r['parties'][0].update(registry_namespace='CNPJ',registry_identifier='123')
    other=deepcopy(r);other['source_identifier']='other'
    ledger.ingest([r,other])
    matches=ledger.reconcile()
    assert len(matches)==1 and matches[0]['status']=='matching_observations'

def test_cross_source_conflict_not_silently_overwritten(ledger):
    ledger.register_source(source('other'))
    document={'namespace':'BR:customs','identifier':'DECL-1','line_identifier':'1','verified':True}
    ledger.ingest([row(document_key=document),row(source_identifier='other',document_key=document,value='9')])
    assert ledger.reconcile()[0]['status']=='conflicting_observations'

def test_unverified_document_not_linked(ledger):
    ledger.register_source(source('other'))
    key={'namespace':'BR:customs','identifier':'X','line_identifier':'1','verified':False}
    ledger.ingest([row(document_key=key),row(source_identifier='other',document_key=key)])
    assert ledger.reconcile()==[]

def test_sql_injection_does_not_expand_results(ledger):
    ledger.ingest([row()])
    assert ledger.stats(company="' OR 1=1 --")==[]
