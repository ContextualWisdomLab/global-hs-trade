from .helpers import mod,row,source
import pytest

@pytest.fixture
def ledger(tmp_path):
    with mod('storage').Ledger(tmp_path/'review.sqlite') as db:
        db.register_source(source());yield db

def test_aliases_under_same_source_identity_do_not_split_company(ledger):
    a=row();b=row(source_record_identifier='declaration-2')
    b['parties'][0]['legal_name']='SYNTHETIC Coffee Brasil Limited'
    ledger.ingest([a,b])
    stats=ledger.stats()
    assert len(stats)==1
    assert stats[0]['observed_value']=='2469.12'
    assert len(stats[0]['observed_company_names'])==2

def test_alias_query_returns_full_same_identity_group(ledger):
    a=row();b=row(source_record_identifier='declaration-2')
    b['parties'][0]['legal_name']='SYNTHETIC Coffee Brasil Limited'
    ledger.ingest([a,b])
    stats=ledger.stats(company='Limited')
    assert len(stats)==1 and stats[0]['observed_value']=='2469.12'

def test_baseline_read_enforces_source_analysis_permission(ledger):
    # Permissions are also enforced on read, including a database whose policy was externally restricted.
    spec=source('restricted-baseline');ledger.register_source(spec)
    from global_hs_trade.sources.comtrade import validate_baseline
    baseline={'source_identifier':'restricted-baseline','record_kind':'national_aggregate',
      'reporter_country':'BR','partner_country':'WORLD','period':'2024','recorded_flow':'X','hs6':'090111',
      'hs_revision':'HS1992','value':'1','value_currency':'USD','value_basis':'FOB'}
    ledger.save_baselines([baseline])
    spec['rights']['internal_analysis']=False
    import json
    with ledger.connection:
        ledger.connection.execute('UPDATE sources SET configuration=? WHERE source_identifier=?',(json.dumps(spec),'restricted-baseline'))
    with pytest.raises(PermissionError):ledger.baselines()

def test_http_integration_loopback(tmp_path):
    from threading import Thread
    from urllib.request import urlopen,Request
    from urllib.error import HTTPError
    import json
    with mod('storage').Ledger(tmp_path/'api.sqlite') as db:
        db.register_source(source());db.ingest([row()])
    server=mod('server').make_server(tmp_path/'api.sqlite',0)
    thread=Thread(target=server.serve_forever,kwargs={'poll_interval':0.01},daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    try:
        with urlopen(base+'/v1/trade-stats?hs6=090111',timeout=3) as response:
            payload=json.load(response)
            assert payload['statistics'][0]['observed_value']=='1234.56'
            assert response.headers['Cache-Control']=='no-store'
        with pytest.raises(HTTPError) as err:
            urlopen(Request(base+'/health',headers={'Origin':'https://untrusted.example'}),timeout=3)
        assert err.value.code==403
        err.value.close()
        with pytest.raises(HTTPError) as err:
            urlopen(Request(base+'/v1/trade-stats',data=b'{}',method='POST'),timeout=3)
        assert err.value.code==405
        err.value.close()
    finally:server.shutdown();thread.join(timeout=3);server.server_close()
