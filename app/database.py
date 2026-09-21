import csv
import gzip
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = """
CREATE TABLE IF NOT EXISTS stations (id TEXT PRIMARY KEY, line INTEGER NOT NULL, code INTEGER NOT NULL, name TEXT NOT NULL, details_json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS stations_line ON stations(line,name);
CREATE TABLE IF NOT EXISTS segments (id TEXT PRIMARY KEY, line INTEGER NOT NULL, from_id TEXT NOT NULL REFERENCES stations(id), to_id TEXT NOT NULL REFERENCES stations(id), details_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS transfers (from_id TEXT REFERENCES stations(id), to_id TEXT REFERENCES stations(id), details_json TEXT NOT NULL, PRIMARY KEY(from_id,to_id));
CREATE TABLE IF NOT EXISTS observations (line INTEGER, station INTEGER, direction TEXT, daytype TEXT, time TEXT, service TEXT, period TEXT, congestion REAL, source TEXT, PRIMARY KEY(line,station,direction,daytype,time,service,period));
CREATE TABLE IF NOT EXISTS raw_records (kind TEXT, source_file TEXT, row_number INTEGER, station_id TEXT, date TEXT, raw_json TEXT, PRIMARY KEY(kind,source_file,row_number));
CREATE INDEX IF NOT EXISTS raw_station_date ON raw_records(kind,station_id,date);
CREATE TABLE IF NOT EXISTS source_files (filename TEXT PRIMARY KEY, metadata_json TEXT NOT NULL, original_gzip BLOB);
CREATE TABLE IF NOT EXISTS seed_versions (name TEXT PRIMARY KEY, sha256 TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS predictions (id INTEGER PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP, result_json TEXT NOT NULL);
"""


@contextmanager
def connect(path):
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def seed_database(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    files = [
        "transfers.json",
        "stations_all.json",
        "segments_all.json",
        "observations.csv.gz",
        "sources_all.json",
        "transfer_raw.csv.gz",
        "facilities_raw.csv.gz",
    ]
    fingerprint = hashlib.sha256(
        b"".join((ROOT / "datasets" / f).read_bytes() for f in files)
    ).hexdigest()
    with connect(path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        row = conn.execute(
            "SELECT sha256 FROM seed_versions WHERE name=?", ("all_lines",)
        ).fetchone()
        if row and row["sha256"] == fingerprint:
            return
        conn.execute("DELETE FROM transfers")
        conn.execute("DELETE FROM segments")
        conn.execute("DELETE FROM stations")
        conn.execute("DELETE FROM observations")
        for s in json.loads((ROOT / "datasets/stations_all.json").read_text()):
            conn.execute(
                "INSERT INTO stations VALUES (?,?,?,?,?)",
                (
                    s["id"],
                    s["line"],
                    s["code"],
                    s["name"],
                    json.dumps(s, ensure_ascii=False),
                ),
            )
        for s in json.loads((ROOT / "datasets/segments_all.json").read_text()):
            conn.execute(
                "INSERT INTO segments VALUES (?,?,?,?,?)",
                (
                    s["id"],
                    s["line"],
                    s["from_id"],
                    s["to_id"],
                    json.dumps(s, ensure_ascii=False),
                ),
            )

        for t in json.loads((ROOT / "datasets/transfers.json").read_text()):
            conn.execute(
                "INSERT INTO transfers VALUES (?,?,?)",
                (t["from_id"], t["to_id"], json.dumps(t, ensure_ascii=False)),
            )

        def obs():
            with gzip.open(ROOT / "datasets/observations.csv.gz", "rt") as f:
                for r in csv.DictReader(f):
                    yield (
                        int(r["line"]),
                        int(r["station"]),
                        r["direction"],
                        r["daytype"],
                        r["time"],
                        r["service"],
                        r["period"],
                        float(r["congestion"]) if r["congestion"] else None,
                        r["source"],
                    )

        conn.executemany("INSERT INTO observations VALUES (?,?,?,?,?,?,?,?,?)", obs())
        for s in json.loads((ROOT / "datasets/sources_all.json").read_text()):
            conn.execute(
                "INSERT INTO source_files(filename,metadata_json) VALUES (?,?) ON CONFLICT(filename) DO UPDATE SET metadata_json=excluded.metadata_json",
                (s["filename"], json.dumps(s, ensure_ascii=False)),
            )
        for kind, name in [
            ("transfer", "transfer_raw.csv.gz"),
            ("facility", "facilities_raw.csv.gz"),
        ]:
            conn.execute("DELETE FROM raw_records WHERE kind=?", (kind,))
            with gzip.open(ROOT / "datasets" / name, "rt", encoding="utf-8-sig") as f:
                conn.executemany(
                    "INSERT INTO raw_records VALUES (?,?,?,?,?,?)",
                    (
                        (kind, name, i, None, None, json.dumps(r, ensure_ascii=False))
                        for i, r in enumerate(csv.DictReader(f), 1)
                    ),
                )
        conn.execute(
            "INSERT OR REPLACE INTO seed_versions VALUES (?,?)",
            ("all_lines", fingerprint),
        )
