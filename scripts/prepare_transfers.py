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
    (ROOT / "datasets/transfers.json").write_text(
        json.dumps(edges, ensure_ascii=False, indent=2)
    )
    print("transfer edges", len(edges))


if __name__ == "__main__":
    main()
