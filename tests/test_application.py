import json
import subprocess
import sys
from pathlib import Path
import pytest
from .helpers import mod,row,source

@pytest.fixture
def ledger(tmp_path):
    with mod('storage').Ledger(tmp_path/'trade.sqlite') as ledger:
        for spec in mod('coverage.catalog').builtin_sources(): ledger.register_source(spec)
        ledger.register_source(source())
        yield ledger

def hmrc_payload():
    return {'value':[{'TraderId':123,'CommodityId':9011100,'MonthId':202601,'TradeTypeId':1,
        'Trader':{'CompanyName':'SYNTHETIC UK TRADER'},'Commodity':{'Cn8Code':'09011100'}}]}

class Client:
    def __init__(self,payload=None,error=None): self.payload=payload; self.error=error
    def get(self,url):
        if self.error:raise self.error
        return self.payload

def test_company_country_is_distinct_from_reporting_country(ledger):
    ledger.ingest([row(reporter_country='VN',recorded_flow='M',parties=[{
      'role':'supplier','legal_name':'SYNTHETIC German supplier','country_code':'DE','external_identifier':'de1'}])])
    results=mod('application').query_stats(ledger,hs6='090111',company_country='DE',role='supplier')
    assert len(results['statistics'])==1
    assert results['statistics'][0]['reporter_country']=='VN'
    assert mod('application').query_stats(ledger,company_country='VN')['status']=='no_observed_records'

def test_unknown_country_query_fails_instead_of_empty_success(ledger):
    with pytest.raises(ValueError):mod('application').query_stats(ledger,company_country='ZZ')

def test_invalid_hs_and_reversed_months_fail(ledger):
    with pytest.raises(ValueError):mod('application').query_stats(ledger,hs6='09011100')
    with pytest.raises(ValueError):mod('application').query_stats(ledger,start='2026-02',end='2026-01')

def test_empty_query_is_not_zero_trade(ledger):
    result=mod('application').query_stats(ledger,hs6='090111')
    assert result['statistics']==[] and result['status']=='no_observed_records'
    assert result['complete_company_coverage'] is False

def test_hmrc_fetch_receipt_and_value_absence(ledger):
    receipt=mod('application').fetch_hmrc(ledger,'090111','2026-01','2026-01','M',client=Client(hmrc_payload()))
    assert receipt['status']=='query_pages_exhausted' and receipt['inserted']==1
    assert receipt['company_value_coverage'] is False
    assert ledger.stats()[0]['observed_value'] is None
    assert ledger.runs()[-1]['receipt']['status']=='query_pages_exhausted'

def test_fetch_failure_has_audit_and_non_success_status(ledger):
    receipt=mod('application').fetch_hmrc(ledger,'090111','2026-01','2026-01','M',client=Client(error=ConnectionError('DNS unavailable')))
    assert receipt['status']=='failed' and receipt['pages_received']==0
    assert 'DNS' in receipt['error']
    assert len(ledger.runs())==1

def test_fetch_rejections_are_not_marked_complete(ledger):
    ledger.ingest(mod('sources.hmrc').parse_page(hmrc_payload()))
    changed=hmrc_payload();changed['value'][0]['Trader']['CompanyName']='SYNTHETIC CHANGED'
    receipt=mod('application').fetch_hmrc(ledger,'090111','2026-01','2026-01','M',client=Client(changed))
    assert receipt['status']=='completed_with_rejections' and receipt['rejected']==1

def test_network_io_never_holds_transaction(ledger):
    class CheckClient:
        def get(self,url):
            assert not ledger.connection.in_transaction
            return hmrc_payload()
    assert mod('application').fetch_hmrc(ledger,'090111','2026-01','2026-01','M',client=CheckClient())['inserted']==1

def test_comtrade_receipt_does_not_claim_full_data(ledger):
    receipt=mod('application').fetch_comtrade(ledger,76,'090111','2024','X',client=Client({'data':[]}))
    assert receipt['status']=='preview_not_exhaustive'
    assert ledger.stats()==[] and receipt['company_data'] is False

def invoke(*args):
    return subprocess.run([sys.executable,'-m','global_hs_trade',*map(str,args)],capture_output=True,text=True,timeout=15)

def test_cli_init_ingest_query(tmp_path):
    db=tmp_path/'cli.sqlite'; data=tmp_path/'rows.jsonl'
    data.write_text(json.dumps(row(source_identifier='demo-synthetic'))+'\n')
    result=invoke('init','--db',db)
    assert result.returncode==0,result.stderr
    result=invoke('ingest','--db',db,'--file',data)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)['inserted']==1
    result=invoke('query','--db',db,'--hs6','090111','--company-country','BR','--role','exporter')
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)['statistics'][0]['observed_value']=='1234.56'

def test_cli_missing_database_is_error_not_empty_database(tmp_path):
    db=tmp_path/'absent.sqlite'
    result=invoke('query','--db',db)
    assert result.returncode!=0 and not db.exists()

def test_cli_dry_run_needs_no_db_or_network():
    result=invoke('fetch-hmrc','--hs6','090111','--start','2026-01','--end','2026-02','--flow','M','--dry-run')
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)['network_called'] is False

def test_cli_coverage_not_connected():
    result=invoke('coverage','--country','DE','--flow','X')
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)['company_values_live_connected'] is False

def test_cli_rejected_input_nonzero(tmp_path):
    db=tmp_path/'bad.sqlite';data=tmp_path/'bad.jsonl'
    invoke('init','--db',db)
    data.write_text(json.dumps(row(source_identifier='missing-policy'))+'\n')
    result=invoke('ingest','--db',db,'--file',data)
    assert result.returncode!=0 and json.loads(result.stdout)['rejected']==1

def test_cli_refuses_unbounded_listen_address(tmp_path):
    result=invoke('serve','--db',tmp_path/'absent.sqlite','--host','0.0.0.0')
    assert result.returncode!=0

def test_server_dispatch_readonly_and_filtering(ledger):
    ledger.ingest([row()])
    status,body=mod('server').dispatch(ledger,'/v1/trade-stats',{'hs6':'090111','company_country':'BR'})
    assert status==200 and len(body['statistics'])==1
    assert mod('server').dispatch(ledger,'/v1/trade-stats',{'sql':'DROP TABLE observations'})[0]==400
    assert mod('server').dispatch(ledger,'/v1/unknown',{})[0]==404

def test_server_only_allows_loopback_host_headers():
    server=mod('server')
    assert server.valid_host('127.0.0.1:8765',8765)
    assert server.valid_host('localhost:8765',8765)
    assert not server.valid_host('attacker.example:8765',8765)
    assert not server.valid_host('127.0.0.1:80',8765)
