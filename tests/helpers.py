import importlib
from copy import deepcopy
import pytest

def mod(name):
    try:
        return importlib.import_module('global_hs_trade.' + name)
    except ModuleNotFoundError:
        pytest.fail('required implementation is absent: ' + name)

def row(**changes):
    result = {
        'source_identifier':'test-source', 'source_record_identifier':'declaration-1-line-1',
        'source_version':1, 'period':'2026-01','reporter_country':'BR','recorded_flow':'X',
        'record_kind':'customs_line','date_basis':'declaration_month',
        'hs_code':'09011100','hs_revision':'HS2022','hs_code_origin':'reported',
        'value':'1234.56','value_currency':'USD','value_basis':'FOB','value_origin':'reported',
        'net_weight_kg':'100','gross_weight_kg':None,'quantity':None,'quantity_unit':None,
        'partner_country':'DE','partner_basis':'destination',
        'origin_country':'BR','dispatch_country':'BR','destination_country':'DE',
        'parties':[{'role':'exporter','legal_name':'SYNTHETIC Coffee Brasil Ltd',
          'country_code':'BR','external_identifier':'br-supplier-1',
          'registry_identifier':None,'registry_namespace':None}],
        'event_status':'active','document_key':None,'source_url':'https://example.org/synthetic/1',
        'retrieved_at':'2026-09-12T00:00:00+00:00',
    }
    result.update(deepcopy(changes))
    return result

def source(identifier='test-source', kind='synthetic', export=True):
    return {'source_identifier':identifier,'name':identifier,'dataset_kind':kind,
      'rights':{'internal_analysis':True,'export_aggregates':export,'redistribute_rows':False},
      'rights_basis':'Synthetic test data only; no real vendor entitlement.'}
