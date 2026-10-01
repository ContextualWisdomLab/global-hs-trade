import json
import sqlite3
import subprocess
import sys

import pytest

from tests.helpers import mod, source


def baseline(**changes):
    record = {
        "record_kind": "national_aggregate",
        "source_identifier": "test-source",
        "reporter_country": "BR",
        "partner_country": "WORLD",
        "recorded_flow": "X",
        "period": "2024",
        "hs6": "090111",
        "hs_revision": "HS2022",
        "value": "100",
        "value_currency": "USD",
        "value_basis": "FOB",
        "net_weight_kg": "10",
        "quantity": "10",
        "quantity_unit": "kg",
        "customs_code": "C00",
        "transport_mode": 0,
        "retrieved_at": "2026-09-12T00:00:00Z",
    }
    record.update(changes)
    return record


@pytest.fixture
def ledger(tmp_path):
    database = mod("storage").Ledger(tmp_path / "trade.sqlite")
    database.register_source(source())
    yield database
    database.close()


def test_baseline_revisions_preserve_history_and_current_value(ledger):
    ledger.save_baselines([baseline()])
    ledger.save_baselines([baseline(value="125")])

    assert [item["value"] for item in ledger.baseline_history()] == ["100", "125"]
    assert [item["baseline_revision"] for item in ledger.baseline_history()] == [1, 2]
    assert ledger.baselines()[0]["value"] == "125"


def test_baseline_replay_is_idempotent_and_cannot_roll_back_current(ledger):
    first = baseline()
    ledger.save_baselines([first])
    ledger.save_baselines([baseline(retrieved_at="2026-09-13T00:00:00Z")])
    ledger.save_baselines([baseline(value="125")])
    ledger.save_baselines([first])

    assert len(ledger.baseline_history()) == 2
    assert ledger.baselines()[0]["value"] == "125"


def test_invalid_baseline_batch_rolls_back_before_writing(ledger):
    ledger.save_baselines([baseline()])

    with pytest.raises(ValueError):
        ledger.save_baselines([baseline(value="125"), baseline(hs_revision="invented")])

    assert len(ledger.baseline_history()) == 1
    assert ledger.baselines()[0]["value"] == "100"


def test_legacy_baseline_snapshot_migrates_to_revision_one(tmp_path):
    path = tmp_path / "legacy.sqlite"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE sources(source_identifier TEXT PRIMARY KEY, configuration TEXT NOT NULL);
        CREATE TABLE baselines(
          baseline_key TEXT PRIMARY KEY,
          source_identifier TEXT NOT NULL REFERENCES sources(source_identifier),
          hs6 TEXT NOT NULL,
          period TEXT NOT NULL,
          payload TEXT NOT NULL
        );
        """
    )
    record = baseline()
    connection.execute(
        "INSERT INTO sources VALUES (?, ?)",
        ("test-source", json.dumps(source(), sort_keys=True, separators=(",", ":"))),
    )
    connection.execute(
        "INSERT INTO baselines VALUES (?, ?, ?, ?, ?)",
        ("legacy-key", "test-source", "090111", "2024", json.dumps(record)),
    )
    connection.commit()
    connection.close()

    with mod("storage").Ledger(path) as migrated:
        history = migrated.baseline_history()

    assert history[0]["baseline_revision"] == 1
    assert history[0]["value"] == "100"
    assert history[0]["baseline_content_hash"]


def test_cli_exposes_baseline_history(tmp_path):
    path = tmp_path / "history.sqlite"
    with mod("storage").Ledger(path) as database:
        database.register_source(source())
        database.save_baselines([baseline(), baseline(value="125")])

    result = subprocess.run(
        [sys.executable, "-m", "global_hs_trade", "baselines", "--db", str(path), "--history"],
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert [record["baseline_revision"] for record in payload["records"]] == [1, 2]
