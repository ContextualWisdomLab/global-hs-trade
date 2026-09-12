from copy import deepcopy
from decimal import Decimal
import pytest
from tests.helpers import mod, row

def test_valid_record_keeps_leading_zero():
    record=mod('trade.model').normalize_observation(row())
    assert record['hs6']=='090111'
    assert record['value']=='1234.56'

@pytest.mark.parametrize('code',['90111',9011100,'090111,090112','not-a-code',''])
def test_invalid_hs_never_guessed(code):
    with pytest.raises(ValueError):mod('trade.model').normalize_observation(row(hs_code=code))

def test_formatted_hs():
    assert mod('trade.model').normalize_observation(row(hs_code='09 01.11 00'))['hs6']=='090111'

@pytest.mark.parametrize('value',['NaN','Infinity','-1',True,1.23,'1,234.56'])
def test_nonfinite_negative_float_or_ambiguous_money_rejected(value):
    with pytest.raises(ValueError):mod('trade.model').normalize_observation(row(value=value))

def test_large_decimal_has_no_binary_float_loss():
    amount='9007199254740993.123456789'
    assert mod('trade.model').normalize_observation(row(value=amount))['value']==amount

def test_missing_is_not_zero():
    result=mod('trade.model').normalize_observation(row(value=None,value_origin='missing'))
    assert result['value'] is None

@pytest.mark.parametrize('period',['2026-13','2026-00','2026-1','2026','2026-01-12'])
def test_invalid_month_rejected(period):
    with pytest.raises(ValueError):mod('trade.model').normalize_observation(row(period=period))

def test_unknown_revision_is_preserved():
    assert mod('trade.model').normalize_observation(row(hs_revision='UNKNOWN'))['hs_revision']=='UNKNOWN'

def test_invalid_country_is_not_accepted():
    with pytest.raises(ValueError):mod('trade.model').normalize_observation(row(reporter_country='ZZ'))

def test_supplier_is_not_exporter():
    parties=deepcopy(row()['parties']);parties[0]['role']='supplier'
    result=mod('trade.model').normalize_observation(row(parties=parties,reporter_country='VN',recorded_flow='M',origin_country='CN'))
    assert result['parties'][0]['role']=='supplier'
    assert result['parties'][0]['country_code']=='BR'
    assert result['origin_country']=='CN'

def test_company_country_unknown_is_not_filled_from_reporter():
    p=deepcopy(row()['parties']);p[0]['country_code']=None
    assert mod('trade.model').normalize_observation(row(parties=p))['parties'][0]['country_code'] is None

def test_same_name_does_not_merge_source_entities():
    p=row()['parties'][0]
    identity=mod('identity.entities')
    assert identity.company_key(p,'one')!=identity.company_key(p,'two')

def test_registry_identity_can_link_across_sources():
    p=row()['parties'][0];p.update(registry_namespace='CNPJ',registry_identifier='12345678000199')
    identity=mod('identity.entities')
    assert identity.company_key(p,'one')==identity.company_key(p,'two')

def test_different_registry_jurisdictions_remain_separate():
    p=row()['parties'][0];p.update(registry_namespace='REGISTER',registry_identifier='123')
    q=deepcopy(p);q['country_code']='DE'
    assert mod('identity.entities').company_key(p,'one')!=mod('identity.entities').company_key(q,'one')

def test_presence_cannot_claim_money():
    with pytest.raises(ValueError):mod('trade.model').normalize_observation(row(record_kind='trader_presence'))

def test_quantity_needs_unit():
    with pytest.raises(ValueError):mod('trade.model').normalize_observation(row(quantity='5',quantity_unit=None))

def test_same_role_twice_rejected():
    p=row()['parties']
    with pytest.raises(ValueError):mod('trade.model').normalize_observation(row(parties=p+p))

def test_naive_retrieval_time_rejected():
    with pytest.raises(ValueError):mod('trade.model').normalize_observation(row(retrieved_at='2026-09-12T00:00:00'))

def test_estimated_amount_is_explicit():
    result=mod('trade.model').normalize_observation(row(value_origin='estimated'))
    assert result['value_origin']=='estimated'
