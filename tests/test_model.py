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
    assert len(model.segments()) == 640
    for s in model.segments():
        r = model.predict(
            s["from_station"],
            s["to_station"],
            datetime(2026, 9, 21, 8, 15, tzinfo=KST),
            line=s["line"],
            service=s["service"],
        )
        assert r["direction"] == s["direction"]
        assert len(r["cars"]) == s["car_count"]
        vals = [c["estimated_congestion_pct"] for c in r["cars"]]
        assert all(math.isfinite(v) and v >= 0 for v in vals)
        assert abs(sum(vals) / s["car_count"] - r["train_mean_congestion_pct"]) < 0.002
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


@pytest.mark.parametrize(
    "line,origin,destination,service,count,direction,code",
    [
        (2, "성수", "용답", "일반", 4, "외선", 9002),
        (2, "신도림", "도림천", "일반", 6, "내선", 9003),
        (5, "강동", "둔촌동", "일반", 8, "하선", 9005),
        (5, "강동", "길동", "일반", 8, "하선", 2549),
        (6, "응암", "역촌", "일반", 8, "하선", 9006),
        (6, "구산", "응암", "일반", 8, "하선", 2616),
        (8, "복정", "남위례", "일반", 6, "하선", 2821),
        (9, "김포공항", "마곡나루", "급행", 6, "상선", 4102),
    ],
)
def test_branch_profiles(
    model, line, origin, destination, service, count, direction, code
):
    r = model.predict(
        origin, destination, datetime(2026, 9, 21, 8), line=line, service=service
    )
    assert r["car_count"] == count and r["direction"] == direction
    assert (
        model._lookup[(line, origin, destination, service)]["profile_station"] == code
    )


def test_one_way_loop_and_express_stops(model):
    with pytest.raises(PredictionError):
        model.predict("역촌", "응암", datetime(2026, 9, 21, 8), line=6)
    with pytest.raises(PredictionError):
        model.predict(
            "김포공항", "공항시장", datetime(2026, 9, 21, 8), line=9, service="급행"
        )


def test_inference_interpolates_time(model):
    a = model.predict("사당", "방배", datetime(2026, 9, 21, 8, 0))[
        "train_mean_congestion_pct"
    ]
    b = model.predict("사당", "방배", datetime(2026, 9, 21, 8, 30))[
        "train_mean_congestion_pct"
    ]
    mid = model.predict("사당", "방배", datetime(2026, 9, 21, 8, 15))
    assert mid["interpolation_fraction"] == 0.5
    assert abs(mid["train_mean_congestion_pct"] - (a + b) / 2) < 0.002
