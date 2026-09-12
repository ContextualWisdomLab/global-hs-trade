from __future__ import annotations
import re
from typing import Any
from urllib.parse import urlencode
from ..coverage.catalog import country_code
from ..trade.model import hs_code,decimal_text,month,utc_timestamp,REVISIONS

REVISION_MAP={'H0':'HS1992','H1':'HS1996','H2':'HS2002','H3':'HS2007','H4':'HS2012','H5':'HS2017','H6':'HS2022','HS':'UNKNOWN'}


def build_url(reporter_code: int,hs6: str,period: str,flow: str) -> str:
    if not isinstance(reporter_code,int) or isinstance(reporter_code,bool) or reporter_code<=0:
        raise ValueError('a positive UN reporter code is required')
    if len(hs_code(hs6))!=6:raise ValueError('query requires HS6')
    if re.fullmatch(r'\d{4}',period):freq='A'
    else:month(period);freq='M'
    if flow not in {'M','X'}:raise ValueError('flow must be M or X')
    parameters={'reporterCode':reporter_code,'period':period.replace('-',''),'cmdCode':hs6,'flowCode':flow,
      'partnerCode':0,'partner2Code':0,'customsCode':'C00','motCode':0,'maxRecords':500,
      'aggregateBy':6,'breakdownMode':'classic','includeDesc':'true'}
    return f'https://comtradeapi.un.org/public/v1/preview/C/{freq}/HS?'+urlencode(parameters)


def receipt_status(number_of_records: int) -> str:
    return 'preview_not_exhaustive'


def validate_baseline(data: dict[str,Any]) -> dict[str,Any]:
    result=dict(data)
    if result.get('record_kind')!='national_aggregate' or 'parties' in result:
        raise ValueError('national aggregates cannot contain company parties')
    result['reporter_country']=country_code(result.get('reporter_country'))
    result['partner_country']=country_code(result.get('partner_country'),allow_world=True)
    code=hs_code(result.get('hs6'))
    if len(code)!=6:raise ValueError('baseline requires exactly HS6')
    result['hs6']=code
    period=result.get('period')
    if isinstance(period,str) and re.fullmatch(r'\d{4}',period):
        if not 1900<=int(period)<=2100:raise ValueError('baseline year outside supported range')
        result['period_precision']='year'
    else:result['period']=month(period);result['period_precision']='month'
    if result.get('recorded_flow') not in {'M','X'}:raise ValueError('baseline flow must be M/X')
    if result.get('hs_revision') not in REVISIONS:raise ValueError('unknown baseline revision value')
    if result.get('value_basis') not in {'FOB','CIF','CUSTOMS','UNKNOWN'}:raise ValueError('invalid baseline value basis')
    if not isinstance(result.get('value_currency'),str) or not re.fullmatch('[A-Z]{3}',result['value_currency']):
        raise ValueError('baseline currency must be explicit')
    for field in ['value','net_weight_kg','quantity']:
        result[field]=decimal_text(result.get(field),field)
    result['retrieved_at']=utc_timestamp(result.get('retrieved_at'))
    return result


def parse_page(payload: dict[str,Any]) -> list[dict[str,Any]]:
    if not isinstance(payload,dict) or not isinstance(payload.get('data'),list):
        raise ValueError('UN Comtrade response must contain a data array')
    result=[]
    for raw in payload['data']:
        try:
            period=str(raw['period'])
            if len(period)==6:period=period[:4]+'-'+period[4:]
            flow=raw['flowCode']
            if flow not in {'M','X'}:raise ValueError('unsupported Comtrade flow')
            value=raw.get('primaryValue');basis='UNKNOWN'
            if flow=='X' and raw.get('fobvalue') is not None:value=raw['fobvalue'];basis='FOB'
            if flow=='M' and raw.get('cifvalue') is not None:value=raw['cifvalue'];basis='CIF'
            partner=raw.get('partnerISO')
            if partner is None and raw.get('partnerCode')==0:partner='WORLD'
            record={'record_kind':'national_aggregate','source_identifier':'un-comtrade',
              'reporter_country':country_code(raw['reporterISO']),'partner_country':country_code(partner,allow_world=True),
              'recorded_flow':flow,'period':period,'hs6':raw['cmdCode'],
              'hs_revision':REVISION_MAP.get(raw.get('classificationCode'),'UNKNOWN'),
              'value':value,'value_currency':'USD','value_basis':basis,
              'net_weight_kg':raw.get('netWgt'),'quantity':raw.get('qty'),'quantity_unit':raw.get('qtyUnitAbbr'),
              'net_weight_estimated':raw.get('isNetWgtEstimated'),
              'is_reported':raw.get('isReported'),'is_aggregate':raw.get('isAggregate'),
              'is_original_classification':raw.get('isOriginalClassification'),
              'customs_code':raw.get('customsCode','C00'),'transport_mode':raw.get('motCode',0),
              'coverage':'preview_not_exhaustive','source_url':'https://uncomtrade.org/docs/un-comtrade-api/',
              'retrieved_at':utc_timestamp()}
            result.append(validate_baseline(record))
        except (KeyError,TypeError,ValueError) as exc:
            raise ValueError('UN Comtrade schema/field validation failed: '+str(exc)) from exc
    return result
