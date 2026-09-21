import json
import os
from contextlib import asynccontextmanager
from datetime import date, datetime, time
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.database import connect
from app.journey import JourneyModel
from app.model import Model, PredictionError

ROOT = Path(__file__).resolve().parents[1]


class PredictionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    line: int = Field(default=2, ge=1, le=9)
    service: Literal["일반", "급행"] = "일반"
    from_station: str = Field(min_length=1, max_length=40, examples=["사당"])
    to_station: str = Field(min_length=1, max_length=40, examples=["방배"])
    at: datetime | time | None = Field(
        default=None,
        description="ISO 8601 또는 HH:MM. 시간만 입력하면 한국 오늘 날짜. 생략하면 현재 한국 시각, 시간대 없는 값은 한국 시각.",
    )
    scenario_strength: float = Field(
        default=0.2,
        ge=0,
        le=0.3,
        allow_inf_nan=False,
        description="학습된 계수가 아닌 위치 집중도 시나리오 강도",
    )


class JourneyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_station: str = Field(min_length=1, max_length=40, examples=["건대"])
    to_station: str = Field(min_length=1, max_length=40, examples=["고속터미널"])
    at: datetime | time | None = None
    from_line: int | None = Field(default=None, ge=1, le=9)
    to_line: int | None = Field(default=None, ge=1, le=9)
    strategy: Literal["estimated_fastest", "fewest_transfers"] = "estimated_fastest"
    allow_express: bool = True
    scenario_strength: float = Field(default=0.2, ge=0, le=0.3, allow_inf_nan=False)


def create_app(db_path=None):
    db = Path(db_path or os.getenv("SQLITE_PATH", ROOT / "var/subway.sqlite3"))

    @asynccontextmanager
    async def lifespan(app):
        app.state.model = Model(ROOT, db)
        app.state.journey = JourneyModel(app.state.model)
        db.parent.mkdir(parents=True, exist_ok=True)
        with connect(db) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS predictions (id INTEGER PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP, result_json TEXT NOT NULL)"
            )
        yield

    app = FastAPI(
        title="지하철 칸별 혼잡도 추정",
        version="0.3.0",
        lifespan=lifespan,
        description="1~9호선 다음 정차역 구간. 칸별 값은 위치 배분 시나리오이며 실측 검증되지 않았습니다.",
    )

    @app.get("/health")
    def health():
        return {"status": "ok", "model_version": app.state.model.artifact["version"]}

    @app.get("/v1/segments")
    def segments(line: int | None = Query(default=None, ge=1, le=9)):
        return {"segments": app.state.model.segments(line)}

    @app.get("/v1/stations")
    def stations(line: int | None = Query(default=None, ge=1, le=9)):
        with connect(db) as conn:
            rows = conn.execute(
                "SELECT details_json FROM stations WHERE (? IS NULL OR line=?) ORDER BY line,code",
                (line, line),
            )
            return {"stations": [json.loads(r[0]) for r in rows]}

    @app.get("/v1/stations/{station_id}")
    def station_detail(station_id: str):
        with connect(db) as conn:
            row = conn.execute(
                "SELECT details_json FROM stations WHERE id=?", (station_id,)
            ).fetchone()
            if row is None:
                raise HTTPException(404, "역을 찾을 수 없습니다.")
            return json.loads(row[0])

    @app.get("/v1/stations/{station_id}/observations")
    def observations(
        station_id: str,
        limit: int = Query(100, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ):
        st = station_detail(station_id)
        with connect(db) as conn:
            # Include branch-specific source codes in the raw history of their physical station.
            codes = {st["code"]} | {
                s["profile_station"]
                for s in app.state.model.segments(st["line"])
                if s["from_id"] == station_id
            }
            placeholders = ",".join("?" for _ in codes)
            where = f"line=? AND station IN ({placeholders})"
            args = (st["line"], *sorted(codes))
            total = conn.execute(
                f"SELECT count(*) FROM observations WHERE {where}", args
            ).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM observations WHERE {where} ORDER BY period DESC,station,direction,service,daytype,time LIMIT ? OFFSET ?",
                (*args, limit, offset),
            )
            return {
                "total": total,
                "limit": limit,
                "offset": offset,
                "observations": [dict(r) for r in rows],
            }

    @app.get("/v1/stations/{station_id}/ridership")
    def ridership(
        station_id: str, service_date: date, limit: int = Query(100, ge=1, le=500)
    ):
        station_detail(station_id)
        with connect(db) as conn:
            rows = conn.execute(
                "SELECT source_file,row_number,raw_json FROM raw_records WHERE kind='ridership' AND station_id=? AND date=? ORDER BY source_file,row_number LIMIT ?",
                (station_id, service_date.isoformat(), limit),
            )
            records = [
                {"source_file": r[0], "row_number": r[1], "raw": json.loads(r[2])}
                for r in rows
            ]
            return {
                "station_id": station_id,
                "service_date": service_date,
                "records": records,
            }

    @app.get("/v1/model")
    def model_info():
        return {
            "version": app.state.model.artifact["version"],
            "metrics": json.loads((ROOT / "artifacts/metrics.json").read_text()),
            "provenance": json.loads((ROOT / "datasets/sources_all.json").read_text()),
        }

    @app.post("/v1/journeys/predict")
    def journey(body: JourneyRequest):
        try:
            r = app.state.journey.predict(
                body.from_station,
                body.to_station,
                body.at,
                body.scenario_strength,
                body.from_line,
                body.to_line,
                body.strategy,
                body.allow_express,
            )
        except PredictionError as exc:
            raise HTTPException(422, str(exc)) from exc
        with connect(db) as conn:
            cur = conn.execute(
                "INSERT INTO predictions(result_json) VALUES (?)",
                (json.dumps(r, ensure_ascii=False),),
            )
            r["prediction_id"] = cur.lastrowid
            conn.execute(
                "DELETE FROM predictions WHERE id <= ?", (cur.lastrowid - 1000,)
            )
        return r

    @app.post("/v1/predict")
    def predict(body: PredictionRequest):
        try:
            r = app.state.model.predict(
                body.from_station,
                body.to_station,
                body.at,
                body.scenario_strength,
                line=body.line,
                service=body.service,
            )
        except PredictionError as e:
            raise HTTPException(422, str(e)) from e
        with connect(db) as conn:
            cur = conn.execute(
                "INSERT INTO predictions(result_json) VALUES (?)",
                (json.dumps(r, ensure_ascii=False),),
            )
            r["prediction_id"] = cur.lastrowid
            conn.execute(
                "DELETE FROM predictions WHERE id <= ?", (cur.lastrowid - 1000,)
            )
        return r

    return app


app = create_app()
