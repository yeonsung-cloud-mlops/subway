from collections import defaultdict
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.database import connect
from app.model import KST, PredictionError
from app.scheduled_routing import search


def router(tmp_path, trips, transfers=()):
    db = tmp_path / "schedule.sqlite3"
    segments = {}
    with connect(db) as conn:
        conn.execute(
            "CREATE TABLE timetable_stops(trip_id TEXT, station_id TEXT, line INTEGER, week TEXT, service TEXT, train_no TEXT, arrival_seconds INTEGER, departure_seconds INTEGER, source_row INTEGER, destination TEXT)"
        )
        row = 0
        for name, service, stops in trips:
            for station, arrival, departure in stops:
                row += 1
                conn.execute(
                    "INSERT INTO timetable_stops VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        name,
                        station,
                        9,
                        "DAY",
                        service,
                        name,
                        arrival,
                        departure,
                        row,
                        stops[-1][0],
                    ),
                )
            for a, b in zip(stops, stops[1:]):
                segments[a[0], b[0], service] = dict(
                    from_id=a[0], to_id=b[0], service=service
                )
    graph = defaultdict(list)
    for a, b, minutes in transfers:
        graph[a].append(
            dict(kind="transfer", to_id=b, transfer={"walking_minutes": minutes})
        )
    return SimpleNamespace(
        model=SimpleNamespace(db_path=db, segments=lambda: list(segments.values())),
        graph=graph,
    )


AT = datetime(2026, 9, 21, 8, tzinfo=KST)
H = 8 * 3600


def test_later_express_overtakes_local(tmp_path):
    r = router(
        tmp_path,
        [
            (
                "local",
                "일반",
                [("A", H, H), ("B", H + 600, H + 610), ("C", H + 1200, H + 1210)],
            ),
            ("express", "급행", [("A", H + 180, H + 180), ("C", H + 600, H + 610)]),
        ],
    )
    edges, meta = search(r, ["A"], {"C"}, AT)
    assert [e["schedule"]["train_no"] for e in edges] == ["express"]
    assert edges[0]["waiting_minutes"] == 3
    assert meta["route_search_basis"] == "time_expanded_earliest_arrival"
    edges, _ = search(r, ["A"], {"C"}, AT, allow_express=False)
    assert all(e["schedule"]["train_no"] == "local" for e in edges)


def test_same_train_continuation_does_not_need_platform_buffer(tmp_path):
    r = router(
        tmp_path,
        [
            (
                "through",
                "일반",
                [("A", H, H), ("B", H + 120, H + 140), ("C", H + 240, H + 250)],
            )
        ],
    )
    edges, _ = search(r, ["A"], {"C"}, AT)
    assert len(edges) == 2
    assert edges[1]["waiting_minutes"] == 0
    assert edges[1]["dwell_minutes"] == pytest.approx(1 / 3)


def test_transfer_walk_misses_departure_and_changes_route(tmp_path):
    r = router(
        tmp_path,
        [
            ("first", "일반", [("A", H, H), ("B", H + 120, H + 130)]),
            ("missed", "일반", [("X", H + 180, H + 180), ("D", H + 300, H + 310)]),
            ("late", "일반", [("X", H + 1200, H + 1200), ("D", H + 1320, H + 1330)]),
            ("direct", "일반", [("A", H + 60, H + 60), ("D", H + 600, H + 610)]),
        ],
        [("B", "X", 2)],
    )
    edges, _ = search(r, ["A"], {"D"}, AT)
    assert [e["schedule"]["train_no"] for e in edges] == ["direct"]


def test_same_platform_short_turn_requires_actual_next_train(tmp_path):
    r = router(
        tmp_path,
        [
            ("short", "일반", [("A", H, H), ("B", H + 120, H + 130)]),
            ("too_soon", "일반", [("B", H + 140, H + 140), ("C", H + 240, H + 250)]),
            ("later", "일반", [("B", H + 240, H + 240), ("C", H + 360, H + 370)]),
        ],
    )
    edges, _ = search(r, ["A"], {"C"}, AT)
    assert [e["schedule"]["train_no"] for e in edges] == ["short", "later"]
    assert edges[1]["train_change_wait_minutes"] == 2


def test_no_schedule_never_silently_invents_route(tmp_path):
    r = router(
        tmp_path, [("old", "일반", [("A", H - 120, H - 120), ("C", H - 60, H - 50)])]
    )
    with pytest.raises(PredictionError):
        search(r, ["A"], {"C"}, AT)


def test_fewer_transfers_can_choose_later_direct_train(tmp_path):
    r = router(
        tmp_path,
        [
            ("one", "일반", [("A", H, H), ("B", H + 120, H + 130)]),
            ("two", "급행", [("B", H + 180, H + 180), ("C", H + 300, H + 310)]),
            ("direct", "일반", [("A", H + 60, H + 60), ("C", H + 600, H + 610)]),
        ],
    )
    fast, _ = search(r, ["A"], {"C"}, AT)
    few, _ = search(r, ["A"], {"C"}, AT, strategy="fewest_transfers")
    assert len(fast) == 2
    assert len(few) == 1 and few[0]["schedule"]["train_no"] == "direct"


def test_after_midnight_uses_previous_service_day(tmp_path):
    r = router(
        tmp_path,
        [
            (
                "overnight",
                "일반",
                [
                    ("A", 24 * 3600 + 600, 24 * 3600 + 600),
                    ("C", 24 * 3600 + 720, 24 * 3600 + 730),
                ],
            )
        ],
    )
    edges, _ = search(r, ["A"], {"C"}, datetime(2026, 9, 22, 0, 5, tzinfo=KST))
    assert edges[0]["scheduled_departure"] == "2026-09-22T00:10:00+09:00"
    assert edges[0]["waiting_minutes"] == 5


def test_weekday_trains_are_not_used_on_sunday(tmp_path):
    r = router(tmp_path, [("weekday", "일반", [("A", H, H), ("C", H + 120, H + 130)])])
    with pytest.raises(PredictionError):
        search(r, ["A"], {"C"}, datetime(2026, 9, 27, 8, tzinfo=KST))
