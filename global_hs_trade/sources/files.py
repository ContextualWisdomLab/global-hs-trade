from __future__ import annotations
import csv
import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Iterator
from ..trade.model import utc_timestamp

MAX_FILE_BYTES=128*1024*1024


def read_json(path: str | Path) -> Any:
    path=Path(path)
    if path.stat().st_size>MAX_FILE_BYTES:raise ValueError('input file is larger than the 128 MiB local import limit; split it into explicit batches')
    return json.loads(path.read_text(encoding='utf-8-sig'),parse_float=Decimal)


def read_jsonl(path: str | Path) -> list[dict[str,Any]]:
    path=Path(path)
    if path.stat().st_size>MAX_FILE_BYTES:raise ValueError('input file exceeds 128 MiB; split into batches')
    result=[]
    with path.open(encoding='utf-8-sig') as handle:
        for number,line in enumerate(handle,1):
            if not line.strip():continue
            try:parsed=json.loads(line,parse_float=Decimal)
            except json.JSONDecodeError as exc:raise ValueError(f'invalid JSON at line {number}') from exc
            if not isinstance(parsed,dict):raise ValueError(f'line {number} must be an object')
            result.append(parsed)
    return result


def map_csv_rows(rows: Iterable[dict[str,str]],mapping: dict[str,Any]) -> Iterator[dict[str,Any]]:
    for number,raw in enumerate(rows,1):
        item=dict(mapping.get('constants',{}))
        item['source_identifier']=mapping['source_identifier']
        for target,source in mapping.get('fields',{}).items():
            if source not in raw:raise ValueError(f'CSV row {number}: mapped column {source!r} is absent')
            item[target]=raw[source] if raw[source]!='' else None
        item['parties']=[]
        for role,fields in mapping.get('parties',{}).items():
            party={'role':role}
            for target,source in fields.items():
                if source not in raw:raise ValueError(f'CSV row {number}: party column {source!r} is absent')
                party[target]=raw[source] if raw[source]!='' else None
            if any(v is not None for k,v in party.items() if k!='role'):
                item['parties'].append(party)
        if isinstance(item.get('source_version'),str):
            if not item['source_version'].isdigit():raise ValueError('source_version CSV field must be an integer')
            item['source_version']=int(item['source_version'])
        item.setdefault('retrieved_at',utc_timestamp())
        if mapping.get('document_key'):
            keymap=mapping['document_key']
            key={'verified':keymap.get('verified',False)}
            for target in ['namespace','identifier','line_identifier']:
                column=keymap[target]
                if column not in raw:raise ValueError(f'CSV document key column {column!r} is absent')
                key[target]=raw[column]
            item['document_key']=key
        yield item


def load_csv(path: str | Path,mapping: dict[str,Any]) -> list[dict[str,Any]]:
    path=Path(path)
    if path.stat().st_size>MAX_FILE_BYTES:raise ValueError('CSV exceeds the 128 MiB import limit')
    delimiter=mapping.get('delimiter',',')
    if not isinstance(delimiter,str) or len(delimiter)!=1:raise ValueError('CSV delimiter must be a single character')
    with path.open(encoding='utf-8-sig',newline='') as handle:
        return list(map_csv_rows(csv.DictReader(handle,delimiter=delimiter),mapping))
