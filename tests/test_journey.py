from datetime import datetime
from pathlib import Path

import pytest

from app.journey import JourneyModel
from app.model import KST, Model, PredictionError


@pytest.fixture(scope="module")
def journey():
    return JourneyModel(Model(Path(__file__).resolve().parents[1]))


def test_konkuk_to_express_bus_terminal(journey):
    r = journey.predict(
        "건대", "고속터미널", datetime(2026, 9, 21, 8, 15), use_timetable=False
    )
    assert r["from_station"] == "건대입구"
    assert r["status"] == "complete" and r["transfer_count"] == 0
    assert len(r["legs"]) == 1 and r["legs"][0]["line"] == 7
    assert r["ride_segments"] == 7 and r["estimated_minutes"] == 14
    assert len(r["legs"][0]["cars"]) == 8
    assert (
        r["steps"][0]["from_station"] == "건대입구"
        and r["steps"][-1]["to_station"] == "고속터미널"
    )
    assert r["steps"][1]["forecast_at"] == "2026-09-21T08:17:00+09:00"
    assert r["estimated_arrival_at"] == "2026-09-21T08:29:00+09:00"


def test_transfer_changes_leg_and_car_identity(journey):
    r = journey.predict(
        "서울역", "봉은사", datetime(2026, 9, 21, 8), from_line=1, to_line=9
    )
    assert (
        r["status"] == "complete" and r["transfer_count"] >= 1 and len(r["legs"]) >= 2
    )
    transfers = [s for s in r["steps"] if s["kind"] == "transfer"]
    assert transfers and all(
        s["estimated_minutes"] == s["walking_minutes"] > 0 for s in transfers
    )
    for leg in r["legs"]:
        assert len(leg["cars"]) == leg["car_count"]
    for a, b in zip(r["steps"], r["steps"][1:]):
        assert a["end_at"] == b["start_at"]
    assert r["legs"][-1]["line"] == 9


def test_line_constraint_and_no_express(journey):
    r = journey.predict(
        "건대",
        "고터",
        datetime(2026, 9, 21, 8),
        from_line=2,
        to_line=3,
        allow_express=False,
        strategy="fewest_transfers",
    )
    assert r["legs"][0]["line"] == 2 and r["legs"][-1]["line"] == 3
    assert r["transfer_count"] == 1 and all(
        leg["service"] == "일반" for leg in r["legs"]
    )


def test_partial_after_service_hours(journey):
    r = journey.predict(
        "건대", "고터", datetime(2026, 9, 22, 0, 58), use_timetable=False
    )
    assert r["status"] in ["partial", "unavailable"]
    assert any(s["unavailable_reason"] for s in r["steps"] if s["kind"] == "ride")
    assert r["predicted_segments"] < r["ride_segments"]


def test_missing_stations_and_same_station(journey):
    for origin, dest in [("건대", "건대입구"), ("부산", "고터"), ("건대", "수원")]:
        with pytest.raises(PredictionError):
            journey.predict(origin, dest, datetime(2026, 9, 21, 8))


def test_omitted_time(journey):
    r = journey.predict("건대", "고터", now=datetime(2026, 9, 21, 8, 15, tzinfo=KST))
    assert r["departure_at"] == "2026-09-21T08:15:00+09:00"


def test_line2_branch_requires_new_train(journey):
    r = journey.predict(
        "용답",
        "건대입구",
        datetime(2026, 9, 21, 8),
        from_line=2,
        to_line=2,
        use_timetable=False,
    )
    assert r["transfer_count"] == 1
    assert [leg["car_count"] for leg in r["legs"]] == [4, 10]
    assert r["steps"][1]["train_change_wait_minutes"] == 3


def test_official_door_features_change_allocation_without_changing_mean(journey):
    r = journey.predict(
        "사당", "압구정", datetime(2026, 9, 21, 8, 15), from_line=2, to_line=3
    )
    transfer = next(s for s in r["steps"] if s["kind"] == "transfer")
    assert transfer["door_guidance"]["status"] == "available"
    route = transfer["door_guidance"]["routes"][0]
    assert route["alight"]["car"] == 10 and route["alight"]["door"] == 4
    assert route["board"]["car"] == 7 and route["board"]["door"] == 4
    before = r["steps"][0]["forecast"]
    assert before["location_features"]["transfer_alight_cars"] == [10]
    assert before["location_features"]["exit_mapping_status"].startswith("unavailable")
    assert sum(c["estimated_congestion_pct"] for c in before["cars"]) / len(
        before["cars"]
    ) == pytest.approx(before["train_mean_congestion_pct"], abs=0.002)
    assert len({c["estimated_congestion_pct"] for c in before["cars"]}) > 1
    assert before["evidence"]["car_ground_truth_count"] == 0
    assert r["endpoint_facilities"]["departure"]["status"] == "available"


def test_snapshot_has_connected_trains_and_explicit_age(journey):
    r = journey.predict("건대", "고터", datetime(2026, 9, 21, 8, 15))
    assert r["timetable"]["current_service_verified"] is False
    assert r["timetable"]["fallback_ride_segments"] == 0
    assert r["timetable"]["route_search_basis"] == "time_expanded_earliest_arrival"
    assert r["arrival_alighting_guidance"]["points"]
    for a, b in zip(r["steps"], r["steps"][1:]):
        assert a["end_at"] == b["start_at"]
    for s in r["steps"]:
        if s["kind"] == "ride":
            assert s["forecast_at"] >= s["start_at"] and s["forecast_at"] < s["end_at"]
