"""Station amenities and direction-specific boarding/alighting door advice."""

import csv
import gzip
import hashlib
import json
import re

from app.database import ROOT, connect


def seed_enrichment(path):
    files = [
        "amenities.json",
        "access_doors.json",
        "timetable.csv.gz",
        "enrichment_sources.json",
    ]
    digest = hashlib.sha256(
        b"".join((ROOT / "datasets" / f).read_bytes() for f in files)
    ).hexdigest()
    with connect(path) as conn:
        conn.executescript("""
CREATE TABLE IF NOT EXISTS amenities(station_id TEXT PRIMARY KEY, details_json TEXT);
CREATE TABLE IF NOT EXISTS access_doors(station_id TEXT PRIMARY KEY, details_json TEXT);
CREATE TABLE IF NOT EXISTS timetable_stops(trip_id TEXT, station_id TEXT, line INTEGER, week TEXT, service TEXT, train_no TEXT, arrival_seconds INTEGER, departure_seconds INTEGER, source_row INTEGER, destination TEXT);
CREATE INDEX IF NOT EXISTS timetable_boarding ON timetable_stops(station_id,week,service,departure_seconds);
CREATE INDEX IF NOT EXISTS timetable_trip ON timetable_stops(trip_id,arrival_seconds,departure_seconds);
""")
        old = conn.execute(
            "SELECT sha256 FROM seed_versions WHERE name='enrichment'"
        ).fetchone()
        if old and old[0] == digest:
            return
        for table, filename in [
            ("amenities", "amenities.json"),
            ("access_doors", "access_doors.json"),
        ]:
            conn.execute(f"DELETE FROM {table}")
            conn.executemany(
                f"INSERT INTO {table} VALUES (?,?)",
                (
                    (key, json.dumps(value, ensure_ascii=False))
                    for key, value in json.loads(
                        (ROOT / "datasets" / filename).read_text()
                    ).items()
                ),
            )
        conn.execute("DELETE FROM timetable_stops")
        with gzip.open(ROOT / "datasets/timetable.csv.gz", "rt", encoding="utf8") as f:
            conn.executemany(
                "INSERT INTO timetable_stops VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    (
                        r["trip_id"],
                        r["station_id"],
                        int(r["line"]),
                        r["week"],
                        r["service"],
                        r["train_no"],
                        int(r["arrival_seconds"]) if r["arrival_seconds"] else None,
                        int(r["departure_seconds"]) if r["departure_seconds"] else None,
                        int(r["source_row"]),
                        r["destination"],
                    )
                    for r in csv.DictReader(f)
                ),
            )
        for s in json.loads((ROOT / "datasets/enrichment_sources.json").read_text()):
            conn.execute(
                "INSERT INTO source_files(filename,metadata_json) VALUES (?,?) ON CONFLICT(filename) DO UPDATE SET metadata_json=excluded.metadata_json",
                (s["filename"], json.dumps(s, ensure_ascii=False)),
            )
        conn.execute(
            "INSERT OR REPLACE INTO seed_versions VALUES (?,?)", ("enrichment", digest)
        )


def norm(s):
    s = re.sub(r"\([^)]*\)", "", str(s)).strip()
    return {"당고개": "불암산", "뚝섬유원지": "자양"}.get(s, s)


class Guidance:
    def __init__(self, model):
        self.model = model
        with connect(model.db_path) as conn:
            self.amenities = {
                r[0]: json.loads(r[1]) for r in conn.execute("SELECT * FROM amenities")
            }
            self.access = {
                r[0]: json.loads(r[1])
                for r in conn.execute("SELECT * FROM access_doors")
            }
            self.routes = [
                json.loads(r[0])
                for r in conn.execute(
                    "SELECT raw_json FROM raw_records WHERE kind='transfer'"
                )
            ]

    def directions(self, segment, station_id):
        # Direction must continue through the transfer/alighting station. Never substitute the opposite platform.
        return {
            s["to_station"]
            for s in self.model.segments(segment["line"])
            if s["from_id"] == station_id
            and s["direction"] == segment["direction"]
            and s["service"] == "일반"
            and s["car_count"] == segment["car_count"]
        }

    def access_advice(self, segment, station_id):
        names = self.directions(segment, station_id)
        points = [
            r
            for r in self.access.get(station_id, [])
            if r["toward_station"] in names and r["car"] <= segment["car_count"]
        ]
        return {
            "status": "available" if points else "unavailable",
            "kind": "escalator_nearby_doors",
            "points": points,
            "note": "승강장 연결 에스컬레이터 인접 문입니다. 특정 출구까지 최단 하차 위치를 보장하지 않습니다.",
            "source": "OA-22486 / OA-22443",
            "as_of": "2026-02-11 / 2026-01-31",
        }

    def transfer_advice(self, before, after, transfer):
        a, b = transfer["from_id"], transfer["to_id"]
        incoming = self.directions(before, a)
        outgoing = self.directions(after, b)
        rows = []
        for r in self.routes:
            if r["환승시작 호선"] != str(before["line"]) or r["환승종료 호선"] != str(
                after["line"]
            ):
                continue
            if (
                norm(r["환승시작역"]) != before["to_station"]
                or norm(r["환승종료역"]) != after["from_station"]
            ):
                continue
            if (
                r["하차 열차 방면"].replace(" 방면", "") not in incoming
                or r["환승 열차 방면"].replace(" 방면", "") not in outgoing
            ):
                continue

            def position(car, door, count):
                if (
                    car.isdigit()
                    and door.isdigit()
                    and 1 <= int(car) <= count
                    and 1 <= int(door) <= 4
                ):
                    return {
                        "car": int(car),
                        "door": int(door),
                        "label": f"{car}호차 {door}번 문",
                    }
                return {"car": None, "door": None, "label": f"{car} / {door}"}

            rows.append(
                {
                    "source_route_id": r["고유번호"],
                    "alight": position(
                        r["하차위치(호차)"], r["하차위치(문)"], before["car_count"]
                    ),
                    "board": position(
                        r["환승 승차위치(호차)"],
                        r["환승 승차위치(문)"],
                        after["car_count"],
                    ),
                    "from_direction": r["하차 열차 방면"],
                    "to_direction": r["환승 열차 방면"],
                    "walking_time": r.get("소요시간"),
                }
            )
        return {
            "status": "available" if rows else "unavailable",
            "routes": rows,
            "source": "OA-22521",
            "as_of": "2025-03-17",
            "note": "진행 방면이 일치하는 공식 환승 승하차 문 위치입니다."
            if rows
            else "이 경로의 양쪽 진행 방면이 일치하는 문 위치를 확보하지 못했습니다.",
        }

    def attach(self, result):
        rides = [s for s in result["steps"] if s["kind"] == "ride"]
        if not rides:
            return

        def segment(step):
            return self.model._lookup[
                (
                    step["line"],
                    step["from_station"],
                    step["to_station"],
                    step["service"],
                )
            ]

        first, last = segment(rides[0]), segment(rides[-1])
        a, b = first["from_id"], last["to_id"]
        result["endpoint_facilities"] = {
            "departure": self.amenities[a],
            "arrival": self.amenities[result.get("arrival_station_id", b)],
        }
        result["departure_boarding_guidance"] = self.access_advice(first, a)
        result["arrival_alighting_guidance"] = self.access_advice(last, b)
        for i, step in enumerate(result["steps"]):
            if step["kind"] != "transfer":
                continue
            before = next(
                (s for s in reversed(result["steps"][:i]) if s["kind"] == "ride"), None
            )
            after = next(
                (s for s in result["steps"][i + 1 :] if s["kind"] == "ride"), None
            )
            step["door_guidance"] = (
                self.transfer_advice(segment(before), segment(after), step)
                if before and after
                else {
                    "status": "unavailable",
                    "routes": [],
                    "note": "환승 전후 탑승 구간이 없어 방면을 확정할 수 없습니다.",
                }
            )

    def allocation_features(self, edges):
        """Direction-filtered access/transfer attraction, shared within each actual train leg."""
        result = {}
        i = 0
        while i < len(edges):
            if edges[i]["kind"] != "ride":
                i += 1
                continue
            j = i + 1
            while (
                j < len(edges)
                and edges[j]["kind"] == "ride"
                and not edges[j].get("train_change_wait_minutes")
            ):
                j += 1
            first, last = edges[i]["segment"], edges[j - 1]["segment"]
            board = self.access_advice(first, first["from_id"])
            alight = self.access_advice(last, last["to_id"])
            incoming, outgoing = [], []
            if (
                i >= 2
                and edges[i - 1]["kind"] == "transfer"
                and edges[i - 2]["kind"] == "ride"
            ):
                incoming = self.transfer_advice(
                    edges[i - 2]["segment"], first, edges[i - 1]["transfer"]
                )["routes"]
            if (
                j + 1 < len(edges)
                and edges[j]["kind"] == "transfer"
                and edges[j + 1]["kind"] == "ride"
            ):
                outgoing = self.transfer_advice(
                    last, edges[j + 1]["segment"], edges[j]["transfer"]
                )["routes"]
            features = {
                "access_cars": sorted({p["car"] for p in board["points"]}),
                "destination_access_cars": sorted({p["car"] for p in alight["points"]}),
                "transfer_board_cars": sorted(
                    {r["board"]["car"] for r in incoming if r["board"]["car"]}
                ),
                "transfer_alight_cars": sorted(
                    {r["alight"]["car"] for r in outgoing if r["alight"]["car"]}
                ),
                "boarding_door_points": board["points"],
                "alighting_door_points": alight["points"],
                "incoming_transfer_routes": incoming,
                "outgoing_transfer_routes": outgoing,
                "exit_mapping_status": "unavailable_escalator_access_proxy_only",
                "allocation_basis": "route_conditioned_door_attraction_scenario",
                "note": "각 탑승 구간의 출입 접근·환승 문 인접 칸 선호 가정입니다. 특정 출구별 최단 문 매핑과 실제 승객 OD 비율은 없으며, 계수는 학습되지 않았습니다.",
            }
            for index in range(i, j):
                result[index] = features
            i = j
        return result
