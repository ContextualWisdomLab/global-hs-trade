from __future__ import annotations
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable
from .trade.model import normalize_observation, utc_timestamp, hs_code
from .trade.statistics import aggregate, reconcile_records


def canonical(value: Any) -> str:
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))


class Ledger:
    def __init__(self,path: str | Path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.connection=sqlite3.connect(self.path,timeout=3)
        self.connection.row_factory=sqlite3.Row
        self.connection.execute('PRAGMA foreign_keys=ON')
        self.connection.execute('PRAGMA journal_mode=WAL')
        self.connection.execute('PRAGMA busy_timeout=3000')
        self.connection.executescript('''
          CREATE TABLE IF NOT EXISTS sources(source_identifier TEXT PRIMARY KEY, configuration TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS observations(
            source_identifier TEXT NOT NULL REFERENCES sources(source_identifier),
            source_record_identifier TEXT NOT NULL,source_version INTEGER NOT NULL,
            hs6 TEXT NOT NULL,period TEXT NOT NULL,reporter_country TEXT NOT NULL,
            recorded_flow TEXT NOT NULL,event_status TEXT NOT NULL,content_hash TEXT NOT NULL,
            payload TEXT NOT NULL,PRIMARY KEY(source_identifier,source_record_identifier,source_version));
          CREATE INDEX IF NOT EXISTS observation_slice ON observations(hs6,period,reporter_country,recorded_flow,source_identifier);
          CREATE TABLE IF NOT EXISTS baselines(baseline_key TEXT PRIMARY KEY,source_identifier TEXT NOT NULL REFERENCES sources(source_identifier),
            hs6 TEXT NOT NULL,period TEXT NOT NULL,payload TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS issues(issue_identifier INTEGER PRIMARY KEY,created_at TEXT NOT NULL,
            source_identifier TEXT,source_record_identifier TEXT,error TEXT NOT NULL,payload_hash TEXT);
          CREATE TABLE IF NOT EXISTS runs(run_identifier INTEGER PRIMARY KEY,created_at TEXT NOT NULL,receipt TEXT NOT NULL);
        ''')

    def close(self) -> None:
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self,*args):
        self.close()

    def register_source(self,specification: dict[str,Any]) -> None:
        identifier=specification.get('source_identifier')
        if not isinstance(identifier,str) or not identifier or len(identifier)>256:
            raise ValueError('source_identifier is required')
        if specification.get('dataset_kind') not in {'real','synthetic'}:
            raise ValueError('source dataset_kind must be real or synthetic')
        rights=specification.get('rights',{})
        if any(not isinstance(rights.get(k),bool) for k in ['internal_analysis','export_aggregates','redistribute_rows']):
            raise ValueError('each rights flag must explicitly be true or false')
        if not specification.get('rights_basis'):
            raise ValueError('a source-specific rights basis/attestation is required')
        existing=self.source(identifier,required=False)
        if existing is not None and canonical(existing)!=canonical(specification):
            raise ValueError('source already registered with a different policy; do not silently alter entitlements')
        with self.connection:
            self.connection.execute('INSERT OR IGNORE INTO sources VALUES (?,?)',(identifier,canonical(specification)))

    def source(self,identifier: str,required: bool=True) -> dict[str,Any] | None:
        found=self.connection.execute('SELECT configuration FROM sources WHERE source_identifier=?',(identifier,)).fetchone()
        if found is None:
            if required:raise ValueError('source is not registered: '+str(identifier))
            return None
        return json.loads(found['configuration'])

    def sources(self) -> list[dict[str,Any]]:
        return [json.loads(r[0]) for r in self.connection.execute('SELECT configuration FROM sources ORDER BY source_identifier')]

    def _right(self,identifier: str,right: str) -> dict[str,Any]:
        source=self.source(identifier)
        if not source['rights'].get(right,False):
            raise PermissionError(f'{identifier}: {right} is not permitted by registered policy')
        return source

    def ingest(self,records: Iterable[dict[str,Any]]) -> dict[str,Any]:
        outcome={'inserted':0,'replayed':0,'rejected':0,'errors':[]}
        batch=[]
        for index,raw in enumerate(records,1):
            batch.append((index,raw))
            if len(batch)>=500:
                self._ingest_batch(batch,outcome);batch=[]
        if batch:self._ingest_batch(batch,outcome)
        return outcome

    def _ingest_batch(self,batch: list,outcome: dict[str,Any]) -> None:
        prepared=[];failures=[]
        # Validation and canonical serialization finish before a write transaction opens.
        for index,raw in batch:
            try:
                value=normalize_observation(raw)
                source=self._right(value['source_identifier'],'internal_analysis')
                value['dataset_kind']=source['dataset_kind']
                digest_value={k:v for k,v in value.items() if k!='retrieved_at'}
                digest=hashlib.sha256(canonical(digest_value).encode()).hexdigest()
                prepared.append((index,value,digest))
            except (ValueError,PermissionError,TypeError,KeyError) as exc:
                failures.append((index,raw,str(exc)))
        with self.connection:
            for index,value,digest in prepared:
                params=(value['source_identifier'],value['source_record_identifier'],value['source_version'])
                old=self.connection.execute('SELECT content_hash FROM observations WHERE source_identifier=? AND source_record_identifier=? AND source_version=?',params).fetchone()
                if old:
                    if old['content_hash']==digest:
                        outcome['replayed']+=1
                    else:
                        failures.append((index,value,'same source key/version has conflicting content; supply an explicit corrected version'))
                    continue
                self.connection.execute('INSERT INTO observations VALUES (?,?,?,?,?,?,?,?,?,?)',params+
                 (value['hs6'],value['period'],value['reporter_country'],value['recorded_flow'],value['event_status'],digest,canonical(value)))
                outcome['inserted']+=1
            for index,raw,error in failures:
                source=raw.get('source_identifier') if isinstance(raw,dict) else None
                record=raw.get('source_record_identifier') if isinstance(raw,dict) else None
                digest=hashlib.sha256(repr(raw).encode()).hexdigest()
                self.connection.execute('INSERT INTO issues(created_at,source_identifier,source_record_identifier,error,payload_hash) VALUES (?,?,?,?,?)',
                  (utc_timestamp(),source,record,error,digest))
                outcome['errors'].append({'input_row':index,'source_record_identifier':record,'error':error})
                outcome['rejected']+=1

    def observations(self,source_identifier: str | None=None,hs6: str | None=None,reporter_country: str | None=None,
                     start: str | None=None,end: str | None=None,recorded_flow: str | None=None,dataset_kind: str | None=None) -> list[dict[str,Any]]:
        rows=self.connection.execute(
            '''SELECT o.payload FROM observations o
               WHERE o.source_version=(
                   SELECT MAX(n.source_version) FROM observations n
                   WHERE n.source_identifier=o.source_identifier
                     AND n.source_record_identifier=o.source_record_identifier
               )
                 AND o.event_status='active'
                 AND (? IS NULL OR o.source_identifier=?)
                 AND (? IS NULL OR o.hs6=?)
                 AND (? IS NULL OR o.reporter_country=?)
                 AND (? IS NULL OR o.recorded_flow=?)
                 AND (? IS NULL OR o.period>=?)
                 AND (? IS NULL OR o.period<=?)
               ORDER BY o.source_identifier,o.source_record_identifier''',
            (source_identifier,source_identifier,hs6,hs6,reporter_country,reporter_country,
             recorded_flow,recorded_flow,start,start,end,end))
        result=[]
        for row in rows:
            record=json.loads(row['payload'])
            if dataset_kind and record['dataset_kind']!=dataset_kind:continue
            self._right(record['source_identifier'],'internal_analysis')
            result.append(record)
        return result

    def stats(self,role: str | None=None,company: str | None=None,company_country: str | None=None,**filters) -> list[dict[str,Any]]:
        return aggregate(self.observations(**filters),role=role,company=company,company_country=company_country)

    def reconcile(self) -> list[dict[str,Any]]:
        return reconcile_records(self.observations())

    def issues(self) -> list[dict[str,Any]]:
        return [dict(row) for row in self.connection.execute('SELECT * FROM issues ORDER BY issue_identifier')]

    def record_run(self,receipt: dict[str,Any]) -> None:
        with self.connection:
            self.connection.execute('INSERT INTO runs(created_at,receipt) VALUES (?,?)',(utc_timestamp(),canonical(receipt)))

    def runs(self) -> list[dict[str,Any]]:
        return [dict(row)|{'receipt':json.loads(row['receipt'])} for row in self.connection.execute('SELECT * FROM runs ORDER BY run_identifier')]

    def save_baselines(self,records: Iterable[dict[str,Any]]) -> int:
        from .sources.comtrade import validate_baseline
        prepared=[]
        for record in records:
            record=validate_baseline(record)
            source=self._right(record['source_identifier'],'internal_analysis')
            record['dataset_kind']=source['dataset_kind']
            keyfields={k:record.get(k) for k in ['source_identifier','reporter_country','partner_country','period','recorded_flow','hs6','hs_revision','value_currency','value_basis','customs_code','transport_mode']}
            key=hashlib.sha256(canonical(keyfields).encode()).hexdigest()
            prepared.append((key,record['source_identifier'],record['hs6'],record['period'],canonical(record)))
        with self.connection:
            self.connection.executemany('INSERT INTO baselines VALUES (?,?,?,?,?) ON CONFLICT(baseline_key) DO UPDATE SET payload=excluded.payload',prepared)
        return len(prepared)

    def baselines(self,hs6: str | None=None) -> list[dict[str,Any]]:
        if hs6 is None:
            rows=self.connection.execute('SELECT payload FROM baselines')
        else:
            rows=self.connection.execute('SELECT payload FROM baselines WHERE hs6=?',(hs6,))
        records=[json.loads(r[0]) for r in rows]
        for record in records:self._right(record['source_identifier'],'internal_analysis')
        return records

    def export_rows(self,source_identifier: str,path: str | Path) -> None:
        self._right(source_identifier,'redistribute_rows')
        records=self.observations(source_identifier=source_identifier)
        Path(path).write_text(''.join(canonical(r)+'\n' for r in records),encoding='utf-8')

    def export_stats(self,source_identifier: str,path: str | Path) -> None:
        self._right(source_identifier,'export_aggregates')
        payload={'scope':'source-qualified observed statics; not complete company trade',
                 'statistics':self.stats(source_identifier=source_identifier)}
        Path(path).write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
