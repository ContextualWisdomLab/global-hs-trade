from __future__ import annotations

import hashlib
import json
from typing import Any
from ..storage import Ledger, canonical
from ..trade.model import utc_timestamp


def ensure_schema(ledger: Ledger) -> None:
    ledger.connection.execute('''CREATE TABLE IF NOT EXISTS collection_checkpoints(
        checkpoint_identifier TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL)''')


def identifier(query_url: str, source_version: int) -> str:
    return hashlib.sha256(canonical({'query_url':query_url,'source_version':source_version}).encode()).hexdigest()


def load(ledger: Ledger, key: str) -> dict[str, Any] | None:
    ensure_schema(ledger)
    row=ledger.connection.execute('SELECT revision,payload FROM collection_checkpoints WHERE checkpoint_identifier=?',(key,)).fetchone()
    if row is None:
        return None
    return {'revision':row['revision'],'state':json.loads(row['payload'])}


def save(ledger: Ledger, key: str, state: dict[str,Any], expected_revision: int | None) -> int:
    encoded=canonical(dict(state,updated_at=utc_timestamp()))
    ensure_schema(ledger)
    revision=1 if expected_revision is None else expected_revision+1
    with ledger.connection:
        if expected_revision is None:
            result=ledger.connection.execute('INSERT OR IGNORE INTO collection_checkpoints VALUES (?,?,?)',(key,revision,encoded))
        else:
            result=ledger.connection.execute('UPDATE collection_checkpoints SET revision=?,payload=? WHERE checkpoint_identifier=? AND revision=?',
                (revision,encoded,key,expected_revision))
        if result.rowcount != 1:
            raise ValueError('checkpoint changed concurrently; stop this collector and inspect the active writer')
    return revision
