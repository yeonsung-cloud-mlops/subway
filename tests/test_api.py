import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("api")
    with TestClient(create_app(tmp_path / "test.sqlite3")) as c:
        yield c, tmp_path / "test.sqlite3"


def test_predict_and_sqlite(client):
    c, db = client
    assert c.get("/health").status_code == 200
    assert len(c.get("/v1/segments").json()["segments"]) == 640
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
        assert conn.execute("SELECT count(*) FROM predictions").fetchone()[0] >= 12


def test_station_metadata_and_raw_pages(client):
    c, _ = client
    assert len(c.get("/v1/stations").json()["stations"]) == 315
    assert len(c.get("/v1/stations?line=9").json()["stations"]) == 38
    s = c.get("/v1/stations/2:226").json()
    assert s["name"] == "사당" and s["address"] and s["latitude"]
    r = c.get("/v1/stations/2:226/observations?limit=2").json()
    assert r["total"] > 2 and len(r["observations"]) == 2
    assert (
        r["observations"]
        != c.get("/v1/stations/2:226/observations?limit=2&offset=2").json()[
            "observations"
        ]
    )
    assert c.get("/v1/stations/nope").status_code == 404
    assert c.get("/v1/stations/2:226/observations?limit=9999").status_code == 422
    assert (
        c.get("/v1/stations/2:226/ridership?service_date=2025-01-01").status_code == 200
    )


def test_all_lines_api(client):
    c, _ = client
    for line in range(1, 10):
        s = c.get(f"/v1/segments?line={line}").json()["segments"][0]
        r = c.post(
            "/v1/predict",
            json={
                "line": line,
                "service": s["service"],
                "from_station": s["from_station"],
                "to_station": s["to_station"],
                "at": "2026-09-21T08:00:00+09:00",
            },
        )
        assert r.status_code == 200, r.text
        assert (
            r.json()["inference_mode"] == "on_request"
            and r.json()["car_count"] == s["car_count"]
        )


def test_journey_endpoint(client):
    c, db = client
    r = c.post(
        "/v1/journeys/predict",
        json={
            "from_station": "건대",
            "to_station": "고속터미널",
            "at": "2026-09-21T08:15:00+09:00",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["ride_segments"] == 7 and r.json()["legs"][0]["line"] == 7
    with sqlite3.connect(db) as conn:
        stored = json.loads(
            conn.execute(
                "SELECT result_json FROM predictions WHERE id=?",
                (r.json()["prediction_id"],),
            ).fetchone()[0]
        )
    assert stored["prediction_kind"] == "unvalidated_journey_car_scenario"
    assert (
        c.post(
            "/v1/journeys/predict",
            json={"from_station": "건대", "to_station": "건대입구"},
        ).status_code
        == 422
    )
