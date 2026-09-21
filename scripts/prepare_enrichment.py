"""Normalize downloaded timetable and station facility files; retain source snapshots."""

import csv
import gzip
import hashlib
import io
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "datasets"


def read(p):
    blob = p.read_bytes()
    try:
        text = blob.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = blob.decode("cp949")
    return list(csv.DictReader(io.StringIO(text)))


def norm(v):
    s = re.sub(r"\([^)]*\)", "", v).strip()
    s = s[:-1] if s.endswith("역") and s != "서울역" else s
    return {"당고개": "불암산", "뚝섬유원지": "자양", "서울": "서울역"}.get(s, s)


def seconds(v):
    if not re.fullmatch(r"\d{2}:\d{2}:\d{2}", v or ""):
        return None
    h, m, s = map(int, v.split(":"))
    return (
        h * 3600 + m * 60 + s
        if h <= 26 and m < 60 and s < 60 and h * 3600 + m * 60 + s > 0
        else None
    )


def main():
    raw = ROOT / "journey_enrichment/raw"
    stations = json.loads((OUT / "stations_all.json").read_text())
    lookup = {(s["line"], s["name"]): s["id"] for s in stations}
    amenities = {
        s["id"]: {
            "station_id": s["id"],
            "station_name": s["name"],
            "line": s["line"],
            "status": "unavailable",
            "as_of": "2025-03-20",
            "features": {},
            "nursing_rooms": [],
        }
        for s in stations
    }
    for r in read(next(raw.glob("*편의시설*.csv"))):
        key = lookup.get((int(re.search(r"\d+", r["호선"])[0]), norm(r["역명"])))
        if key:
            amenities[key].update(
                status="available",
                features={
                    k.removesuffix("여부"): True
                    if v == "Y"
                    else False
                    if v == "N"
                    else None
                    for k, v in r.items()
                    if k.endswith("여부")
                },
            )
    for r in read(next(raw.glob("*수유실*.csv"))):
        key = lookup.get((int(re.search(r"\d+", r["호선"])[0]), norm(r["역명"])))
        if key:
            amenities[key]["nursing_rooms"].append(
                {
                    "location": r["상세위치"],
                    "fare_area": r["운임 비운임"],
                    "type": r["시설구분"],
                    "as_of": "2025-09-24",
                }
            )
    (OUT / "amenities.json").write_text(
        json.dumps(amenities, ensure_ascii=False, indent=2)
    )
    records = read(next(raw.glob("*시각표*.csv")))
    counts = Counter()
    stops = []
    seen = set()
    for r in records:
        counts["source_rows"] += 1
        line = int(r["LINE"])
        sid = lookup.get((line, norm(r["STATION_NM"])))
        if not sid:
            counts["outside_scope"] += 1
            continue
        if r["WEEKTAG"] not in ["DAY", "SAT", "END"]:
            counts["unknown_weekday"] += 1
            continue
        arr, dep = seconds(r["STT"]), seconds(r["EDT"])
        if arr is None and dep is None:
            counts["no_valid_time"] += 1
            continue
        trip = "|".join(
            [
                str(line),
                r["WEEKTAG"],
                r["TRAIN_NO"],
                r["GUBHANG"],
                r["INOUTTAG"],
                r["ST_STT_NM"],
                r["ED_STT_NM"],
            ]
        )
        key = (trip, sid, arr, dep)
        if key in seen:
            counts["duplicates"] += 1
            continue
        seen.add(key)
        stops.append(
            {
                "trip_id": trip,
                "station_id": sid,
                "line": line,
                "week": r["WEEKTAG"],
                "service": "급행" if r["GUBHANG"] == "1" else "일반",
                "train_no": r["TRAIN_NO"],
                "arrival_seconds": arr,
                "departure_seconds": dep,
                "source_row": r["ROWNUM"],
                "destination": r["ED_STT_NM"],
            }
        )
    with gzip.open(OUT / "timetable.csv.gz", "wt", encoding="utf8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(stops[0]))
        writer.writeheader()
        writer.writerows(stops)
    counts["imported_stops"] = len(stops)
    counts["trips"] = len({r["trip_id"] for r in stops})
    counts["amenity_stations"] = sum(
        r["status"] == "available" for r in amenities.values()
    )
    # Facility door points from existing raw data, only explicit directed locations.
    with gzip.open(OUT / "facilities_raw.csv.gz", "rt", encoding="utf-8-sig") as f:
        access = list(csv.DictReader(f))
    p = (
        ROOT
        / "car_congestion_review/raw/서울교통공사_9호선2_3단계 에스컬레이터 설치현황_20260131.CSV"
    )
    for r in read(p):
        access.append(
            {
                "호선": "9",
                "station_name": norm(r["역명"]),
                "설치위치": " ".join(
                    r.get(k, "")
                    for k in ["시작층(상세위치)", "종료층(상세위치)", "설치위치"]
                ),
            }
        )
    points = defaultdict(list)
    for r in access:
        if not r["호선"].isdigit():
            continue
        key = lookup.get(
            (int(r["호선"]), norm(r.get("station_name") or r.get("역명", "")))
        )
        if not key:
            continue
        text = r.get("설치위치", "")
        for m in re.finditer(
            r"([가-힣0-9]+)\s*방면\s*(\d{1,2})\s*-\s*([1-4])(?!\d)", text
        ):
            entry = {
                "toward_station": norm(m[1]),
                "car": int(m[2]),
                "door": int(m[3]),
                "facility": "에스컬레이터",
                "location_text": text,
            }
            if entry not in points[key]:
                points[key].append(entry)
    (OUT / "access_doors.json").write_text(
        json.dumps(points, ensure_ascii=False, indent=2)
    )
    sources = json.loads((ROOT / "journey_enrichment/manifest.json").read_text())
    (OUT / "enrichment_sources.json").write_text(
        json.dumps(sources, ensure_ascii=False, indent=2)
    )
    report = {
        "checked_on": "2026-09-21",
        "timetable_as_of": "2025-09-30",
        "current_service_verified": False,
        **dict(counts),
        "by_line": dict(Counter(r["line"] for r in stops)),
        "sha256": {
            name: hashlib.sha256((OUT / name).read_bytes()).hexdigest()
            for name in ["timetable.csv.gz", "amenities.json", "access_doors.json"]
        },
    }
    (OUT / "enrichment_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2)
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
