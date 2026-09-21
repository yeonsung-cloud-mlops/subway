"""Export a small, attributed training subset from locally collected official files."""

import hashlib
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main():
    out = ROOT / "datasets"
    out.mkdir(exist_ok=True)
    src = ROOT / "data_review/metro_results/congestion_long.csv.gz"
    d = pd.read_csv(src)
    d = d[
        d.line.eq(2) & d.station.between(201, 243) & d.direction.isin(["내선", "외선"])
    ].copy()
    # Official 24:00/24:30 notation belongs to the preceding service day.
    d["time"] = d.time.replace({"00:00": "24:00", "00:30": "24:30"})
    assert not d.duplicated(["period", "station", "direction", "daytype", "time"]).any()
    d.sort_values(["period", "station", "direction", "daytype", "time"]).to_csv(
        out / "congestion.csv.gz",
        index=False,
        compression={"method": "gzip", "mtime": 0},
    )
    s = pd.read_csv(ROOT / "data_review/metro_results/station_dong_mapping.csv")
    s = s[s.line.eq(2) & s.station.between(201, 243)].sort_values("station")
    stations = [
        {"id": int(r.station), "name": re.sub(r"\([^)]*\)", "", r["name"]).strip()}
        for _, r in s.iterrows()
    ]
    assert len(stations) == 43
    (out / "stations.json").write_text(
        json.dumps(stations, ensure_ascii=False, indent=2)
    )
    t = pd.read_csv(
        ROOT / "car_congestion_review/results/transfer_routes_clean.csv", dtype=str
    )
    e = pd.read_csv(ROOT / "car_congestion_review/results/escalators_clean.csv")
    features = {}
    for i, st in enumerate(stations):
        for step, direction in [(1, "내선"), (-1, "외선")]:
            nxt = stations[(i + step) % 43]["name"]
            key = f"{st['id']}|{direction}"
            rows = t[
                (t["환승종료 호선"] == "2")
                & (t["환승종료역"] == st["name"])
                & (t["환승 열차 방면"] == nxt + " 방면")
            ]
            board = sorted(
                {
                    int(v)
                    for v in rows["환승 승차위치(호차)"]
                    if v.isdigit() and 1 <= int(v) <= 10
                }
            )
            loc = (
                e[e["호선"].astype(str).eq("2") & e.station_name.eq(st["name"])][
                    "설치위치"
                ]
                .dropna()
                .astype(str)
            )
            # Use explicit matching next-station direction only; ambiguous locations are excluded.
            access = sorted(
                {
                    int(m.group(1))
                    for v in loc
                    if nxt + " 방면" in v
                    for m in re.finditer(r"(?<!\d)(\d{1,2})\s*-\s*[1-4](?!\d)", v)
                    if 1 <= int(m.group(1)) <= 10
                }
            )
            features[key] = {"transfer_board_cars": board, "access_cars": access}
    (out / "locations.json").write_text(
        json.dumps(features, ensure_ascii=False, indent=2)
    )
    manifests = []
    for p in ["data_review/manifest.json", "car_congestion_review/manifest.json"]:
        manifests.extend(json.loads((ROOT / p).read_text()))
    sources = [
        x for x in manifests if x["dataset"] in ["OA-12928", "OA-22521", "OA-22486"]
    ]
    provenance = {
        "collected_on": "2026-09-21",
        "scope": "2호선 본선 43역, 지선 및 9001~9003 특수 코드 제외",
        "sources": sources,
        "derived_files": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(out.iterdir())
            if p.name != "provenance.json"
        },
    }
    (out / "provenance.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2)
    )
    print(
        {
            "rows": len(d),
            "positive": int(d.congestion.gt(0).sum()),
            "stations": len(stations),
            "direction_features": sum(
                bool(v["transfer_board_cars"] or v["access_cars"])
                for v in features.values()
            ),
        }
    )


if __name__ == "__main__":
    main()
