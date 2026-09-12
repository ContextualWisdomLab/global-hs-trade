from __future__ import annotations
import hashlib
import unicodedata
from typing import Any


def clean_text(value: Any, field: str, maximum: int = 1024) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{field}: nonempty text is required')
    result = ' '.join(unicodedata.normalize('NFKC', value).split())
    if len(result) > maximum or any(ord(c) < 32 for c in result):
        raise ValueError(f'{field}: invalid text length or control character')
    return result


def company_key(party: dict[str, Any], source_identifier: str) -> str:
    registration = party.get('registry_identifier')
    namespace = party.get('registry_namespace')
    if registration or namespace:
        if not (registration and namespace and party.get('country_code')):
            raise ValueError('registry identity requires namespace, identifier and registration country')
        material = ['registry', clean_text(namespace, 'registry_namespace'),
                    party['country_code'], clean_text(registration, 'registry_identifier')]
    else:
        # A name is evidence about identity, not an identity key.
        material = ['source', source_identifier,
                    clean_text(party.get('external_identifier'), 'external_identifier')]
    payload = '\x1f'.join(material).encode('utf-8')
    return 'company_' + hashlib.sha256(payload).hexdigest()[:32]
