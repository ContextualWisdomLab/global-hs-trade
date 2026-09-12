from __future__ import annotations
import json
import time
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from typing import Any, Callable, Iterator

ALLOWED_HOSTS={'api.uktradeinfo.com','comtradeapi.un.org'}
MAX_RESPONSE_BYTES=16*1024*1024


def validate_url(url: str, allowed_hosts: set[str] | None=None) -> str:
    if not isinstance(url,str) or len(url)>16000 or any(ord(c)<32 for c in url):
        raise ValueError('invalid request URL')
    allowed_hosts=allowed_hosts or ALLOWED_HOSTS
    parsed=urlsplit(url)
    try:
        port=parsed.port
    except ValueError as exc:
        raise ValueError('invalid URL port') from exc
    if parsed.scheme!='https' or parsed.hostname not in allowed_hosts or port not in {None,443} or parsed.username or parsed.password or parsed.fragment:
        raise ValueError('only HTTPS requests to the exact approved source host are allowed')
    return url


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        raise ValueError('HTTP redirects are disabled; review source endpoint changes explicitly')


class HttpClient:
    def __init__(self,timeout: float=20.0,minimum_interval: float=1.1,retries: int=2):
        self.timeout=timeout
        self.minimum_interval=minimum_interval
        self.retries=retries
        self.last_request=0.0
        self.opener=build_opener(NoRedirect())

    def get(self,url: str) -> dict[str,Any]:
        validate_url(url)
        for attempt in range(self.retries+1):
            wait=self.minimum_interval-(time.monotonic()-self.last_request)
            if wait>0:time.sleep(wait)
            self.last_request=time.monotonic()
            request=Request(url,headers={'Accept':'application/json','User-Agent':'GlobalHSTrade/0.2 (+source-qualified research client)'})
            try:
                with self.opener.open(request,timeout=self.timeout) as response:
                    body=response.read(MAX_RESPONSE_BYTES+1)
                    if len(body)>MAX_RESPONSE_BYTES:
                        raise ValueError('response exceeds the 16 MiB safety limit; narrow the source query')
                    mime=response.headers.get_content_type()
                    if mime not in {'application/json','text/json'}:
                        raise ValueError('unexpected response content type; source schema or access may have changed')
                parsed=json.loads(body.decode('utf-8-sig'),parse_float=Decimal)
                if not isinstance(parsed,dict) or 'error' in parsed:
                    raise ValueError('source returned an error or a non-object response')
                return parsed
            except HTTPError as exc:
                if exc.code in {429,502,503,504} and attempt<self.retries:
                    hint=exc.headers.get('Retry-After','') if exc.headers else ''
                    delay=min(60,max(1,int(hint))) if hint.isdigit() else min(60,2**(attempt+1))
                    time.sleep(delay)
                    continue
                raise ConnectionError(f'{urlsplit(url).hostname}: HTTP {exc.code}; data was not treated as zero') from exc
            except (URLError,TimeoutError,OSError) as exc:
                raise ConnectionError(f'{urlsplit(url).hostname}: network/DNS/TLS failure; no successful data receipt') from exc
        raise ConnectionError('source request failed')


def iter_pages(url: str,get: Callable[[str],dict[str,Any]],max_pages: int=3) -> Iterator[tuple[str,dict[str,Any],str]]:
    if not isinstance(max_pages,int) or not 1<=max_pages<=10000:
        raise ValueError('max_pages must be between 1 and 10000')
    host=urlsplit(validate_url(url)).hostname
    seen=set()
    for page in range(max_pages):
        validate_url(url,{host})
        if url in seen:raise ValueError('pagination cycle detected')
        seen.add(url)
        payload=get(url)
        if not isinstance(payload,dict) or not isinstance(payload.get('value'),list):
            raise ValueError('OData response must contain a value array')
        next_url=payload.get('@odata.nextLink')
        if next_url:
            if not isinstance(next_url,str):raise ValueError('invalid nextLink type')
            next_url=validate_url(urljoin(url,next_url),{host})
            if next_url in seen:raise ValueError('pagination cycle detected')
        status='query_pages_exhausted' if not next_url else ('page_limit_reached' if page+1==max_pages else 'more_pages')
        yield url,payload,status
        if not next_url or status=='page_limit_reached':return
        url=next_url
