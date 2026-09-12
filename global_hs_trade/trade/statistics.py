from __future__ import annotations
import json
from collections import defaultdict
from decimal import Decimal, localcontext
from typing import Any, Iterable

GROUP_FIELDS=['source_identifier','dataset_kind','reporter_country','recorded_flow','period',
  'record_kind','date_basis','hs6','hs_revision','hs_code_origin','partner_country','partner_basis',
  'value_currency','value_basis','value_origin','quantity_unit']
PARTY_FIELDS=['company_identifier','country_code','identity_basis','role']


def aggregate(records: Iterable[dict[str,Any]], role: str | None=None, company: str | None=None, company_country: str | None=None) -> list[dict[str,Any]]:
    records=list(records)
    matched_identifiers=None
    if company:
        matched_identifiers={p['company_identifier'] for r in records for p in r['parties']
            if company.casefold() in p['legal_name'].casefold() or company==p['company_identifier']}
    groups: dict[tuple,dict[str,Any]]={}
    for record in records:
        for party in record['parties']:
            if company_country and party['country_code']!=company_country:
                continue
            if role and party['role']!=role:
                continue
            if matched_identifiers is not None and party['company_identifier'] not in matched_identifiers:
                continue
            key=tuple(record.get(k) for k in GROUP_FIELDS)+tuple(party.get(k) for k in PARTY_FIELDS)
            if key not in groups:
                item={k:record.get(k) for k in GROUP_FIELDS}
                item.update(company_identifier=party['company_identifier'],company_name=party['legal_name'],
                  company_country=party['country_code'],identity_basis=party['identity_basis'],role=party['role'],
                  observed_company_names=[],observation_count=0,customs_lines=0,bill_of_lading_observations=0,presence_observations=0,
                  observed_value=None,net_weight_kg=None,gross_weight_kg=None,quantity=None,
                  missing_value_observations=0,evidence_sample=[],coverage='partial_or_unknown')
                groups[key]=item
            item=groups[key]
            if party['legal_name'] not in item['observed_company_names']:
                item['observed_company_names'].append(party['legal_name'])
                item['observed_company_names'].sort()
                item['company_name']=item['observed_company_names'][0]
            item['observation_count']+=1
            counter={'customs_line':'customs_lines','bill_of_lading':'bill_of_lading_observations','trader_presence':'presence_observations'}[record['record_kind']]
            item[counter]+=1
            item['missing_value_observations']+=record['value'] is None
            # Missing values stay absent; no summation across currencies, sources or valuation bases.
            with localcontext() as context:
                context.prec=60
                for field,out in [('value','observed_value'),('net_weight_kg','net_weight_kg'),('gross_weight_kg','gross_weight_kg'),('quantity','quantity')]:
                    if record[field] is not None:
                        item[out]=format(Decimal(item[out] or '0')+Decimal(record[field]),'f')
            if len(item['evidence_sample'])<5:
                item['evidence_sample'].append({'source_record_identifier':record['source_record_identifier'],
                    'source_version':record['source_version'],'source_url':record['source_url']})
    return sorted(groups.values(),key=lambda r:json.dumps(r,sort_keys=True,ensure_ascii=False))


def reconcile_records(records: Iterable[dict[str,Any]]) -> list[dict[str,Any]]:
    groups=defaultdict(list)
    for record in records:
        key=record.get('document_key')
        if key and key.get('verified'):
            group=(key['namespace'],key['identifier'],key['line_identifier'],record['reporter_country'],record['recorded_flow'],record['record_kind'])
            groups[group].append(record)
    result=[]
    for key,items in groups.items():
        if len({i['source_identifier'] for i in items})<2:
            continue
        signatures=set()
        for item in items:
            signature={k:item.get(k) for k in ['period','date_basis','hs_code','hs_revision','hs_code_origin',
                'value','value_currency','value_basis','value_origin','net_weight_kg','gross_weight_kg',
                'quantity','quantity_unit','partner_country','partner_basis','origin_country','dispatch_country','destination_country']}
            signature['parties']=sorted((p['role'],p['company_identifier']) for p in item['parties'])
            signatures.add(json.dumps(signature,sort_keys=True))
        result.append({'document_namespace':key[0],'document_identifier':key[1],'line_identifier':key[2],
          'reporter_country':key[3],'recorded_flow':key[4],
          'status':'matching_observations' if len(signatures)==1 else 'conflicting_observations',
          'action':'No automatic cross-source sum or overwrite; choose the contractual authoritative source.',
          'evidence':[{'source_identifier':i['source_identifier'],'source_record_identifier':i['source_record_identifier'],
          'source_version':i['source_version'],'value':i['value']} for i in items]})
    return result
