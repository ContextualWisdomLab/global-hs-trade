from __future__ import annotations
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
from typing import Any
from urllib.parse import urlsplit
from ..coverage.catalog import country_code
from ..identity.entities import clean_text, company_key

REVISIONS = {'UNKNOWN','HS1992','HS1996','HS2002','HS2007','HS2012','HS2017','HS2022'}
ROLES = {'importer','exporter','supplier','buyer','shipper','consignee','manufacturer','forwarder'}
KINDS = {'customs_line','bill_of_lading','trader_presence'}


def decimal_text(value: Any, field: str) -> str | None:
    if value is None or value == '':
        return None
    if isinstance(value, (bool, float)) or not isinstance(value, (str, int, Decimal)):
        raise ValueError(f'{field}: pass an exact decimal string, not a float/bool')
    try:
        number = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f'{field}: invalid decimal or unconfigured locale') from exc
    if not number.is_finite() or number < 0 or len(number.as_tuple().digits) > 38 or abs(number.adjusted()) > 38:
        raise ValueError(f'{field}: nonfinite, negative or excessive precision/scale')
    return format(number, 'f')


def month(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', value):
        raise ValueError('period must be YYYY-MM')
    if not 1900 <= int(value[:4]) <= 2100:
        raise ValueError('period year outside supported range')
    return value


def hs_code(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError('HS must be text; numeric values may have lost leading zeroes')
    if not re.fullmatch(r'[0-9.\s]+', value):
        raise ValueError('one HS code is required; lists and descriptions are not codes')
    code = re.sub(r'[.\s]', '', value)
    if not 6 <= len(code) <= 12 or code[:2] in {'00','77'}:
        raise ValueError('HS must have 6 to 12 digits and a valid-format chapter')
    return code


def utc_timestamp(value: Any = None) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat()
    if not isinstance(value, str):
        raise ValueError('retrieved_at must be an ISO8601 timestamp')
    try:
        parsed = datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError as exc:
        raise ValueError('retrieved_at is not an ISO8601 timestamp') from exc
    if parsed.tzinfo is None:
        raise ValueError('retrieved_at must have an explicit timezone')
    return parsed.astimezone(timezone.utc).isoformat()


def normalize_observation(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError('observation must be an object')
    result: dict[str, Any] = {}
    for field in ['source_identifier','source_record_identifier']:
        result[field] = clean_text(data.get(field),field,256)
    version = data.get('source_version',1)
    if isinstance(version,bool) or not isinstance(version,int) or not 1 <= version <= 2**53:
        raise ValueError('source_version must be a positive integer')
    result['source_version'] = version
    result['period'] = month(data.get('period'))
    result['reporter_country'] = country_code(data.get('reporter_country'))
    result['recorded_flow'] = data.get('recorded_flow')
    if result['recorded_flow'] not in {'M','X'}:
        raise ValueError('recorded_flow must be M or X at the reporting customs territory')
    result['record_kind'] = data.get('record_kind')
    if result['record_kind'] not in KINDS:
        raise ValueError('unsupported observation kind')
    result['date_basis'] = clean_text(data.get('date_basis','source_period'),'date_basis',100)
    result['hs_code'] = hs_code(data.get('hs_code'))
    result['hs6'] = result['hs_code'][:6]
    result['hs_revision'] = data.get('hs_revision','UNKNOWN')
    if result['hs_revision'] not in REVISIONS:
        raise ValueError('HS revision must be explicit or UNKNOWN')
    result['hs_code_origin'] = data.get('hs_code_origin','reported')
    if result['hs_code_origin'] not in {'reported','declared','provider_inferred','user_inferred'}:
        raise ValueError('unsupported HS evidence origin')
    for field in ['value','net_weight_kg','gross_weight_kg','quantity']:
        result[field] = decimal_text(data.get(field),field)
    result['value_origin'] = data.get('value_origin','missing' if result['value'] is None else 'reported')
    if result['value_origin'] not in {'reported','estimated','missing'}:
        raise ValueError('unsupported value origin')
    if (result['value'] is None) != (result['value_origin']=='missing'):
        raise ValueError('value_origin must agree with whether a value is present')
    currency=data.get('value_currency')
    if currency is not None and (not isinstance(currency,str) or not re.fullmatch('[A-Z]{3}',currency)):
        raise ValueError('value_currency must be an explicit three-letter code')
    if result['value'] is not None and not currency:
        raise ValueError('a value requires a currency')
    result['value_currency']=currency
    result['value_basis']=data.get('value_basis','UNKNOWN')
    if result['value_basis'] not in {'FOB','CIF','CUSTOMS','UNKNOWN'}:
        raise ValueError('unsupported valuation basis')
    result['quantity_unit']=data.get('quantity_unit') or None
    if (result['quantity'] is None) != (result['quantity_unit'] is None):
        raise ValueError('quantity and unit must be supplied together')
    if result['quantity_unit'] is not None:
        result['quantity_unit']=clean_text(result['quantity_unit'],'quantity_unit',40)
    if result['record_kind']=='trader_presence' and any(result[f] is not None for f in ['value','net_weight_kg','gross_weight_kg','quantity']):
        raise ValueError('a trader presence record cannot carry transaction money or physical quantity')
    for field in ['partner_country','origin_country','dispatch_country','destination_country']:
        result[field]=country_code(data.get(field),optional=True)
    result['partner_basis']=clean_text(data.get('partner_basis','unknown'),'partner_basis',80)
    result['event_status']=data.get('event_status','active')
    if result['event_status'] not in {'active','cancelled'}:
        raise ValueError('event_status must be active or cancelled')
    parties=data.get('parties')
    if not isinstance(parties,list) or not parties:
        raise ValueError('at least one explicitly identified party is required')
    result['parties']=[]
    seen_roles=set()
    for party in parties:
        if not isinstance(party,dict) or party.get('role') not in ROLES:
            raise ValueError('unsupported party role')
        role=party['role']
        if role in seen_roles:
            raise ValueError('duplicate party role; split ambiguous assertions instead of guessing')
        seen_roles.add(role)
        normalized={'role':role,'legal_name':clean_text(party.get('legal_name'),'legal_name'),
          'country_code':country_code(party.get('country_code'),optional=True),
          'external_identifier':party.get('external_identifier'),
          'registry_namespace':party.get('registry_namespace'),
          'registry_identifier':party.get('registry_identifier')}
        normalized['company_identifier']=company_key(normalized,result['source_identifier'])
        normalized['identity_basis']='registry_identifier_supplied' if normalized['registry_identifier'] else 'source_scoped_identifier'
        result['parties'].append(normalized)
    result['parties'].sort(key=lambda p:p['role'])
    key=data.get('document_key')
    if key is not None:
        if not isinstance(key,dict) or not isinstance(key.get('verified'),bool):
            raise ValueError('document key requires an explicit verified boolean')
        key={field:clean_text(key.get(field),'document_key.'+field,256) for field in ['namespace','identifier','line_identifier']} | {'verified':key['verified']}
    result['document_key']=key
    url=data.get('source_url')
    if url is not None:
        url=clean_text(url,'source_url',4096)
        parsed=urlsplit(url)
        try:
            parsed.port
        except ValueError as exc:
            raise ValueError('source_url has an invalid port') from exc
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username
                or parsed.password or parsed.fragment):
            raise ValueError('source_url must be an HTTPS URL without credentials or fragment')
    result['source_url']=url
    result['retrieved_at']=utc_timestamp(data.get('retrieved_at'))
    return result
