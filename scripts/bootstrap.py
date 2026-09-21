"""Load originals and source cells into SQLite; download missing originals with --download."""

import argparse
import csv
import gzip
import hashlib
import json
import re
import subprocess
from pathlib import Path

from app.database import ROOT, connect, seed_database
from app.enrichment import seed_enrichment


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(ROOT / "var/subway.sqlite3"))
    p.add_argument("--download", action="store_true")
    p.add_argument("--skip-originals", action="store_true")
    args = p.parse_args()
    seed_database(args.db)
    seed_enrichment(args.db)
    if not args.skip_originals:
        roots = [
            ROOT / "data_review/raw",
            ROOT / "car_congestion_review/raw",
            ROOT / "metro_expansion/raw",
            ROOT / "journey_enrichment/raw",
            ROOT / "var/downloads",
        ]
        roots[-1].mkdir(parents=True, exist_ok=True)
        for s in json.loads(
            (ROOT / "datasets/sources_all.json").read_text()
        ) + json.loads((ROOT / "datasets/enrichment_sources.json").read_text()):
            filename = s["filename"]
            source = next(
                (r / filename for r in roots if (r / filename).exists()), None
            )
            if source is None and s.get("bundled_gzip"):
                source = roots[-1] / filename
                source.write_bytes(
                    gzip.decompress(
                        (ROOT / "datasets" / s["bundled_gzip"]).read_bytes()
                    )
                )
            if source is None and args.download:
                source = roots[-1] / Path(filename).name
                subprocess.run(
                    [
                        "curl",
                        "-fsSL",
                        "--retry",
                        "2",
                        "--max-time",
                        "180",
                        "-d",
                        f"infId={s['dataset']}&seq={s['seq']}&infSeq={s.get('infSeq', '1')}",
                        s.get("url") or s["download_url"],
                        "-o",
                        str(source),
                    ],
                    check=True,
                )
            if source is None:
                raise SystemExit(
                    f"Missing original {filename}. Re-run with --download."
                )
            blob = source.read_bytes()
            if hashlib.sha256(blob).hexdigest() != s["sha256"]:
                raise SystemExit(
                    f"Source hash changed: {filename}; review source version before import."
                )
            with connect(args.db) as conn:
                old = conn.execute(
                    "SELECT original_gzip IS NOT NULL AS loaded FROM source_files WHERE filename=?",
                    (filename,),
                ).fetchone()
                if old and old["loaded"]:
                    continue
                conn.execute(
                    "UPDATE source_files SET original_gzip=? WHERE filename=?",
                    (gzip.compress(blob, mtime=0), filename),
                )
                if s["dataset"] == "OA-12921":
                    # Preserve original wide hourly cells instead of expanding ~12 million hourly rows.
                    with source.open(encoding="cp949", newline="") as f:

                        def records():
                            for i, r in enumerate(csv.DictReader(f), 1):
                                date = r.get("수송일자") or r.get("날짜")
                                code = r.get("역번호")
                                line = r.get("호선")
                                if not date or not code or not line:
                                    continue
                                line = int(re.search(r"\d+", line)[0])
                                station_id = f"{line}:{int(float(code))}"
                                yield (
                                    "ridership",
                                    filename,
                                    i,
                                    station_id,
                                    date,
                                    json.dumps(r, ensure_ascii=False),
                                )

                        conn.executemany(
                            "INSERT OR REPLACE INTO raw_records VALUES (?,?,?,?,?,?)",
                            records(),
                        )
            print("Imported", filename, flush=True)
    with connect(args.db) as conn:
        report = {
            t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            for t in [
                "stations",
                "segments",
                "observations",
                "source_files",
                "raw_records",
            ]
        }
        report["ridership_records"] = conn.execute(
            "SELECT count(*) FROM raw_records WHERE kind='ridership'"
        ).fetchone()[0]
        report["original_files_loaded"] = conn.execute(
            "SELECT count(*) FROM source_files WHERE original_gzip IS NOT NULL"
        ).fetchone()[0]
        report["database_bytes"] = Path(args.db).stat().st_size
    print(json.dumps(report, indent=2))
    (ROOT / "artifacts/database_report.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
