from copy import deepcopy
import hashlib
import json
import pytest
from .helpers import mod, row, source
from .test_application import ledger, hmrc_payload, invoke

URL='https://example.org/synthetic/1'

def envelope(payload=None, **changes):
    payload=payload if payload is not None else [row()]
    value={'schema_version':1,'adapter':'normalized_observations','source_identifier':'test-source',
        'source_url':URL,'captured_at':'2026-09-12T00:00:00+00:00',
        'representation':'selected_fields_transcription','selection_scope':'One fictional test row only',
        'transcription_note':'SYNTHETIC test fixture, not real trade.',
        'payload':payload,'payload_sha256':hashlib.sha256(mod('storage').canonical(payload).encode()).hexdigest()}
    value.update(changes)
    return value


def test_import_capture_replay_and_provenance(ledger):
    capture=mod('collection.captures')
    result=capture.import_capture(ledger,envelope())
    assert result['inserted']==1 and result['status']=='imported'
    assert capture.import_capture(ledger,envelope())['replayed']==1
    assert len(ledger.observations())==1
    saved=capture.list_captures(ledger)
    assert len(saved)==1 and saved[0]['payload_sha256']==envelope()['payload_sha256']
    assert saved[0]['authenticity_verified'] is False
    assert 'payload' not in saved[0]
    linked=capture.provenance(ledger,'test-source',row()['source_record_identifier'],1)
    assert len(linked)==1 and linked[0]['capture_identifier']==result['capture_identifier']


def test_capture_tampering_rejected_before_writes(ledger):
    value=envelope();value['payload'][0]['value']='9999'
    with pytest.raises(ValueError,match='digest'):
        mod('collection.captures').import_capture(ledger,value)
    assert not ledger.observations()


def test_capture_metadata_not_same_capture(ledger):
    c=mod('collection.captures');a=c.import_capture(ledger,envelope())
    b=c.import_capture(ledger,envelope(selection_scope='Same fixture, separately described'))
    assert a['capture_identifier']!=b['capture_identifier'] and b['replayed']==1

@pytest.mark.parametrize('change',[
    {'source_identifier':'demo-synthetic'},
    {'source_url':'https://other.example/1'},
    {'adapter':'hmrc_trade'},
    {'representation':'verified_customs_document'},
    {'schema_version':True},
    {'captured_at':'yesterday'},
    {'source_url':'https://secret@api.uktradeinfo.com/Trade'},
])
def test_false_binding_and_invalid_envelopes_rejected(ledger,change):
    with pytest.raises(ValueError):
        mod('collection.captures').import_capture(ledger,envelope(**change))
    assert not ledger.observations()


def test_hmrc_transcription_keeps_presence_not_money(ledger):
    cap=envelope(hmrc_payload(),adapter='hmrc_trade',source_identifier='hmrc-traders',
                 source_url='https://api.uktradeinfo.com/Trade?$top=1',selection_scope='First selected row, not complete response')
    result=mod('collection.captures').import_capture(ledger,cap)
    assert result['inserted']==1 and result['live_network_request'] is False
    stats=ledger.stats()[0]
    assert stats['observed_value'] is None and stats['record_kind']=='trader_presence'
    assert stats['company_country'] is None


def test_capture_cannot_bypass_read_right(ledger):
    spec=source('blocked');spec['rights']['internal_analysis']=False;ledger.register_source(spec)
    cap=envelope([row(source_identifier='blocked')],source_identifier='blocked')
    with pytest.raises(PermissionError):mod('collection.captures').import_capture(ledger,cap)


def test_partial_invalid_capture_links_only_accepted_rows(ledger):
    cap=envelope([row(),row(source_record_identifier='bad',value='-1')])
    c=mod('collection.captures');out=c.import_capture(ledger,cap)
    assert out['status']=='imported_with_rejections' and out['rejected']==1
    assert c.provenance(ledger,'test-source','bad',1)==[]


def test_comtrade_capture_is_never_company_data(ledger):
    cap=envelope({'data':[]},adapter='comtrade_preview',source_identifier='un-comtrade',
                 source_url='https://comtradeapi.un.org/public/v1/preview/C/A/HS?period=2024')
    result=mod('collection.captures').import_capture(ledger,cap)
    assert result['company_records_added']==0 and result['population_completeness']=='not_asserted'
    assert ledger.stats()==[]


def test_dataset_status_does_not_claim_geographic_coverage(ledger):
    ledger.ingest([row(),row(source_record_identifier='missing',value=None,value_origin='missing'),
                   row(source_record_identifier='cancelled',event_status='cancelled')])
    status=mod('coverage.inventory').dataset_status(ledger)
    assert status['active_observations']==2
    assert status['observations_with_value']==1
    assert status['synthetic_observations']==2 and status['real_observations']==0
    assert status['coverage_percent'] is None
    assert status['reporter_countries_observed']==['BR']
    assert status['source_scoped_company_identities']==1
    assert status['global_unique_legal_entities_verified'] is False


def test_status_separates_sources_and_fob_cif(ledger):
    ledger.ingest([row(),row(source_identifier='demo-synthetic',value_basis='CIF')])
    status=mod('coverage.inventory').dataset_status(ledger)
    assert len(status['slices'])==2
    assert 'total_value' not in status
    assert {x['value_basis'] for x in status['slices']}=={'FOB','CIF'}


def test_cli_capture_status_provenance(tmp_path):
    db=tmp_path/'cli.sqlite';file=tmp_path/'capture.json'
    cap=envelope([row(source_identifier='demo-synthetic')],source_identifier='demo-synthetic')
    file.write_text(json.dumps(cap))
    assert invoke('init','--db',db).returncode==0
    response=invoke('import-capture','--db',db,'--file',file)
    assert response.returncode==0,response.stderr
    status=invoke('dataset-status','--db',db)
    assert status.returncode==0,status.stderr
    assert json.loads(status.stdout)['active_observations']==1
    response=invoke('provenance','--db',db,'--source','demo-synthetic','--record',row()['source_record_identifier'])
    assert response.returncode==0,response.stderr
    assert len(json.loads(response.stdout)['captures'])==1


def test_cli_hmrc_page_size_dry_run():
    out=invoke('fetch-hmrc','--hs6','090111','--start','2026-01','--end','2026-01','--flow','M',
               '--page-size','2','--resume','--dry-run')
    assert out.returncode==0,out.stderr
    assert '%24top=2' in json.loads(out.stdout)['query_url']


def test_inventory_api_dispatch(ledger):
    status,result=mod('server').dispatch(ledger,'/v1/dataset-status',{})
    assert status==200 and result['active_observations']==0


def test_capture_lookup_does_not_commit_caller_transaction(ledger):
    c=mod('collection.captures');c.list_captures(ledger)
    ledger.connection.execute('CREATE TABLE scratch_probe (value TEXT)')
    ledger.connection.execute("INSERT INTO scratch_probe VALUES ('uncommitted')")
    assert ledger.connection.in_transaction
    c.list_captures(ledger)
    assert ledger.connection.in_transaction
    ledger.connection.rollback()
    assert ledger.connection.execute('SELECT COUNT(*) FROM scratch_probe').fetchone()[0]==0


def test_conflicting_capture_does_not_become_supporting_evidence(ledger):
    c=mod('collection.captures');first=c.import_capture(ledger,envelope())
    second=c.import_capture(ledger,envelope([row(value='222')]))
    assert second['rejected']==1
    refs=c.provenance(ledger,'test-source',row()['source_record_identifier'],1)
    assert [r['capture_identifier'] for r in refs]==[first['capture_identifier']]


def test_capture_latest_provenance_follows_revision_not_input_order(ledger):
    c=mod('collection.captures');c.import_capture(ledger,envelope())
    newer=c.import_capture(ledger,envelope([row(source_version=2,value='456')]))
    assert c.provenance(ledger,'test-source',row()['source_record_identifier'])[0]['capture_identifier']==newer['capture_identifier']
    assert len(c.provenance(ledger,'test-source',row()['source_record_identifier'],1))==1


def test_capture_decimal_canonicalization_is_exact():
    from decimal import Decimal
    c=mod('collection.captures')
    assert c.payload_digest({'amount':Decimal('1.20')})==c.payload_digest({'amount':'1.20'})
    with pytest.raises(ValueError):c.payload_digest({'amount':1.2})
    with pytest.raises(ValueError):c.payload_digest({'amount':Decimal('NaN')})


def test_query_links_captures_and_does_not_claim_authenticity(ledger):
    c=mod('collection.captures');receipt=c.import_capture(ledger,envelope())
    result=mod('application').query_stats(ledger)
    assert result['record_authenticity_verified'] is False
    sample=result['statistics'][0]['evidence_sample'][0]
    assert sample['capture_identifiers']==[receipt['capture_identifier']]


@pytest.mark.parametrize('change',[
    {'TradeTypeId':True}, {'CommodityId':True}, {'TraderId':-1},
    {'Trader':{'TraderId':456,'CompanyName':'SYNTHETIC WRONG ID'}},
    {'Commodity':{'CommodityId':1,'Cn8Code':'09011100'}},
    {'Commodity':{'Cn8Code':'09011100','Hs6Code':'850940'}},
])
def test_hmrc_parser_rejects_conflicting_expanded_identifiers(ledger,change):
    payload=hmrc_payload();payload['value'][0].update(change)
    with pytest.raises(ValueError):mod('sources.hmrc').parse_page(payload)


def test_filtered_query_not_blocked_by_unrelated_revoked_capture(ledger):
    c=mod('collection.captures');c.import_capture(ledger,envelope())
    spec=source('other');ledger.register_source(spec)
    c.import_capture(ledger,envelope([row(source_identifier='other')],source_identifier='other'))
    spec['rights']['internal_analysis']=False
    with ledger.connection:
        ledger.connection.execute('UPDATE sources SET configuration=? WHERE source_identifier=?',
                                  (json.dumps(spec),'other'))
    result=mod('application').query_stats(ledger,source_identifier='test-source')
    assert len(result['statistics'])==1


def test_empty_hmrc_capture_requires_valid_version(ledger):
    with pytest.raises(ValueError):mod('sources.hmrc').parse_page({'value':[]},source_version=True)
