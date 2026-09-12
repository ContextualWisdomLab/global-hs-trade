from __future__ import annotations
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from .storage import Ledger
from .application import query_stats
from .coverage.catalog import coverage_for
from .coverage.inventory import dataset_status

QUERY_FIELDS={'hs6','reporter_country','company_country','role','company','start','end',
              'recorded_flow','source_identifier','dataset_kind'}


def valid_host(host: str,port: int) -> bool:
    return host in {f'127.0.0.1:{port}',f'localhost:{port}'}


def dispatch(ledger: Ledger,path: str,parameters: dict[str,str]) -> tuple[int,dict]:
    try:
        if any(len(value)>1024 for value in parameters.values()):raise ValueError('parameter too long')
        if path=='/health' and not parameters:
            return 200,{'status':'ok','mode':'local_read_only','database_open':True,'upstream_freshness_verified':False}
        if path=='/v1/dataset-status' and not parameters:return 200,dataset_status(ledger)
        if path=='/v1/trade-stats':
            if set(parameters)-QUERY_FIELDS:raise ValueError('unknown query parameter')
            result=query_stats(ledger,**parameters)
            count=len(result['statistics'])
            result['statistics']=result['statistics'][:1000]
            result['result_limit']=1000;result['matching_groups']=count;result['truncated']=count>1000
            return 200,result
        if path=='/v1/coverage':
            if set(parameters)-{'country','flow','measure'}:raise ValueError('unknown coverage parameter')
            return 200,coverage_for(parameters['country'],parameters['flow'],parameters.get('measure','value'))
        if path=='/v1/sources' and not parameters:return 200,{'sources':ledger.sources()}
        return 404,{'status':'not_found'}
    except (ValueError,KeyError,TypeError,PermissionError) as exc:
        return 400,{'status':'invalid_request','message':str(exc)}


def make_server(path: str | Path,port: int=8765) -> HTTPServer:
    if not isinstance(port,int) or not 0<=port<=65535:raise ValueError('invalid port')
    path=Path(path)
    if not path.is_file():raise ValueError('initialize the database before serving')
    class Handler(BaseHTTPRequestHandler):
        server_version='GlobalHSTrade/0.2'
        sys_version=''
        def send_json(self,status,body):
            encoded=json.dumps(body,ensure_ascii=False,allow_nan=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Content-Length',str(len(encoded)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'none'; frame-ancestors 'none'")
            self.end_headers();self.wfile.write(encoded)
        def do_GET(self):
            if not valid_host(self.headers.get('Host',''),self.server.server_port):
                self.send_json(403,{'status':'forbidden_host'});return
            if self.headers.get('Origin') or self.headers.get('Sec-Fetch-Site')=='cross-site':
                self.send_json(403,{'status':'cross_origin_not_supported'});return
            if len(self.path)>8192:
                self.send_json(414,{'status':'uri_too_long'});return
            try:
                parsed=urlsplit(self.path)
                if parsed.scheme or parsed.netloc:raise ValueError('absolute-form targets are not accepted')
                values=parse_qs(parsed.query,keep_blank_values=True,max_num_fields=20,strict_parsing=True)
                if any(len(items)!=1 for items in values.values()):raise ValueError('duplicate parameters are not accepted')
                with Ledger(path) as ledger:
                    status,body=dispatch(ledger,parsed.path,{key:items[0] for key,items in values.items()})
                self.send_json(status,body)
            except (ValueError,UnicodeError) as exc:self.send_json(400,{'status':'invalid_request','message':str(exc)})
            except Exception:self.send_json(500,{'status':'internal_error','message':'Inspect the local database with the audit command.'})
        def do_POST(self):self.send_json(405,{'status':'read_only'})
        do_PUT=do_POST;do_DELETE=do_POST;do_PATCH=do_POST;do_OPTIONS=do_POST
        def log_message(self,*args):pass
    return HTTPServer(('127.0.0.1',port),Handler)


def serve(path: str | Path,port: int=8765) -> None:
    with make_server(path,port) as server:
        print(f'Local read-only API: http://127.0.0.1:{server.server_port}; Ctrl+C stops it.',flush=True)
        try:server.serve_forever(poll_interval=0.25)
        except KeyboardInterrupt:pass
