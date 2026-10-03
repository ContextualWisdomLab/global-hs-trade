from copy import deepcopy
from urllib.parse import parse_qs, urlsplit
import pytest
from .helpers import mod
from .test_application import ledger, hmrc_payload


def batch(*ids):
    values=[]
    for i in ids:
        v=deepcopy(hmrc_payload()['value'][0]); v['TraderId']=i
        v['Trader']['CompanyName']=f'SYNTHETIC {i}'
        values.append(v)
    return {'value':values}

class Feed:
    def __init__(self, responses, ledger):
        self.responses=iter(responses); self.urls=[]; self.ledger=ledger
    def get(self,url):
        assert not self.ledger.connection.in_transaction
        self.urls.append(url)
        answer=next(self.responses)
        if isinstance(answer,Exception): raise answer
        return answer

def test_full_top_without_nextlink_continues(ledger):
    client=Feed([batch(1,2),batch(3)],ledger)
    result=mod('application').fetch_hmrc(ledger,'090111','2026-01','2026-01','M',page_size=2,client=client)
    assert result['inserted']==3
    assert result['status']=='query_pages_exhausted'
    assert len(client.urls)==2
    assert parse_qs(urlsplit(client.urls[1]).query)['$skip']==['2']

def test_failed_second_page_resumes_not_restarts(ledger):
    fn=mod('application').fetch_hmrc
    c1=Feed([batch(1,2),ConnectionError('DNS unavailable')],ledger)
    first=fn(ledger,'090111','2026-01','2026-01','M',page_size=2,client=c1)
    assert first['status']=='partial_failure'
    c2=Feed([batch(3)],ledger)
    second=fn(ledger,'090111','2026-01','2026-01','M',page_size=2,resume=True,client=c2)
    assert second['inserted']==1 and second['resumed']
    assert parse_qs(urlsplit(c2.urls[0]).query)['$skip']==['2']
    assert len(ledger.observations())==3

def test_maxpages_preserves_unconsumed_cursor(ledger):
    fn=mod('application').fetch_hmrc
    first=fn(ledger,'090111','2026-01','2026-01','M',page_size=2,max_pages=1,client=Feed([batch(1,2)],ledger))
    assert first['status']=='page_limit_reached' and first['next_page_url']
    second=fn(ledger,'090111','2026-01','2026-01','M',page_size=2,resume=True,client=Feed([batch()],ledger))
    assert second['status']=='query_pages_exhausted'

def test_exact_multiple_gets_empty_final_page(ledger):
    c=Feed([batch(1,2),batch()],ledger)
    result=mod('application').fetch_hmrc(ledger,'090111','2026-01','2026-01','M',page_size=2,client=c)
    assert result['pages_received']==2 and result['status']=='query_pages_exhausted'

def test_conflict_does_not_advance_checkpoint(ledger):
    ledger.ingest(mod('sources.hmrc').parse_page(batch(1)))
    changed=batch(1,2);changed['value'][0]['Trader']['CompanyName']='SYNTHETIC CHANGED'
    result=mod('application').fetch_hmrc(ledger,'090111','2026-01','2026-01','M',page_size=2,client=Feed([changed],ledger))
    assert result['status']=='completed_with_rejections'
    assert result['next_page_url']==result['query_url']
    assert result['rejected']==1

def test_completed_resume_performs_no_http(ledger):
    fn=mod('application').fetch_hmrc
    fn(ledger,'090111','2026-01','2026-01','M',page_size=2,client=Feed([batch(1)],ledger))
    c=Feed([],ledger)
    result=fn(ledger,'090111','2026-01','2026-01','M',page_size=2,resume=True,client=c)
    assert result['status']=='query_pages_exhausted' and not c.urls

def test_unapproved_nextlink_does_not_fetch(ledger):
    payload=batch(1);payload['@odata.nextLink']='https://evil.example/steal'
    c=Feed([payload],ledger)
    result=mod('application').fetch_hmrc(ledger,'090111','2026-01','2026-01','M',page_size=2,client=c)
    assert result['status']=='failed' and len(c.urls)==1
    assert not ledger.observations()

def test_schema_mismatch_against_requested_hs_rejected(ledger):
    payload=batch(1);payload['value'][0]['Commodity']['Cn8Code']='85094000'
    result=mod('application').fetch_hmrc(ledger,'090111','2026-01','2026-01','M',client=Feed([payload],ledger))
    assert result['status']=='failed' and not ledger.observations()

def test_paging_repeat_is_not_silent_exhaustion(ledger):
    c=Feed([batch(1,2),batch(1,2)],ledger)
    result=mod('application').fetch_hmrc(ledger,'090111','2026-01','2026-01','M',page_size=2,client=c)
    assert result['status']=='partial_failure' and 'repeat' in result['error'].lower()

@pytest.mark.parametrize('size',[0,True,40001])
def test_invalid_page_size_fails(ledger,size):
    with pytest.raises(ValueError):
        mod('application').fetch_hmrc(ledger,'090111','2026-01','2026-01','M',page_size=size,client=Feed([],ledger))


def test_malformed_false_nextlink_rejected(ledger):
    payload=batch(1);payload['@odata.nextLink']=False
    result=mod('application').fetch_hmrc(ledger,'090111','2026-01','2026-01','M',client=Feed([payload],ledger))
    assert result['status']=='failed' and not ledger.observations()
