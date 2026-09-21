import json
import math
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import holidays

KST = ZoneInfo("Asia/Seoul")


class PredictionError(ValueError):
    pass


def time_context(at, now=None):
    clock = now or datetime.now(KST)
    if isinstance(at, time):
        at = datetime.combine(clock.astimezone(KST).date(), at)
    dt = at or clock
    dt = dt.replace(tzinfo=KST) if dt.tzinfo is None else dt.astimezone(KST)
    minute = dt.hour * 60 + dt.minute
    if 60 <= minute < 330:
        raise PredictionError("01:00~05:29는 지원 운행 시간대 밖입니다.")
    service_date = dt.date() - timedelta(days=1) if minute < 60 else dt.date()
    if minute < 60:
        minute += 1440
    slot = minute // 30 * 30
    holiday = holidays.KR(years=service_date.year).get(service_date)
    daytype = (
        "일요일"
        if holiday or service_date.weekday() == 6
        else ("토요일" if service_date.weekday() == 5 else "평일")
    )
    return dt, service_date, daytype, f"{slot // 60:02d}:{slot % 60:02d}", holiday


def multipliers(loc, strength):
    # Smooth proximity in car-number units, not physical distance or passenger count.
    groups = [loc[x] for x in ["transfer_board_cars", "access_cars"] if loc[x]]
    if not groups:
        return [1.0] * 10
    weights = [
        sum(
            sum(math.exp(-0.5 * ((c - k) / 1.0) ** 2) for k in g) / len(g)
            for g in groups
        )
        / len(groups)
        for c in range(1, 11)
    ]
    mean = sum(weights) / 10
    return [(1 - strength) + strength * w / mean for w in weights]


class Model:
    def __init__(self, root: Path):
        self.artifact = json.loads((root / "artifacts/model.json").read_text())
        self.stations = json.loads((root / "datasets/stations.json").read_text())
        self.locations = json.loads((root / "datasets/locations.json").read_text())
        self.lookup = {s["name"]: i for i, s in enumerate(self.stations)}

    def segments(self):
        return [
            {
                "from_station": s["name"],
                "to_station": self.stations[(i + step) % 43]["name"],
                "direction": direction,
            }
            for i, s in enumerate(self.stations)
            for step, direction in [(1, "내선"), (-1, "외선")]
        ]

    def predict(self, origin, destination, at=None, strength=0.2, now=None):
        if not math.isfinite(strength) or not 0 <= strength <= 0.3:
            raise PredictionError("배분 강도는 0~0.3이어야 합니다.")
        if origin not in self.lookup or destination not in self.lookup:
            raise PredictionError(
                "2호선 본선 역명만 지원합니다. /v1/segments를 확인하세요."
            )
        i, j = self.lookup[origin], self.lookup[destination]
        delta = (j - i) % 43
        if delta not in (1, 42):
            raise PredictionError(
                "현재 버전은 서로 인접한 두 역 사이 구간만 지원합니다."
            )
        direction = "내선" if delta == 1 else "외선"
        station = self.stations[i]["id"]
        dt, date, daytype, slot, holiday = time_context(at, now)
        cutoff = datetime.strptime(self.artifact["trained_through"], "%Y%m%d").date()
        if date <= cutoff:
            raise PredictionError(
                "현재 모델 학습 기준일 이후만 조회할 수 있습니다. 과거 검증은 artifacts/metrics.json을 확인하세요."
            )
        k = f"{station}|{direction}|{daytype}|{slot}"
        p = self.artifact["profiles"].get(k)
        if p is None:
            raise PredictionError("이 구간·시간대에 유효한 혼잡도 조사값이 없습니다.")
        loc = self.locations[f"{station}|{direction}"]
        w = multipliers(loc, strength)
        high = multipliers(loc, 0.3)
        base = p["value"]
        warnings = [
            "칸별 값은 실측 검증되지 않은 위치 기반 시나리오입니다.",
            "출발역·방향의 30분 조사평균 기반이며 다음 열차 또는 도착/출발 순간의 실측값이 아닙니다.",
        ]
        if not loc["transfer_board_cars"] and not loc["access_cars"]:
            warnings.append(
                "방향이 확인된 위치 자료가 없어 칸별 균등 배분을 사용했습니다."
            )
        if holiday:
            warnings.append("공휴일은 일요일 조사 패턴으로 대체했습니다.")
        if (date - cutoff).days > 90:
            warnings.append("최신 학습 조사시점으로부터 90일 이상 지난 조회입니다.")
        if p["last_period"] != self.artifact["trained_through"]:
            warnings.append("최신 조사값이 없어 이전 조사 이력을 사용했습니다.")
        return {
            "model_version": self.artifact["version"],
            "prediction_kind": "unvalidated_car_scenario",
            "line": 2,
            "from_station": origin,
            "to_station": destination,
            "direction": direction,
            "requested_at": dt.isoformat(),
            "service_date": date.isoformat(),
            "daytype": daytype,
            "holiday": holiday,
            "time_bin": slot,
            "train_mean_congestion_pct": round(base, 3),
            "cars": [
                {
                    "car": c,
                    "estimated_congestion_pct": round(base * w[c - 1], 3),
                    "scenario_range_pct": [
                        round(min(base, base * high[c - 1]), 3),
                        round(max(base, base * high[c - 1]), 3),
                    ],
                }
                for c in range(1, 11)
            ],
            "location_features": loc,
            "scenario_strength": strength,
            "range_kind": "sensitivity_strength_0_to_0.3_not_confidence_interval",
            "evidence": {
                "trained_through": self.artifact["trained_through"],
                "profile_last_period": p["last_period"],
                "profile_snapshot_count": p["n"],
                "car_ground_truth_count": 0,
            },
            "warnings": warnings,
        }
