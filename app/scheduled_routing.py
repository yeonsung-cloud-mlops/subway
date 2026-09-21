"""Time-expanded earliest-arrival search over validated consecutive train stops."""

import heapq
import itertools
from collections import defaultdict
from datetime import datetime, time, timedelta

import holidays

from app.database import connect
from app.model import KST, PredictionError


def search(
    journey,
    starts,
    targets,
    departure,
    allow_express=True,
    strategy="estimated_fastest",
):
    horizon = departure + timedelta(hours=6)
    segments = {
        (s["from_id"], s["to_id"], s["service"]): s for s in journey.model.segments()
    }
    outgoing = defaultdict(list)
    continuation = {}
    connections = {}
    # Preserve original row adjacency: never bridge a missing or invalid stop.
    with connect(journey.model.db_path) as conn:
        for delta in (-1, 0, 1):
            date = departure.date() + timedelta(days=delta)
            base = datetime.combine(date, time(), tzinfo=KST)
            week = (
                "END"
                if date.weekday() == 6 or date in holidays.KR(years=date.year)
                else "SAT"
                if date.weekday() == 5
                else "DAY"
            )
            rows = conn.execute(
                "SELECT * FROM timetable_stops WHERE week=? ORDER BY trip_id,coalesce(arrival_seconds,departure_seconds),source_row",
                (week,),
            )
            previous = None
            for raw in rows:
                b = dict(raw)
                a, previous = previous, b
                if not a or a["trip_id"] != b["trip_id"]:
                    continue
                seg = segments.get((a["station_id"], b["station_id"], a["service"]))
                dep, arr = a["departure_seconds"], b["arrival_seconds"]
                if not seg or dep is None or arr is None or not 0 < arr - dep <= 1800:
                    continue
                if not allow_express and a["service"] == "급행":
                    continue
                dep, arr = base + timedelta(seconds=dep), base + timedelta(seconds=arr)
                if dep < departure or arr > horizon:
                    continue
                key = (date.isoformat(), a["trip_id"], a["source_row"])
                edge = {
                    "kind": "ride",
                    "segment": seg,
                    "from_id": seg["from_id"],
                    "to_id": seg["to_id"],
                    "dep": dep,
                    "arr": arr,
                    "schedule": {
                        "trip_id": a["trip_id"],
                        "train_no": a["train_no"],
                        "destination": a["destination"],
                        "source_rows": [a["source_row"], b["source_row"]],
                    },
                }
                connections[key] = edge
                outgoing[seg["from_id"]].append(key)
                continuation[key] = (date.isoformat(), b["trip_id"], b["source_row"])
    serial = itertools.count()
    heap, best, prev = [], {}, {}
    fewest = strategy == "fewest_transfers"

    def offer(state, at, boards, parent=None, edge=None):
        cost = (boards, at) if fewest else (at, boards)
        if state in best and best[state] <= cost:
            return
        best[state] = cost
        prev[state] = (parent, edge)
        heapq.heappush(heap, (cost, next(serial), state, at, boards))

    # Keep boarding counts as separate labels: a later platform arrival with fewer
    # changes can catch the same onward train and win the final arrival-time tie.
    # Platform states are ready-to-board; onboard states keep train identity, allowing dwell without reboarding.
    for station in starts:
        offer(("platform", station, 0), departure, 0)
    end = None
    while heap:
        cost, _, state, at, boards = heapq.heappop(heap)
        if best.get(state) != cost:
            continue
        onboard = state[0] == "train"
        station = connections[state[1]]["to_id"] if onboard else state[1]
        if station in targets and boards > 0:
            end = state
            break
        if onboard:
            following = continuation.get(state[1])
            edge = connections.get(following)
            if edge and edge["dep"] >= at:
                offer(
                    ("train", following, boards),
                    edge["arr"],
                    boards,
                    state,
                    edge,
                )
            # Same-line train change: explicit minimum platform movement assumption.
            offer(
                ("platform", station, boards),
                at + timedelta(minutes=1),
                boards,
                state,
                {"kind": "platform_buffer", "minutes": 1},
            )
        else:
            for key in outgoing[station]:
                edge = connections[key]
                if edge["dep"] >= at:
                    offer(
                        ("train", key, boards + 1),
                        edge["arr"],
                        boards + 1,
                        state,
                        edge,
                    )
        # Transfer walking starts at arrival, without the same-platform change buffer.
        for original in journey.graph[station]:
            if original["kind"] != "transfer" or boards == 0:
                continue
            edge = dict(
                original,
                from_id=station,
                minutes=original["transfer"]["walking_minutes"],
                timing_basis="source_walking_average",
            )
            arrival = at + timedelta(minutes=edge["minutes"])
            if arrival <= horizon:
                offer(
                    ("platform", edge["to_id"], boards),
                    arrival,
                    boards,
                    state,
                    edge,
                )
    if end is None:
        raise PredictionError(
            "공개 시간표의 6시간 탐색 범위에서 연결되는 열차 경로가 없습니다. 다른 시각을 선택하거나 시간표 미사용 모드를 명시하세요."
        )
    route = []
    while prev[end][0] is not None:
        parent, edge = prev[end]
        route.append(edge)
        end = parent
    route.reverse()
    edges, cursor, last_trip = [], departure, None
    pending_buffer = False
    for raw in route:
        edge = dict(raw)
        if edge["kind"] == "platform_buffer":
            pending_buffer = True
            continue
        if edge["kind"] == "transfer":
            cursor += timedelta(minutes=edge["minutes"])
            last_trip = None
        else:
            dep, arr = edge.pop("dep"), edge.pop("arr")
            trip = edge["schedule"]["trip_id"]
            changed = pending_buffer and last_trip is not None
            continuing = last_trip == trip and not pending_buffer
            gap = (dep - cursor).total_seconds() / 60
            edge.update(
                minutes=(arr - cursor).total_seconds() / 60,
                scheduled_departure=dep.isoformat(),
                scheduled_arrival=arr.isoformat(),
                waiting_minutes=0 if continuing else gap,
                dwell_minutes=gap if continuing else 0,
                timing_basis="official_snapshot",
                train_change_wait_minutes=gap if changed else 0,
            )
            cursor, last_trip = arr, trip
            pending_buffer = False
        edges.append(edge)
    return edges, {
        "status": "snapshot",
        "as_of": "2025-09-30",
        "checked_on": "2026-09-21",
        "source": "OA-22522",
        "current_service_verified": False,
        "matched_ride_segments": sum(e["kind"] == "ride" for e in edges),
        "fallback_ride_segments": 0,
        "route_search_basis": "time_expanded_earliest_arrival"
        if not fewest
        else "time_expanded_fewest_boardings_then_arrival",
        "search_horizon_hours": 6,
        "same_platform_change_minutes": 1,
        "transfer_walk_basis": "official_direction_averages_or_labeled_fallback",
    }
