import json
import math
from datetime import datetime
from pathlib import Path

import pytest

from app.model import KST, Model, PredictionError, multipliers, time_context
from scripts.train import fit, score

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def model():
    return Model(ROOT)


def test_every_segment_and_conservation(model):
    assert len(model.segments()) == 86
    for s in model.segments():
        r = model.predict(
            s["from_station"], s["to_station"], datetime(2026, 9, 21, 8, 15, tzinfo=KST)
        )
        assert r["direction"] == s["direction"]
        assert len(r["cars"]) == 10
        vals = [c["estimated_congestion_pct"] for c in r["cars"]]
        assert all(math.isfinite(v) and v >= 0 for v in vals)
        assert abs(sum(vals) / 10 - r["train_mean_congestion_pct"]) < 0.002
        assert r["evidence"]["car_ground_truth_count"] == 0
        for c in r["cars"]:
            assert (
                c["scenario_range_pct"][0]
                <= c["estimated_congestion_pct"]
                <= c["scenario_range_pct"][1]
            )


def test_direction_and_locations(model):
    r = model.predict("사당", "방배", datetime(2026, 9, 21, 8))
    assert r["direction"] == "외선"
    assert r["location_features"]["transfer_board_cars"] == [6]
    assert r["location_features"]["access_cars"] == [3, 8]
    r = model.predict("사당", "낙성대", datetime(2026, 9, 21, 8))
    assert r["direction"] == "내선"
    assert (
        model.predict("충정로", "시청", datetime(2026, 9, 21, 8))["direction"] == "내선"
    )


def test_default_now_timezone_midnight():
    now = datetime(2026, 9, 22, 0, 15, tzinfo=KST)
    dt, date, day, slot, holiday = time_context(None, now)
    assert dt == now and str(date) == "2026-09-21" and slot == "24:00" and day == "평일"
    assert (
        time_context(datetime.fromisoformat("2026-09-20T23:15:00+00:00"))[3] == "08:00"
    )
    assert time_context(datetime(2026, 12, 25, 8))[2] == "일요일"


@pytest.mark.parametrize("hour,minute", [(1, 0), (3, 0), (5, 29)])
def test_out_of_service(hour, minute):
    with pytest.raises(PredictionError):
        time_context(datetime(2026, 9, 21, hour, minute))


@pytest.mark.parametrize(
    "origin,destination",
    [("서울역", "사당"), ("사당", "사당"), ("사당", "강남"), ("까치산", "신도림")],
)
def test_unsupported(model, origin, destination):
    with pytest.raises(PredictionError):
        model.predict(origin, destination, datetime(2026, 9, 21, 8))


def test_no_future_leakage(model):
    with pytest.raises(PredictionError):
        model.predict("사당", "방배", datetime(2025, 9, 21, 8))


def test_missing_profile_and_uniform(model):
    assert (
        multipliers({"transfer_board_cars": [], "access_cars": []}, 0.3) == [1.0] * 10
    )
    m = Model(ROOT)
    m.artifact["profiles"] = {}
    with pytest.raises(PredictionError):
        m.predict("사당", "방배", datetime(2026, 9, 21, 8))


def test_fit_is_chronological_and_skips_unknown_zero():
    def row(period, v):
        return dict(
            station="226",
            direction="외선",
            daytype="평일",
            time="08:00",
            period=period,
            congestion=str(v),
        )

    a, b, c = row("20240101", 20), row("20240201", 40), row("20240301", 0)
    states = fit([b, a, c], 0.5)
    state = next(iter(states.values()))
    assert state == {"value": 30.0, "n": 2, "last_period": "20240201"}
    assert score(states, [row("20240401", 35)])["mae_pp"] == 5
    assert (
        json.loads((ROOT / "artifacts/metrics.json").read_text())["car_accuracy"]
        is None
    )
