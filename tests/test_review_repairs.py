"""Regression coverage for the first current-head review of PR #2."""

from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from threading import Thread
from urllib.request import urlopen
from urllib.parse import parse_qs, urlsplit

import pytest

from .helpers import mod, row, source
from .test_captures_v020 import envelope


def _ledger(tmp_path):
    ledger = mod("storage").Ledger(tmp_path / "review-repairs.sqlite")
    for specification in mod("coverage.catalog").builtin_sources():
        ledger.register_source(specification)
    ledger.register_source(source())
    return ledger


def _comtrade_payload(**changes):
    record = {
        "period": 2024,
        "reporterCode": 76,
        "reporterISO": "BRA",
        "partnerCode": 0,
        "partnerISO": "W00",
        "flowCode": "X",
        "cmdCode": "090111",
        "classificationCode": "H6",
        "primaryValue": "1",
        "fobvalue": "1",
        "netWgt": "1",
    }
    record.update(changes)
    return {"data": [record]}


def test_comtrade_normalizes_hs6_and_rejects_response_scope_mismatch(tmp_path):
    ledger = _ledger(tmp_path)

    class Client:
        def __init__(self, payload):
            self.payload = payload
            self.url = None

        def get(self, url):
            self.url = url
            return self.payload

    client = Client(_comtrade_payload())
    receipt = mod("application").fetch_comtrade(
        ledger, 76, "0901.11", "2024", "X", client=client
    )
    assert receipt["records_saved"] == 1
    assert parse_qs(urlsplit(client.url).query)["cmdCode"] == ["090111"]

    mismatch = Client(_comtrade_payload(reporterCode=32))
    rejected = mod("application").fetch_comtrade(
        ledger, 76, "090111", "2024", "X", client=mismatch
    )
    assert rejected["status"] == "failed"
    assert "outside the requested" in rejected["error"]
    assert len(ledger.baselines()) == 1
    ledger.close()


def test_hmrc_helpers_normalize_dotted_hs6():
    hmrc = mod("sources.hmrc")
    url = hmrc.build_url("0901.11", "2026-01", "2026-01", "M")
    assert "090111" in parse_qs(urlsplit(url).query)["$filter"][0]

    payload = {
        "value": [{
            "TraderId": 1,
            "CommodityId": 2,
            "MonthId": 202601,
            "TradeTypeId": 1,
            "Trader": {"CompanyName": "SYNTHETIC TRADER"},
            "Commodity": {"Cn8Code": "09011100", "Hs6Code": "090111"},
        }]
    }
    rows, _, _ = hmrc.validate_page(
        payload, "0901.11", "2026-01", "2026-01", "M", 1, None, url
    )
    assert rows[0]["hs6"] == "090111"


def test_real_builtin_sources_do_not_default_to_aggregate_export():
    sources = mod("coverage.catalog").builtin_sources()
    for specification in sources:
        expected = specification["dataset_kind"] == "synthetic"
        assert specification["rights"]["export_aggregates"] is expected


def test_inventory_counts_same_registry_identity_once_per_source(tmp_path):
    ledger = _ledger(tmp_path)
    ledger.register_source(source("other"))
    first = row()
    first["parties"][0].update(
        registry_namespace="SYNTHETIC", registry_identifier="shared"
    )
    second = deepcopy(first)
    second.update(source_identifier="other", source_record_identifier="other-row")
    ledger.ingest([first, second])
    status = mod("coverage.inventory").dataset_status(ledger)
    assert status["source_scoped_company_identities"] == 2
    ledger.close()


def test_register_source_rejects_non_object_rights_and_post_insert_conflict(tmp_path, monkeypatch):
    ledger = mod("storage").Ledger(tmp_path / "policy.sqlite")
    malformed = source()
    malformed["rights"] = []
    with pytest.raises(ValueError, match="rights"):
        ledger.register_source(malformed)

    submitted = source("race")
    stored = source("race")
    stored["rights"]["export_aggregates"] = False

    class IgnoredInsert:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, *args):
            return None

    monkeypatch.setattr(ledger, "connection", IgnoredInsert())
    monkeypatch.setattr(
        ledger,
        "source",
        lambda identifier, required=True: stored if required else None,
    )
    with pytest.raises(ValueError, match="different policy"):
        ledger.register_source(submitted)


def test_aggregate_export_hides_row_provenance_without_row_right(tmp_path):
    ledger = _ledger(tmp_path)
    ledger.ingest([row()])
    target = tmp_path / "aggregate.json"
    ledger.export_stats("test-source", target)
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["statistics"]
    assert all("evidence_sample" not in item for item in payload["statistics"])
    ledger.close()


def test_capture_import_rolls_back_every_write_when_receipt_fails(tmp_path, monkeypatch):
    ledger = _ledger(tmp_path)
    original = ledger.record_run

    def fail_after_receipt(receipt, **kwargs):
        original(receipt, **kwargs)
        raise RuntimeError("synthetic receipt failure")

    monkeypatch.setattr(ledger, "record_run", fail_after_receipt)
    with pytest.raises(RuntimeError, match="receipt failure"):
        mod("collection.captures").import_capture(ledger, envelope())

    assert ledger.observations() == []
    assert ledger.runs() == []
    assert ledger.connection.execute("SELECT COUNT(*) FROM captures").fetchone()[0] == 0
    ledger.close()


def test_read_only_ledger_does_not_initialize_capture_schema(tmp_path):
    path = tmp_path / "review-repairs.sqlite"
    with _ledger(tmp_path) as ledger:
        assert ledger.path == path

    with mod("storage").Ledger(path, read_only=True) as ledger:
        status = mod("coverage.inventory").dataset_status(ledger)
        assert status["evidence_captures"] == 0

    server = mod("server").make_server(path, 0)
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        with urlopen(
            f"http://127.0.0.1:{server.server_port}/v1/dataset-status", timeout=3
        ) as response:
            assert json.load(response)["evidence_captures"] == 0
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()

    connection = sqlite3.connect(path)
    names = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    connection.close()
    assert "captures" not in names
    assert not path.with_name(path.name + "-wal").exists()
