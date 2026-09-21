import json
import math
from datetime import date as date_type
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import holidays

from app.database import connect, seed_database

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


def multipliers(loc, strength, car_count=10):
    groups = [
        loc[x]
        for x in [
            "transfer_board_cars",
            "access_cars",
            "transfer_alight_cars",
            "destination_access_cars",
        ]
        if loc.get(x)
    ]
    if not groups:
        return [1.0] * car_count
    weights = [
        sum(
            sum(math.exp(-0.5 * ((c - k) / 1.0) ** 2) for k in g) / len(g)
            for g in groups
        )
        / len(groups)
        for c in range(1, car_count + 1)
    ]
    mean = sum(weights) / car_count
    return [(1 - strength) + strength * w / mean for w in weights]


class Model:
    def __init__(self, root: Path, db_path=None):
        self.artifact = json.loads((root / "artifacts/model.json").read_text())
        self.db_path = db_path or root / "var/subway.sqlite3"
        seed_database(self.db_path)
        from app.enrichment import seed_enrichment

        seed_enrichment(self.db_path)
        with connect(self.db_path) as conn:
            self.stations = [
                json.loads(r[0])
                for r in conn.execute("SELECT details_json FROM stations")
            ]
            self._segments = [
                json.loads(r[0])
                for r in conn.execute("SELECT details_json FROM segments")
            ]
        self._lookup = {
            (s["line"], s["from_station"], s["to_station"], s["service"]): s
            for s in self._segments
        }

    def segments(self, line=None):
        return [s for s in self._segments if line is None or s["line"] == line]

    def predict(
        self,
        origin,
        destination,
        at=None,
        strength=0.2,
        now=None,
        line=2,
        service="일반",
        location_override=None,
    ):
        if not math.isfinite(strength) or not 0 <= strength <= 0.3:
            raise PredictionError("배분 강도는 0~0.3이어야 합니다.")
        seg = self._lookup.get((line, origin, destination, service))
        if seg is None:
            raise PredictionError(
                "지원하지 않는 구간·노선·열차종류입니다. /v1/segments에서 다음 정차역 조합을 선택하세요."
            )
        dt, date, daytype, slot, holiday = time_context(at, now)
        cutoff = date_type.fromisoformat(
            self.artifact["available_after_by_line"][str(line)]
        )
        if date <= cutoff:
            raise PredictionError(
                "현재 모델 자료 기준일 이후만 조회할 수 있습니다. 과거 검증은 /v1/model을 확인하세요."
            )
        if line == 9 and daytype != "평일":
            daytype = "휴일"

        def profile(tm):
            return self.artifact["profiles"].get(
                f"{line}|{seg['profile_station']}|{seg['direction']}|{service}|{daytype}|{tm}"
            )

        p = profile(slot)
        if p is None:
            raise PredictionError("이 구간·시간대에 유효한 혼잡도 조사값이 없습니다.")
        # Evaluate a continuous time profile at request time; no precomputed car predictions are read.
        minute = dt.hour * 60 + dt.minute + dt.second / 60
        if minute < 60:
            minute += 1440
        slot_min = int(slot[:2]) * 60 + int(slot[3:])
        next_min = slot_min + 30
        following = profile(f"{next_min // 60:02d}:{next_min % 60:02d}")
        fraction = (minute - slot_min) / 30 if following else 0
        base = (
            p["value"] * (1 - fraction)
            + (following["value"] if following else p["value"]) * fraction
        )
        count = seg["car_count"]
        loc = location_override if location_override is not None else seg["locations"]
        w = multipliers(loc, strength, count)
        high = multipliers(loc, 0.3, count)
        warnings = [
            "칸별 값은 실측 검증되지 않은 위치 기반 시나리오입니다.",
            "조사평균 시간 패턴을 요청 시점에 추론한 값이며 실제 도착 열차 또는 순간 재차인원은 아닙니다.",
        ]
        if not any(
            loc.get(k)
            for k in [
                "transfer_board_cars",
                "access_cars",
                "transfer_alight_cars",
                "destination_access_cars",
            ]
        ):
            warnings.append(
                "방향이 확인된 위치 자료가 없어 칸별 균등 배분을 사용했습니다."
            )
        if holiday:
            warnings.append("공휴일은 일요일/휴일 조사 패턴으로 대체했습니다.")
        if (date - cutoff).days > 90:
            warnings.append("자료 기준일에서 90일 이상 지난 조회입니다.")
        if following is None:
            warnings.append("다음 시간대 유효값이 없어 현재 시간대 패턴을 유지합니다.")
        latest = "2026" if line == 9 else "20260630"
        if p["last_period"] != latest or (
            following and following["last_period"] != latest
        ):
            warnings.append(
                "최신 조사값이 없는 시간대에 이전 조사 이력을 사용했습니다."
            )
        return {
            "model_version": self.artifact["version"],
            "prediction_kind": "unvalidated_car_scenario",
            "inference_mode": "on_request",
            "line": line,
            "service": service,
            "segment_id": seg["id"],
            "from_station": origin,
            "to_station": destination,
            "direction": seg["direction"],
            "requested_at": dt.isoformat(),
            "service_date": date.isoformat(),
            "daytype": daytype,
            "holiday": holiday,
            "time_bin": slot,
            "interpolation_fraction": round(fraction, 4),
            "train_mean_congestion_pct": round(base, 3),
            "car_count": count,
            "cars": [
                {
                    "car": c,
                    "estimated_congestion_pct": round(base * w[c - 1], 3),
                    "scenario_range_pct": [
                        round(min(base, base * high[c - 1]), 3),
                        round(max(base, base * high[c - 1]), 3),
                    ],
                }
                for c in range(1, count + 1)
            ],
            "location_features": loc,
            "scenario_strength": strength,
            "range_kind": "sensitivity_strength_0_to_0.3_not_confidence_interval",
            "evidence": {
                "available_after": cutoff.isoformat(),
                "profile_last_period": p["last_period"],
                "profile_snapshot_count": p["n"],
                "next_profile_last_period": following["last_period"]
                if following
                else None,
                "car_ground_truth_count": 0,
            },
            "warnings": warnings,
        }
