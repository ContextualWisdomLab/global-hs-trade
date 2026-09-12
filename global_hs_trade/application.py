from __future__ import annotations
from typing import Any
from .coverage.catalog import country_code
from .trade.model import hs_code, month, ROLES
from .sources import hmrc, comtrade
from .sources.http import HttpClient
from .storage import Ledger


def query_stats(ledger: Ledger, *, hs6: str | None=None, reporter_country: str | None=None,
                company_country: str | None=None, role: str | None=None, company: str | None=None,
                start: str | None=None, end: str | None=None, recorded_flow: str | None=None,
                source_identifier: str | None=None, dataset_kind: str | None=None) -> dict[str,Any]:
    if hs6 is not None:
        hs6=hs_code(hs6)
        if len(hs6)!=6:raise ValueError('query requires an HS6 string')
    if reporter_country is not None:reporter_country=country_code(reporter_country)
    if company_country is not None:company_country=country_code(company_country)
    if role is not None and role not in ROLES:raise ValueError('unrecognized party role')
    if start:start=month(start)
    if end:end=month(end)
    if start and end and start>end:raise ValueError('start must not follow end')
    if recorded_flow is not None and recorded_flow not in {'M','X'}:raise ValueError('flow must be M or X')
    if dataset_kind is not None and dataset_kind not in {'real','synthetic'}:raise ValueError('invalid dataset_kind')
    if company is not None and (not isinstance(company,str) or len(company)>1024):raise ValueError('company filter is too long')
    if source_identifier is not None:ledger.source(source_identifier)
    filters=dict(hs6=hs6,reporter_country=reporter_country,company_country=company_country,role=role,
       company=company,start=start,end=end,recorded_flow=recorded_flow,
       source_identifier=source_identifier,dataset_kind=dataset_kind)
    statistics=ledger.stats(**filters)
    from .collection.captures import capture_reference_index
    references=capture_reference_index(ledger,{group['source_identifier'] for group in statistics})
    for group in statistics:
        for evidence in group['evidence_sample']:
            evidence['capture_identifiers']=references.get((group['source_identifier'],
                evidence['source_record_identifier'],evidence['source_version']),[])
    return {'status':'observed_records' if statistics else 'no_observed_records',
       'scope':'Source-qualified company observations; reporting direction is not automatically the company trade direction.',
       'complete_company_coverage':False,'record_authenticity_verified':False,'filters':filters,
       'cross_source_totals_allowed':False,'statistics':statistics}


def fetch_hmrc(ledger: Ledger,hs6: str,start: str,end: str,flow: str,*,max_pages: int=3,
               source_version: int=1,client: Any=None,page_size: int=1000,resume: bool=False) -> dict[str,Any]:
    from .collection import checkpoints
    if isinstance(max_pages,bool) or not isinstance(max_pages,int) or not 1<=max_pages<=10000:
        raise ValueError('max_pages must be between 1 and 10000')
    if isinstance(source_version,bool) or not isinstance(source_version,int) or not 1<=source_version<=2**53:
        raise ValueError('invalid source version')
    url=hmrc.build_url(hs6,start,end,flow,page_size)
    ledger._right('hmrc-traders','internal_analysis')
    key=checkpoints.identifier(url,source_version)
    previous=checkpoints.load(ledger,key)
    revision=previous['revision'] if previous else None
    state=previous['state'] if resume and previous else {
        'query_url':url,'source_version':source_version,'offset':0,'last_key':None,
        'next_page_url':url,'complete':False}
    receipt={'source_identifier':'hmrc-traders','query_url':url,'status':'failed',
       'pages_received':0,'inserted':0,'replayed':0,'rejected':0,
       'company_value_coverage':False,'population_completeness':'not_asserted',
       'snapshot_consistency':'not_guaranteed','pagination_mode':'client_offset',
       'source_version':source_version,'max_pages':max_pages,'page_size':page_size,
       'checkpoint_identifier':key,'resumed':bool(resume and previous),
       'next_page_url':state['next_page_url']}
    client=client or HttpClient()
    if state['complete']:
        receipt['status']='query_pages_exhausted'
        ledger.record_run(receipt)
        return receipt
    try:
        # Only local checkpoint writes occur here. No transaction spans HTTP or parsing.
        revision=checkpoints.save(ledger,key,state,revision)
        for page in range(max_pages):
            page_url=hmrc.with_offset(url,state['offset'])
            payload=client.get(page_url)
            receipt['pages_received']+=1
            rows,last_key,has_next=hmrc.validate_page(payload,hs6,start,end,flow,page_size,state['last_key'],page_url)
            # parse_page supplies a default version; apply the explicitly selected revision.
            for row in rows: row['source_version']=source_version
            outcome=ledger.ingest(rows)
            for field in ['inserted','replayed','rejected']:receipt[field]+=outcome[field]
            receipt['last_page_url']=page_url
            if outcome['rejected']:
                receipt['status']='completed_with_rejections'
                receipt['next_page_url']=page_url
                break
            offset=state['offset']+len(rows)
            complete=len(rows)<page_size and not has_next
            state=dict(state,offset=offset,last_key=last_key,complete=complete,
                next_page_url=None if complete else hmrc.with_offset(url,offset))
            revision=checkpoints.save(ledger,key,state,revision)
            receipt['next_page_url']=state['next_page_url']
            receipt['status']='query_pages_exhausted' if complete else 'page_limit_reached'
            if complete: break
    except (ValueError,ConnectionError,TypeError,KeyError,PermissionError) as exc:
        receipt['status']='partial_failure' if receipt['inserted'] or receipt['replayed'] else 'failed'
        receipt['error']=str(exc)
    ledger.record_run(receipt)
    return receipt


def fetch_comtrade(ledger: Ledger,reporter_code: int,hs6: str,period: str,flow: str,*,client: Any=None) -> dict[str,Any]:
    url=comtrade.build_url(reporter_code,hs6,period,flow)
    ledger._right('un-comtrade','internal_analysis')
    receipt={'source_identifier':'un-comtrade','query_url':url,'status':'failed',
       'company_data':False,'national_records_received':0,'records_saved':0}
    client=client or HttpClient()
    try:
        payload=client.get(url)
        rows=comtrade.parse_page(payload)
        receipt['national_records_received']=len(rows)
        receipt['records_saved']=ledger.save_baselines(rows)
        receipt['status']=comtrade.receipt_status(len(rows))
    except (ValueError,ConnectionError,TypeError,KeyError,PermissionError) as exc:
        receipt['error']=str(exc)
    ledger.record_run(receipt)
    return receipt
