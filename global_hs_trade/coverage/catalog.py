from __future__ import annotations
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

@lru_cache(maxsize=1)
def countries() -> dict[str, dict[str, str]]:
    return json.loads(Path(__file__).with_name('countries.json').read_text(encoding='utf-8'))


def country_code(value: Any, allow_world: bool = False, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise ValueError('country code must be a string')
    value = value.strip().upper()
    if allow_world and value in {'WORLD', 'WLD', 'W00', '0', '000'}:
        return 'WORLD'
    if value in countries():
        return value
    for code, metadata in countries().items():
        if value == metadata['alpha3']:
            return code
    raise ValueError(f'unsupported or unknown country code: {value!r}')


def coverage_for(country: str, flow: str, measure: str = 'value') -> dict[str, Any]:
    country = country_code(country)
    if flow not in {'M', 'X'} or measure not in {'value', 'presence', 'weight'}:
        raise ValueError('flow must be M/X and measure must be value/presence/weight')
    routes: list[dict[str, Any]] = [
        {'source_identifier':'un-comtrade','kind':'national_aggregate',
         'implementation':'preview_adapter_implemented','has_company_value':False,
         'availability':'reporter/period/HS must be checked; preview is not exhaustive'},
        {'source_identifier':'licensed-normalized-feed','kind':'company_transaction',
         'implementation':'csv_jsonl_import_implemented','has_company_value':None,
         'availability':'requires a supplied dataset and source-specific usage rights'},
        {'source_identifier':'counterparty-mirror','kind':'company_transaction',
         'implementation':'same_normalized_contract','has_company_value':None,
         'availability':'conditional on counterpart country publishing the relevant party and field'},
    ]
    if country == 'GB':
        routes.insert(0,{'source_identifier':'hmrc-traders','kind':'company_presence',
           'implementation':'public_api_adapter_implemented','has_company_value':False,
           'availability':'query pagination supported; legal domicile is not inferred'})
    return {'country_code':country,'country_name':countries()[country]['name'],
       'recorded_flow':flow,'requested_measure':measure,
       'company_values_live_connected':False,'routes':routes,
       'scope_note':'A country in this catalog is not a claim of connected company-level coverage.'}


def builtin_sources() -> list[dict[str, Any]]:
    definitions = [
      ('hmrc-traders','HMRC public trader/commodity/month observations','real',
       'https://www.uktradeinfo.com/api-documentation','Public API; review HMRC reuse terms for the intended distribution.'),
      ('un-comtrade','UN Comtrade national aggregate preview','real',
       'https://uncomtrade.org/docs/un-comtrade-api/','UN Comtrade use/re-dissemination policy applies; company data is not supplied.'),
      ('public-factual-excerpts','Small manually transcribed public factual observations','real',
       None,'Source-linked facts only. Not a licensed vendor database; no bulk-redistribution grant.'),
      ('wits-factual-excerpts','Small public WITS national aggregate fact sample','real',
       'https://wits.worldbank.org/','Source-linked facts; not a complete global extraction.'),
      ('demo-synthetic','Clearly synthetic regression/demo transactions','synthetic',
       None,'Generated fictitious firms and transactions solely for software testing.'),
    ]
    return [{'source_identifier':identifier,'name':name,'dataset_kind':kind,'documentation_url':url,
      'rights_basis':rights,'rights':{'internal_analysis':True,'export_aggregates':True,
      'redistribute_rows':kind=='synthetic'}} for identifier,name,kind,url,rights in definitions]
