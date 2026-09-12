from __future__ import annotations
import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Sequence
from .coverage.catalog import builtin_sources, coverage_for
from .sources import files, hmrc, comtrade
from .storage import Ledger
from .application import query_stats, fetch_hmrc, fetch_comtrade
from .collection.captures import import_capture, list_captures, provenance
from .coverage.inventory import dataset_status


def parser() -> argparse.ArgumentParser:
    root=argparse.ArgumentParser(description='Global HS Trade: source-qualified company trade observations, not an all-company census.')
    commands=root.add_subparsers(dest='command',required=True)
    def command(name,help_text):
        p=commands.add_parser(name,help=help_text)
        p.add_argument('--db',default='trade.sqlite',help='Local SQLite database; initialize explicitly first')
        return p
    command('init','Initialize an empty ledger and built-in source policies')
    p=command('ingest','Import normalized JSONL/JSON or explicitly mapped CSV')
    p.add_argument('--file',required=True);p.add_argument('--mapping');p.add_argument('--source-json')
    p=command('ingest-baselines','Import source-qualified national aggregate JSON')
    p.add_argument('--file',required=True)
    p=command('register-source','Register a source policy and rights attestation')
    p.add_argument('--file',required=True)
    p=command('query','Query observed company statistics')
    for name in ['hs6','reporter','company-country','role','company','start','end','source']:
        p.add_argument('--'+name)
    p.add_argument('--flow',choices=['M','X']);p.add_argument('--dataset-kind',choices=['real','synthetic'])
    p=command('baselines','Read national totals separately from company data');p.add_argument('--hs6')
    command('sources','Show registered source policies')
    command('dataset-status','Inspect actual observations, not possible geographic coverage')
    p=command('import-capture','Replay a source-bound integrity-checked local evidence capture')
    p.add_argument('--file',required=True)
    command('captures','List evidence metadata without exposing raw payloads')
    p=command('provenance','Inspect evidence linked to an exact observation version')
    p.add_argument('--source',required=True);p.add_argument('--record',required=True)
    p.add_argument('--version',type=int)
    command('audit','Show import issues, source refresh receipts and verified-document conflicts')
    p=commands.add_parser('coverage',help='Inspect routes; a listed country is not connected coverage')
    p.add_argument('--country',required=True);p.add_argument('--flow',required=True,choices=['M','X'])
    p.add_argument('--measure',default='value',choices=['value','weight','presence'])
    p=command('fetch-hmrc','Fetch public trader/commodity/month presence, not money')
    for name in ['hs6','start','end']:p.add_argument('--'+name,required=True)
    p.add_argument('--flow',required=True,choices=['M','X']);p.add_argument('--max-pages',type=int,default=3)
    p.add_argument('--source-version',type=int,default=1);p.add_argument('--dry-run',action='store_true')
    p.add_argument('--page-size',type=int,default=1000);p.add_argument('--resume',action='store_true')
    p=command('fetch-comtrade','Fetch a non-exhaustive national aggregate preview')
    p.add_argument('--reporter-code',type=int,required=True)
    p.add_argument('--hs6',required=True);p.add_argument('--period',required=True)
    p.add_argument('--flow',required=True,choices=['M','X']);p.add_argument('--dry-run',action='store_true')
    p=command('export','Export a single source under its recorded policy')
    p.add_argument('--source',required=True);p.add_argument('--output',required=True);p.add_argument('--raw',action='store_true')
    p=command('serve','Run the local read-only JSON API on 127.0.0.1')
    p.add_argument('--port',type=int,default=8765)
    return root


def emit(value) -> None:
    print(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False))


def main(argv: Sequence[str] | None=None) -> int:
    args=parser().parse_args(argv)
    try:
        if args.command=='coverage':
            emit(coverage_for(args.country,args.flow,args.measure));return 0
        if getattr(args,'dry_run',False):
            url=hmrc.build_url(args.hs6,args.start,args.end,args.flow,args.page_size) if args.command=='fetch-hmrc' else comtrade.build_url(args.reporter_code,args.hs6,args.period,args.flow)
            emit({'query_url':url,'network_called':False,'database_changed':False});return 0
        path=Path(args.db)
        if args.command!='init' and not path.is_file():
            raise ValueError('database does not exist; run init --db <path> first')
        if args.command=='serve':
            from .server import serve
            serve(path,args.port);return 0
        with Ledger(path) as ledger:
            if args.command=='init':
                for spec in builtin_sources():ledger.register_source(spec)
                emit({'status':'initialized','database':str(path),'connected_company_value_sources':0});return 0
            if args.command=='dataset-status':emit(dataset_status(ledger));return 0
            if args.command=='captures':emit({'captures':list_captures(ledger)});return 0
            if args.command=='provenance':
                emit({'captures':provenance(ledger,args.source,args.record,args.version)});return 0
            if args.command=='import-capture':
                outcome=import_capture(ledger,files.read_json(args.file));emit(outcome)
                return 2 if outcome['rejected'] else 0
            if args.command=='register-source':
                spec=files.read_json(args.file);ledger.register_source(spec)
                emit({'status':'registered','source_identifier':spec['source_identifier']});return 0
            if args.command=='ingest':
                if args.source_json:ledger.register_source(files.read_json(args.source_json))
                if args.mapping:rows=files.load_csv(args.file,files.read_json(args.mapping))
                elif Path(args.file).suffix.lower() in {'.jsonl','.ndjson'}:rows=files.read_jsonl(args.file)
                else:
                    rows=files.read_json(args.file)
                    if not isinstance(rows,list):raise ValueError('JSON input must contain an array of observations')
                outcome=ledger.ingest(rows);emit(outcome)
                return 2 if outcome['rejected'] else 0
            if args.command=='ingest-baselines':
                rows=files.read_json(args.file)
                if not isinstance(rows,list):raise ValueError('baseline JSON must be an array')
                emit({'national_records_saved':ledger.save_baselines(rows),'company_records_added':0});return 0
            if args.command=='query':
                emit(query_stats(ledger,hs6=args.hs6,reporter_country=args.reporter,company_country=args.company_country,
                     role=args.role,company=args.company,start=args.start,end=args.end,recorded_flow=args.flow,
                     source_identifier=args.source,dataset_kind=args.dataset_kind));return 0
            if args.command=='baselines':emit({'record_kind':'national_aggregate','records':ledger.baselines(args.hs6)});return 0
            if args.command=='sources':emit({'sources':ledger.sources()});return 0
            if args.command=='audit':emit({'issues':ledger.issues(),'runs':ledger.runs(),'cross_source_matches':ledger.reconcile()});return 0
            if args.command=='export':
                if args.raw:ledger.export_rows(args.source,args.output)
                else:ledger.export_stats(args.source,args.output)
                emit({'status':'exported','output':args.output,'source_identifier':args.source});return 0
            if args.command=='fetch-hmrc':
                receipt=fetch_hmrc(ledger,args.hs6,args.start,args.end,args.flow,max_pages=args.max_pages,source_version=args.source_version,page_size=args.page_size,resume=args.resume)
            elif args.command=='fetch-comtrade':
                receipt=fetch_comtrade(ledger,args.reporter_code,args.hs6,args.period,args.flow)
            else:raise ValueError('unhandled command')
            emit(receipt)
            return 0 if receipt['status'] in {'query_pages_exhausted','preview_not_exhaustive'} else 2
    except (ValueError,OSError,PermissionError,KeyError,TypeError,sqlite3.Error) as exc:
        print(json.dumps({'status':'error','message':str(exc)},ensure_ascii=False),file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
