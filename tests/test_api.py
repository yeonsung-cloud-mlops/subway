import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "test.sqlite3")) as c:
        yield c, tmp_path / "test.sqlite3"


def test_predict_and_sqlite(client):
    c, db = client
    assert c.get("/health").status_code == 200
    assert len(c.get("/v1/segments").json()["segments"]) == 86
    assert c.get("/v1/model").json()["metrics"]["car_accuracy"] is None
    r = c.post(
        "/v1/predict",
        json={
            "from_station": "사당",
            "to_station": "방배",
            "at": "2026-09-21T08:15:00+09:00",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["time_bin"] == "08:00"
    with sqlite3.connect(db) as conn:
        stored = json.loads(
            conn.execute("SELECT result_json FROM predictions").fetchone()[0]
        )
    assert stored["prediction_kind"] == "unvalidated_car_scenario"


@pytest.mark.parametrize(
    "extra",
    [
        {"scenario_strength": -1},
        {"scenario_strength": 0.4},
        {"at": "nonsense"},
        {"at": "2026-09-21T03:00:00+09:00"},
        {"to_station": "강남"},
        {"unknown": 3},
    ],
)
def test_validation(client, extra):
    c, _ = client
    r = c.post(
        "/v1/predict",
        json={
            "from_station": "사당",
            "to_station": "방배",
            "at": "2026-09-21T08:00:00+09:00",
            **extra,
        },
    )
    assert r.status_code == 422


def test_time_only_and_omitted(client, monkeypatch):
    c, _ = client
    # Clock injected at the model boundary, independent of test machine date or time.
    import app.model as mod

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 21, 9, 12, tzinfo=mod.KST)

    monkeypatch.setattr(mod, "datetime", Clock)
    for extra, slot in [({}, "09:00"), ({"at": "08:15"}, "08:00")]:
        r = c.post(
            "/v1/predict", json={"from_station": "사당", "to_station": "방배", **extra}
        )
        assert r.status_code == 200, r.text
        assert r.json()["time_bin"] == slot


def test_parallel_writes(client):
    c, db = client

    def call(_):
        return c.post(
            "/v1/predict",
            json={
                "from_station": "사당",
                "to_station": "방배",
                "at": "2026-09-21T08:00:00+09:00",
            },
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(call, range(12)))
    assert all(r.status_code == 200 for r in responses)
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT count(*) FROM predictions").fetchone()[0] == 12
