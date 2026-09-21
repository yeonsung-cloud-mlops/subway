"""Build supported transfer edges from collected official routing rows."""

import csv
import gzip
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def name(s):
    return re.sub(r"\([^)]*\)", "", s).strip()


def main():
    stations = json.loads((ROOT / "datasets/stations_all.json").read_text())
    lookup = {(str(s["line"]), s["name"]): s["id"] for s in stations}
    groups = defaultdict(list)
    with gzip.open(
        ROOT / "datasets/transfer_raw.csv.gz", "rt", encoding="utf-8-sig"
    ) as f:
        for r in csv.DictReader(f):
            a = lookup.get((r["환승시작 호선"], name(r["환승시작역"])))
            b = lookup.get((r["환승종료 호선"], name(r["환승종료역"])))
            if not a or not b or a == b or r["환승시작 호선"] == r["환승종료 호선"]:
                continue
            tm = r["소요시간"]
            minutes = None
            if re.fullmatch(r"\d+:\d{2}", tm or ""):
                mm, ss = map(int, tm.split(":"))
                minutes = mm + ss / 60
            groups[(a, b)].append((r["고유번호"], minutes))
    edges = []
    for (a, b), rows in sorted(groups.items()):
        values = [v for _, v in rows if v is not None and v > 0]
        edges.append(
            {
                "from_id": a,
                "to_id": b,
                "walking_minutes": round(sum(values) / len(values), 3)
                if values
                else 5.0,
                "time_basis": "mean_of_directional_source_routes"
                if values
                else "assumed_5_minutes",
                "source_route_ids": [x for x, _ in rows],
            }
        )
    # A detailed door/walking survey is not a complete interchange topology.
    supplement = json.loads(
        (ROOT / "datasets/transfer_connections_supplement.json").read_text()
    )
    known = {(e["from_id"], e["to_id"]) for e in edges}
    for connection in supplement["connections"]:
        ids = [
            lookup[(str(line), connection["station"])] for line in connection["lines"]
        ]
        for a, b in [ids, list(reversed(ids))]:
            if (a, b) not in known:
                edges.append(
                    {
                        "from_id": a,
                        "to_id": b,
                        "walking_minutes": supplement["walking_minutes_assumption"],
                        "time_basis": "assumed_5_minutes",
                        "connection_basis": "official_interchange_confirmation",
                        "connection_source_url": supplement["source_url"],
                        "source_route_ids": [],
                        "note": "환승 연결은 공식 확인, 보행시간 5분은 가정이며 문 위치 자료는 없습니다.",
                    }
                )
                known.add((a, b))
    edges.sort(key=lambda e: (e["from_id"], e["to_id"]))
    (ROOT / "datasets/transfers.json").write_text(
        json.dumps(edges, ensure_ascii=False, indent=2)
    )
    print("transfer edges", len(edges))


if __name__ == "__main__":
    main()
