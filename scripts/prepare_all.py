"""Compile all collected official metro sources without creating car labels."""

import gzip
import hashlib
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "datasets"


def norm(v):
    s = re.sub(r"\([^)]*\)", "", str(v)).strip()
    return {"서울": "서울역", "당고개": "불암산", "뚝섬유원지": "자양"}.get(s, s)


def dump(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2))


def main():
    src = ROOT / "data_review/raw"
    extra = ROOT / "metro_expansion/raw"
    addr = pd.read_csv(next(extra.glob("*역주소*.csv")), encoding="cp949")
    geo = pd.read_csv(src / "stations.csv", encoding="cp949")
    geo["name"] = geo["역사명"].map(norm)
    latest = pd.read_excel(src / "서울교통공사_지하철혼잡도정보_20260630.xlsx")
    stations = {}
    for _, r in latest.iterrows():
        code = int(r["역번호"])
        line = int(str(r["호선"])[0])
        key = f"{line}:{code}"
        if code >= 9000:
            continue
        stations[key] = {"id": key, "code": code, "line": line, "name": norm(r["역명"])}
    ninefile = next(extra.glob("2026*.xlsx"))
    nine = pd.read_excel(ninefile, header=1)
    for i, name in enumerate(nine.iloc[:, 0]):
        key = f"9:{4101 + i}"
        stations[key] = {"id": key, "code": 4101 + i, "line": 9, "name": norm(name)}
    for st in stations.values():
        a = addr[(addr["호선"] == st["line"]) & addr["역번호"].eq(st["code"])]
        g = geo[
            geo["name"].eq(st["name"])
            & geo["호선"]
            .astype(str)
            .isin(
                [f"{st['line']}호선", "9호선(연장)" if st["line"] == 9 else "INVALID"]
            )
        ]
        st.update(
            address=a.iloc[0]["도로명주소"] if len(a) else None,
            phone=a.iloc[0]["역전화번호"] if len(a) else None,
            latitude=float(g.iloc[0]["위도"]) if len(g) == 1 else None,
            longitude=float(g.iloc[0]["경도"]) if len(g) == 1 else None,
            operator="서울교통공사"
            if st["line"] < 9 or st["code"] >= 4126
            else "서울시메트로9호선",
        )
    segments = []

    def route(
        line,
        codes,
        forward,
        cars,
        service="일반",
        circle=False,
        oneway=False,
        profile_override=None,
    ):
        pairs = list(zip(codes, codes[1:]))
        pairs += [(codes[-1], codes[0])] if circle else []
        reverse = {"상선": "하선", "하선": "상선", "내선": "외선", "외선": "내선"}[
            forward
        ]
        for a, b in pairs:
            for u, v, d in [(a, b, forward)] + ([] if oneway else [(b, a, reverse)]):
                profile = (profile_override or {}).get((u, v), u)
                segments.append(
                    {
                        "id": f"{line}:{u}:{v}:{service}",
                        "line": line,
                        "from_id": f"{line}:{u}",
                        "to_id": f"{line}:{v}",
                        "from_station": stations[f"{line}:{u}"]["name"],
                        "to_station": stations[f"{line}:{v}"]["name"],
                        "direction": d,
                        "service": service,
                        "profile_station": profile,
                        "car_count": cars,
                    }
                )

    route(1, [150, 151, 152, 153, 154, 155, 159, 156, 157, 158], "상선", 10)
    route(2, list(range(201, 244)), "내선", 10, circle=True)
    route(2, [211, 244, 245, 250, 246], "외선", 4, profile_override={(211, 244): 9002})
    route(2, [234, 247, 248, 249, 260], "내선", 6, profile_override={(234, 247): 9003})
    route(3, list(range(309, 343)), "하선", 10)
    route(4, list(range(409, 435)), "하선", 10)
    route(5, list(range(2511, 2555)) + list(range(2562, 2567)), "하선", 8)
    route(
        5,
        [2549] + list(range(2555, 2562)),
        "하선",
        8,
        profile_override={(2549, 2555): 9005},
    )
    route(
        6,
        [2611, 2612, 2613, 2614, 2615, 2616],
        "하선",
        8,
        circle=True,
        oneway=True,
        profile_override={(2611, 2612): 9006},
    )
    route(6, [2611] + list(range(2617, 2650)), "하선", 8)
    route(7, list(range(2711, 2753)), "하선", 8)
    route(8, list(range(2810, 2822)) + [2828] + list(range(2822, 2828)), "하선", 6)
    route(9, list(range(4101, 4139)), "상선", 6)
    express = (
        pd.read_excel(ninefile, sheet_name="상선급행(평일)", header=1)
        .iloc[:, 0]
        .map(norm)
    )
    byname = {s["name"]: s["code"] for s in stations.values() if s["line"] == 9}
    route(9, [byname[n] for n in express], "상선", 6, service="급행")
    t = pd.read_csv(
        ROOT / "car_congestion_review/results/transfer_routes_clean.csv", dtype=str
    )
    e = pd.read_csv(
        ROOT / "car_congestion_review/results/escalators_clean.csv", dtype=str
    )
    e9 = pd.read_csv(
        ROOT / "car_congestion_review/results/line9_escalators_clean.csv", dtype=str
    )
    t["station_name"] = t["환승종료역"].map(norm)
    e["station_name"] = e["station_name"].map(norm)
    for seg in segments:
        line = str(seg["line"])
        name = seg["from_station"]
        to = seg["to_station"]
        count = seg["car_count"]
        # Express platform directions are named by neighboring local station, not next express stop.
        if seg["line"] == 9 and seg["service"] == "급행":
            step = 1 if seg["direction"] == "상선" else -1
            to = stations[f"9:{int(seg['from_id'].split(':')[1]) + step}"]["name"]
        rows = t[
            t["환승종료 호선"].eq(line)
            & t.station_name.eq(name)
            & t["환승 열차 방면"].eq(to + " 방면")
        ]
        board = sorted(
            {
                int(v)
                for v in rows["환승 승차위치(호차)"]
                if str(v).isdigit() and 1 <= int(v) <= count
            }
        )
        loc = (
            e[e["호선"].eq(line) & e.station_name.eq(name)]["설치위치"]
            .dropna()
            .tolist()
        )
        if line == "9":
            n = e9[e9["역명"].map(norm).eq(name)]
            if len(n):
                loc += (
                    n[["시작층(상세위치)", "종료층(상세위치)", "설치위치"]]
                    .fillna("")
                    .agg(" ".join, axis=1)
                    .tolist()
                )
        access = sorted(
            {
                int(m.group(1))
                for v in loc
                if to + " 방면" in v
                for m in re.finditer(r"(?<!\d)(\d{1,2})\s*-\s*[1-4](?!\d)", v)
                if 1 <= int(m.group(1)) <= count
            }
        )
        seg["locations"] = {"transfer_board_cars": board, "access_cars": access}
    d = pd.read_csv(ROOT / "data_review/metro_results/congestion_long.csv.gz")
    d["time"] = d.time.replace({"00:00": "24:00", "00:30": "24:30"})
    d["service"] = "일반"
    d["source"] = "OA-12928"
    d["period"] = d.period.astype(str)
    rows = []
    for p in sorted(extra.glob("202*.xlsx")):
        year = p.name[:4]
        for sh in pd.ExcelFile(p).sheet_names:
            frame = pd.read_excel(p, sheet_name=sh, header=1)
            for _, r in frame.iterrows():
                for c in frame.columns[1:]:
                    tm = str(c).split("~")[0]
                    tm = {"00:00": "24:00", "00:30": "24:30"}.get(tm, tm)
                    if not re.fullmatch(r"\d\d:\d\d", tm):
                        continue
                    rows.append(
                        {
                            "station": byname[norm(r.iloc[0])],
                            "line": 9,
                            "direction": sh[:2],
                            "daytype": "平日" if "평일" in sh else "휴일",
                            "time": tm,
                            "congestion": pd.to_numeric(r[c], errors="coerce"),
                            "period": year,
                            "service": "급행" if "급행" in sh else "일반",
                            "source": "OA-22197",
                        }
                    )
    n = pd.DataFrame(rows)
    n["daytype"] = n.daytype.replace({"平日": "평일"})
    d = pd.concat([d, n], ignore_index=True)
    d = d.sort_values(
        ["line", "period", "station", "direction", "service", "daytype", "time"]
    )
    assert not d.duplicated(
        ["line", "period", "station", "direction", "service", "daytype", "time"]
    ).any()
    d.to_csv(
        OUT / "observations.csv.gz",
        index=False,
        compression={"method": "gzip", "mtime": 0},
    )
    dump("stations_all.json", list(stations.values()))
    dump("segments_all.json", segments)
    # All original source cells of transfer and facility rows remain inspectable in SQLite.
    for filename, frame in [
        (
            "transfer_raw.csv.gz",
            pd.read_csv(
                ROOT
                / "car_congestion_review/raw/서울교통공사_수도권 도시철도 환승 데이터_20250317.csv",
                encoding="cp949",
                dtype=str,
            ),
        ),
        ("facilities_raw.csv.gz", e),
    ]:
        frame.to_csv(
            OUT / filename, index=False, compression={"method": "gzip", "mtime": 0}
        )
    manifests = []
    for p in [
        "data_review/manifest.json",
        "car_congestion_review/manifest.json",
        "metro_expansion/manifest.json",
    ]:
        manifests += json.loads((ROOT / p).read_text())
    used = [
        x
        for x in manifests
        if x["dataset"]
        in [
            "OA-12928",
            "OA-12921",
            "OA-22521",
            "OA-22486",
            "OA-22443",
            "OA-22197",
            "OA-12035",
            "OA-12034",
        ]
    ]
    master = src / "stations.csv"
    (OUT / "station_master.csv.gz").write_bytes(
        gzip.compress(master.read_bytes(), mtime=0)
    )
    used.append(
        {
            "dataset": "OA-21232",
            "filename": "stations.csv",
            "page": "https://data.seoul.go.kr/dataList/OA-21232/S/1/datasetView.do",
            "bytes": master.stat().st_size,
            "sha256": hashlib.sha256(master.read_bytes()).hexdigest(),
            "bundled_gzip": "station_master.csv.gz",
        }
    )
    dump("sources_all.json", used)
    audit = {
        "stations": len(stations),
        "segments": len(segments),
        "observations": len(d),
        "line9_observations": len(n),
        "stations_with_address": sum(
            s["address"] is not None for s in stations.values()
        ),
        "stations_with_coordinates": sum(
            s["latitude"] is not None for s in stations.values()
        ),
        "by_line": {
            str(line_number): {
                "stations": sum(s["line"] == line_number for s in stations.values()),
                "segments": sum(s["line"] == line_number for s in segments),
                "observations": int(d.line.eq(line_number).sum()),
            }
            for line_number in range(1, 10)
        },
    }
    dump("coverage.json", audit)
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
