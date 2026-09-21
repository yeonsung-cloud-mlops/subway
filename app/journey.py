"""Transfer-aware route search and on-request forecasts along the journey."""

import heapq
import itertools
import json
from collections import defaultdict
from datetime import datetime, time, timedelta

from app.database import connect
from app.model import KST, PredictionError

ALIASES = {
    "건대": "건대입구",
    "고터": "고속터미널",
    "서울": "서울역",
    "당고개": "불암산",
    "뚝섬유원지": "자양",
}


class JourneyModel:
    def __init__(self, model):
        self.model = model
        self.stations = {s["id"]: s for s in model.stations}
        self.graph = defaultdict(list)
        for s in model.segments():
            # Nominal travel assumptions, not a live timetable or certified arrival estimate.
            distance = (
                abs(int(s["from_id"].split(":")[1]) - int(s["to_id"].split(":")[1]))
                if s["line"] == 9
                else 1
            )
            minutes = max(2.0, 1.3 * distance) if s["service"] == "급행" else 2.0
            self.graph[s["from_id"]].append(
                {"kind": "ride", "minutes": minutes, "to_id": s["to_id"], "segment": s}
            )
        with connect(model.db_path) as conn:
            for row in conn.execute("SELECT details_json FROM transfers"):
                t = json.loads(row[0])
                self.graph[t["from_id"]].append(
                    {
                        "kind": "transfer",
                        "to_id": t["to_id"],
                        "minutes": t["walking_minutes"] + 3,
                        "transfer": t,
                    }
                )

    def plan(
        self,
        origin,
        destination,
        from_line=None,
        to_line=None,
        strategy="estimated_fastest",
        allow_express=True,
    ):
        origin = ALIASES.get(origin.strip(), origin.strip())
        destination = ALIASES.get(destination.strip(), destination.strip())
        if origin == destination:
            raise PredictionError("출발역과 도착역이 같습니다.")
        starts = [
            s["id"]
            for s in self.stations.values()
            if s["name"] == origin and (from_line is None or s["line"] == from_line)
        ]
        targets = {
            s["id"]
            for s in self.stations.values()
            if s["name"] == destination and (to_line is None or s["line"] == to_line)
        }
        if not starts or not targets:
            raise PredictionError(
                "지원 범위 안의 출발역·도착역을 입력하세요. /v1/stations에서 확인할 수 있습니다."
            )
        serial = itertools.count()
        heap = []
        best = {}
        prev = {}
        for station in starts:
            state = (station, None)
            best[state] = (0, 0)
            heapq.heappush(heap, ((0, 0), next(serial), state))
        end = None
        while heap:
            cost, _, state = heapq.heappop(heap)
            if best.get(state) != cost:
                continue
            if state[0] in targets:
                end = state
                break
            for original in self.graph[state[0]]:
                edge = dict(original)
                change = 0
                if edge["kind"] == "ride":
                    segment = edge["segment"]
                    service = segment["service"]
                    mode = (
                        service,
                        segment["car_count"],
                        segment["direction"]
                        if segment["line"] != 6
                        else "응암순환연속",
                    )
                    if not allow_express and service == "급행":
                        continue
                    if state[1] is not None and state[1] != mode:
                        change = 1
                        edge["minutes"] += 3
                        edge["train_change_wait_minutes"] = 3
                    next_state = (edge["to_id"], mode)
                else:
                    change = 1
                    next_state = (edge["to_id"], None)
                delta = (
                    (change, edge["minutes"])
                    if strategy == "fewest_transfers"
                    else (edge["minutes"], change)
                )
                new = (cost[0] + delta[0], cost[1] + delta[1])
                if next_state not in best or new < best[next_state]:
                    best[next_state] = new
                    prev[next_state] = (state, edge)
                    heapq.heappush(heap, (new, next(serial), next_state))
        if end is None:
            raise PredictionError(
                "확보한 노선·환승 데이터 범위에서 경로를 찾지 못했습니다."
            )
        edges = []
        cursor = end
        while cursor in prev:
            before, edge = prev[cursor]
            edge["from_id"] = before[0]
            edges.append(edge)
            cursor = before
        return origin, destination, list(reversed(edges))

    def predict(
        self,
        origin,
        destination,
        at=None,
        strength=0.2,
        from_line=None,
        to_line=None,
        strategy="estimated_fastest",
        allow_express=True,
        now=None,
    ):
        origin, destination, edges = self.plan(
            origin, destination, from_line, to_line, strategy, allow_express
        )
        clock = now or datetime.now(KST)
        if isinstance(at, time):
            at = datetime.combine(clock.astimezone(KST).date(), at)
        departure = at or clock
        departure = (
            departure.replace(tzinfo=KST)
            if departure.tzinfo is None
            else departure.astimezone(KST)
        )
        cursor = departure
        steps = []
        legs = []
        leg = None
        transfer_count = 0
        for edge in edges:
            minutes = edge["minutes"]
            end = cursor + timedelta(minutes=minutes)
            if edge["kind"] == "transfer":
                transfer_count += 1
                leg = None
                steps.append(
                    {
                        "kind": "transfer",
                        "from_station": self.stations[edge["from_id"]]["name"],
                        "to_station": self.stations[edge["to_id"]]["name"],
                        "from_line": self.stations[edge["from_id"]]["line"],
                        "to_line": self.stations[edge["to_id"]]["line"],
                        "start_at": cursor.isoformat(),
                        "end_at": end.isoformat(),
                        "estimated_minutes": round(minutes, 3),
                        "waiting_minutes_assumption": 3,
                        **edge["transfer"],
                    }
                )
            else:
                s = edge["segment"]
                wait = edge.get("train_change_wait_minutes", 0)
                forecast_at = cursor + timedelta(minutes=wait)
                if wait:
                    leg = None
                    transfer_count += 1
                if leg is None:
                    leg = {
                        "line": s["line"],
                        "service": s["service"],
                        "from_station": s["from_station"],
                        "to_station": s["to_station"],
                        "car_count": s["car_count"],
                        "step_indices": [],
                    }
                    legs.append(leg)
                leg["to_station"] = s["to_station"]
                leg["step_indices"].append(len(steps))
                try:
                    forecast = self.model.predict(
                        s["from_station"],
                        s["to_station"],
                        forecast_at,
                        strength,
                        line=s["line"],
                        service=s["service"],
                    )
                    status = "available"
                    reason = None
                except PredictionError as exc:
                    forecast = None
                    status = "unavailable"
                    reason = str(exc)
                steps.append(
                    {
                        "kind": "ride",
                        "line": s["line"],
                        "service": s["service"],
                        "from_station": s["from_station"],
                        "to_station": s["to_station"],
                        "start_at": cursor.isoformat(),
                        "forecast_at": forecast_at.isoformat(),
                        "end_at": end.isoformat(),
                        "estimated_minutes": round(minutes, 3),
                        "ride_minutes": round(minutes - wait, 3),
                        "train_change_wait_minutes": wait,
                        "status": status,
                        "unavailable_reason": reason,
                        "forecast": forecast,
                    }
                )
            cursor = end
        for leg in legs:
            valid = [steps[i] for i in leg["step_indices"] if steps[i]["forecast"]]
            weight = sum(s["ride_minutes"] for s in valid)
            leg["predicted_segments"] = len(valid)
            leg["total_segments"] = len(leg["step_indices"])
            leg["coverage"] = len(valid) / len(leg["step_indices"])
            leg["cars"] = (
                []
                if not weight
                else [
                    {
                        "car": c,
                        "estimated_mean_congestion_pct": round(
                            sum(
                                s["forecast"]["cars"][c - 1]["estimated_congestion_pct"]
                                * s["ride_minutes"]
                                for s in valid
                            )
                            / weight,
                            3,
                        ),
                        "estimated_peak_congestion_pct": max(
                            s["forecast"]["cars"][c - 1]["estimated_congestion_pct"]
                            for s in valid
                        ),
                    }
                    for c in range(1, leg["car_count"] + 1)
                ]
            )
        rides = [s for s in steps if s["kind"] == "ride"]
        valid = [s for s in rides if s["forecast"]]
        weight = sum(s["ride_minutes"] for s in valid)
        return {
            "model_version": self.model.artifact["version"],
            "prediction_kind": "unvalidated_journey_car_scenario",
            "inference_mode": "on_request",
            "from_station": origin,
            "to_station": destination,
            "departure_at": departure.isoformat(),
            "estimated_arrival_at": cursor.isoformat(),
            "estimated_minutes": round((cursor - departure).total_seconds() / 60, 3),
            "route_strategy": strategy,
            "transfer_count": transfer_count,
            "ride_segments": len(rides),
            "predicted_segments": len(valid),
            "status": "complete"
            if len(valid) == len(rides)
            else ("partial" if valid else "unavailable"),
            "available_segment_weighted_mean_pct": round(
                sum(
                    s["forecast"]["train_mean_congestion_pct"] * s["ride_minutes"]
                    for s in valid
                )
                / weight,
                3,
            )
            if weight
            else None,
            "legs": legs,
            "steps": steps,
            "warnings": [
                "칸별 값은 실측 검증되지 않은 시나리오이며 환승 전후의 칸 번호는 서로 다른 열차를 뜻합니다.",
                "이동시간은 일반 구간당 2분, 9호선 급행은 통과 역 수 기반 가정입니다. 실제 시간표·대기·지연과 다릅니다.",
                "환승 보행시간은 방향별 공식 경로값의 평균(없으면 5분), 환승 후 대기는 3분 가정입니다.",
                "요약 혼잡도는 예측 가능한 탑승 구간만 집계하며 도보·대기시간은 제외합니다.",
            ],
        }
