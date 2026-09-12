import json
from urllib.parse import parse_qs,urlsplit
from tests.helpers import mod
import pytest

def hmrc_payload():
    return {'value':[{'TraderId':123,'CommodityId':9011100,'MonthId':202601,'TradeTypeId':1,
       'Trader':{'TraderId':123,'CompanyName':'SYNTHETIC British Trader Ltd'},
       'Commodity':{'Cn8Code':'09011100','Hs6Code':'090111'}}]}

def test_hmrc_expands_original_entities():
    url=mod('sources.hmrc').build_url('090111','2026-01','2026-02','M')
    params=parse_qs(urlsplit(url).query)
    assert urlsplit(url).path=='/Trade'
    assert 'Trader' in params['$expand'][0] and 'Commodity' in params['$expand'][0]
    assert 'TradeTypeId eq 1' in params['$filter'][0]

def test_hmrc_does_not_invent_money_or_country():
    records=mod('sources.hmrc').parse_page(hmrc_payload())
    assert records[0]['hs_code']=='09011100'
    assert records[0]['value'] is None
    assert records[0]['parties'][0]['country_code'] is None
    assert records[0]['record_kind']=='trader_presence'

def test_hmrc_missing_expansion_is_schema_error():
    p=hmrc_payload();del p['value'][0]['Trader']
    with pytest.raises(ValueError):mod('sources.hmrc').parse_page(p)

def test_hmrc_missing_leading_zero_not_reconstructed():
    p=hmrc_payload();p['value'][0]['Commodity']['Cn8Code']=9011100
    with pytest.raises(ValueError):mod('sources.hmrc').parse_page(p)

def test_hmrc_invalid_flow_rejected():
    p=hmrc_payload();p['value'][0]['TradeTypeId']=99
    with pytest.raises(ValueError):mod('sources.hmrc').parse_page(p)

def test_dates_must_be_ordered():
    with pytest.raises(ValueError):mod('sources.hmrc').build_url('090111','2026-02','2026-01','M')

def test_comtrade_preview_is_not_company_data():
    p={'data':[{'period':202401,'reporterISO':'BRA','partnerISO':'DEU','flowCode':'X','cmdCode':'090111',
       'classificationCode':'H6','primaryValue':'1000.50','fobvalue':'1000.50','netWgt':'120','isNetWgtEstimated':False,
       'isReported':True,'isAggregate':False,'qty':'120','qtyUnitAbbr':'kg'}]}
    result=mod('sources.comtrade').parse_page(p)[0]
    assert result['record_kind']=='national_aggregate'
    assert 'parties' not in result
    assert result['reporter_country']=='BR'
    assert result['value']=='1000.50'
    assert result['hs_revision']=='HS2022'

def test_comtrade_annual_not_fabricated_as_month():
    p={'data':[{'period':2024,'reporterISO':'BRA','partnerISO':'W00','flowCode':'X','cmdCode':'090111',
       'classificationCode':'H6','primaryValue':None,'fobvalue':None,'netWgt':None}]}
    result=mod('sources.comtrade').parse_page(p)[0]
    assert result['period']=='2024' and result['period_precision']=='year'
    assert result['value'] is None

def test_preview_receipt_always_conservative():
    assert mod('sources.comtrade').receipt_status(3)=='preview_not_exhaustive'
    assert mod('sources.comtrade').receipt_status(500)=='preview_not_exhaustive'

def test_comtrade_build_url_not_an_invented_paid_endpoint():
    url=mod('sources.comtrade').build_url(76,'090111','2024','X')
    assert '/public/v1/preview/C/A/HS' in url
    assert parse_qs(urlsplit(url).query)['cmdCode']==['090111']

@pytest.mark.parametrize('url',['http://api.uktradeinfo.com/Trade','https://evil.example/Trade',
 'https://api.uktradeinfo.com@evil.example/Trade','https://127.0.0.1/Trade','https://api.uktradeinfo.com:444/Trade'])
def test_http_and_pagination_reject_unapproved_hosts(url):
    with pytest.raises(ValueError):mod('sources.http').validate_url(url,{'api.uktradeinfo.com'})

def test_pagination_follows_nextlink():
    first='https://api.uktradeinfo.com/Trade?a=1';second=first+'&page=2'
    data={first:{'value':[1],'@odata.nextLink':second},second:{'value':[2]}}
    pages=list(mod('sources.http').iter_pages(first,data.__getitem__,max_pages=3))
    assert len(pages)==2 and pages[-1][2]=='query_pages_exhausted'

def test_pagination_limit_visible():
    first='https://api.uktradeinfo.com/Trade?a=1'
    pages=list(mod('sources.http').iter_pages(first,lambda u:{'value':[1],'@odata.nextLink':u+'&next=1'},max_pages=1))
    assert pages[0][2]=='page_limit_reached'

def test_pagination_loop_is_error():
    u='https://api.uktradeinfo.com/Trade'
    with pytest.raises(ValueError):list(mod('sources.http').iter_pages(u,lambda _: {'value':[],'@odata.nextLink':u},max_pages=3))

def test_csv_mapping_no_implicit_provider_schema():
    mapping={'source_identifier':'custom','constants':{'record_kind':'customs_line','hs_revision':'UNKNOWN',
       'recorded_flow':'X','reporter_country':'BR'},'fields':{'source_record_identifier':'record','period':'month',
       'hs_code':'tariff','value':'amount','value_currency':'currency','value_basis':'basis'},
       'parties':{'exporter':{'legal_name':'seller','external_identifier':'seller_id','country_code':'seller_country'}}}
    data=[{'record':'A1','month':'2026-01','tariff':'09011100','amount':'12.34','currency':'USD','basis':'FOB',
       'seller':'SYNTHETIC Seller','seller_id':'s1','seller_country':'BR'}]
    records=list(mod('sources.files').map_csv_rows(data,mapping))
    assert records[0]['parties'][0]['role']=='exporter'
    assert records[0]['value']=='12.34'

def test_csv_missing_mapped_field_fails():
    mapping={'source_identifier':'x','fields':{'hs_code':'nonexistent'},'parties':{},'constants':{}}
    with pytest.raises(ValueError):list(mod('sources.files').map_csv_rows([{'hs':'090111'}],mapping))
