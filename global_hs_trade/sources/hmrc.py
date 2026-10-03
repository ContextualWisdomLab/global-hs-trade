from __future__ import annotations
from typing import Any
from urllib.parse import urlencode, urlsplit, parse_qs, urljoin
from ..trade.model import hs_code,month,normalize_observation,utc_timestamp

BASE_URL='https://api.uktradeinfo.com/Trade'


def build_url(hs6: str,start: str,end: str,flow: str,page_size: int=1000) -> str:
    hs6=hs_code(hs6)
    if len(hs6)!=6:raise ValueError('HMRC query requires HS6')
    start=month(start);end=month(end)
    if start>end:raise ValueError('start month must not follow end month')
    if flow not in {'M','X'}:raise ValueError('flow must be M or X')
    if isinstance(page_size,bool) or not isinstance(page_size,int) or not 1<=page_size<=40000:raise ValueError('page_size must be 1..40000')
    query={'$filter':f"Commodity/Hs6Code eq '{hs6}' and MonthId ge {start.replace('-','')} and MonthId le {end.replace('-','')} and TradeTypeId eq {1 if flow=='M' else 2}",
      '$expand':'Trader,Commodity','$orderby':'MonthId,TraderId,CommodityId,TradeTypeId','$top':str(page_size)}
    return BASE_URL+'?'+urlencode(query)


def parse_page(payload: dict[str,Any],source_version: int=1) -> list[dict[str,Any]]:
    if type(source_version) is not int or not 1<=source_version<=2**53:
        raise ValueError('invalid HMRC source version')
    if not isinstance(payload,dict) or not isinstance(payload.get('value'),list):
        raise ValueError('HMRC response must have a value array')
    result=[]
    for raw in payload['value']:
        try:
            trader=raw['Trader'];commodity=raw['Commodity']
            if not isinstance(trader,dict) or not isinstance(commodity,dict):raise ValueError('missing expanded entities')
            kind=raw['TradeTypeId']
            if type(kind) is not int or kind not in {1,2}:raise ValueError('unrecognized HMRC TradeTypeId')
            for field in ['TraderId','CommodityId','MonthId']:
                if type(raw.get(field)) is not int or raw[field]<=0:
                    raise ValueError(field+' must be a positive integer')
            for expanded,field in [(trader,'TraderId'),(commodity,'CommodityId')]:
                if field in expanded and (type(expanded[field]) is not int or expanded[field]!=raw[field]):
                    raise ValueError('expanded '+field+' conflicts with the trade record')
            code=commodity.get('Cn8Code')
            if code is None:code=commodity.get('Hs6Code')
            if not isinstance(code,str):raise ValueError('HS/CN string is absent; do not reconstruct it from the numeric CommodityId')
            code=hs_code(code)
            if commodity.get('Hs6Code') is not None:
                stated=hs_code(commodity['Hs6Code'])
                if len(stated)!=6 or stated!=code[:6]:
                    raise ValueError('expanded HS6 conflicts with the CN code')
            raw_month=str(raw['MonthId'])
            if len(raw_month)!=6:raise ValueError('invalid HMRC MonthId')
            period=month(raw_month[:4]+'-'+raw_month[4:])
            trader_identifier=raw['TraderId']
            if not isinstance(trader_identifier,int) or isinstance(trader_identifier,bool):raise ValueError('invalid TraderId')
            record={'source_identifier':'hmrc-traders','source_record_identifier':':'.join(str(raw[k]) for k in ['TraderId','CommodityId','MonthId','TradeTypeId']),
              'source_version':source_version,'record_kind':'trader_presence','period':period,
              'date_basis':'hmrc_trade_month','reporter_country':'GB','recorded_flow':'M' if kind==1 else 'X',
              'hs_code':code,'hs_revision':'UNKNOWN','hs_code_origin':'reported','value':None,'value_origin':'missing',
              'value_currency':None,'value_basis':'UNKNOWN','net_weight_kg':None,'gross_weight_kg':None,
              'parties':[{'role':'importer' if kind==1 else 'exporter','legal_name':trader['CompanyName'],
                'external_identifier':str(trader_identifier),'country_code':None}],
              'source_url':BASE_URL,'retrieved_at':utc_timestamp()}
            result.append(normalize_observation(record))
        except (KeyError,TypeError,ValueError) as exc:
            raise ValueError('HMRC schema/field validation failed: '+str(exc)) from exc
    return result


def with_offset(url: str, offset: int) -> str:
    from .http import validate_url
    validate_url(url, {'api.uktradeinfo.com'})
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ValueError('invalid HMRC offset')
    query = parse_qs(urlsplit(url).query)
    if any(len(v) != 1 for v in query.values()):
        raise ValueError('duplicate HMRC query parameters')
    query = {k: v[0] for k, v in query.items()}
    if offset:
        query['$skip'] = str(offset)
    else:
        query.pop('$skip', None)
    return BASE_URL + '?' + urlencode(query)


def validate_page(payload: dict, requested_hs6: str, start: str, end: str, flow: str,
                  page_size: int, last_key: list[int] | None, page_url: str) -> tuple[list[dict], list[int] | None, bool]:
    from .http import validate_url
    requested_hs6 = hs_code(requested_hs6)
    if len(requested_hs6) != 6:
        raise ValueError('HMRC query requires HS6')
    rows = parse_page(payload)
    if len(rows) > page_size:
        raise ValueError('HMRC response exceeded the requested page size')
    next_link = payload.get('@odata.nextLink')
    if next_link is not None and not isinstance(next_link, str):
        raise ValueError('invalid nextLink type')
    if next_link:
        if not isinstance(next_link, str):
            raise ValueError('invalid nextLink type')
        target = validate_url(urljoin(page_url, next_link), {'api.uktradeinfo.com'})
        if urlsplit(target).path != '/Trade':
            raise ValueError('HMRC continuation changed entity endpoint')
        if not rows:
            raise ValueError('empty HMRC page unexpectedly has a continuation')
    cursor = last_key
    for raw, row in zip(payload['value'], rows):
        if row['hs6'] != requested_hs6 or not start <= row['period'] <= end or row['recorded_flow'] != flow:
            raise ValueError('HMRC response is outside the requested HS, period or flow')
        key = [raw[k] for k in ['MonthId', 'TraderId', 'CommodityId', 'TradeTypeId']]
        if any(isinstance(v, bool) or not isinstance(v, int) for v in key):
            raise ValueError('HMRC ordering keys must be integers')
        if cursor is not None and key <= cursor:
            raise ValueError('repeated or out-of-order HMRC page; upstream collection may have changed')
        cursor = key
    return rows, cursor, bool(next_link)
