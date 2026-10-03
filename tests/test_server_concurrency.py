"""Concurrency contract for the local read-only API."""

from __future__ import annotations

from http.server import ThreadingHTTPServer

from .helpers import mod, source


def test_read_only_api_uses_daemon_request_threads(tmp_path):
    """A stalled reader must not serialize every buyer-facing read endpoint."""
    database = tmp_path / "concurrency.sqlite"
    with mod("storage").Ledger(database) as ledger:
        ledger.register_source(source())

    server = mod("server").make_server(database, 0)
    try:
        assert isinstance(server, ThreadingHTTPServer)
        assert server.daemon_threads is True
    finally:
        server.server_close()
