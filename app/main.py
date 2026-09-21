import json
import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.model import Model, PredictionError

ROOT = Path(__file__).resolve().parents[1]


class PredictionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
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


def create_app(db_path=None):
    db = Path(db_path or os.getenv("SQLITE_PATH", ROOT / "var/subway.sqlite3"))

    @asynccontextmanager
    async def lifespan(app):
        app.state.model = Model(ROOT)
        db.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(db) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS predictions (id INTEGER PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP, result_json TEXT NOT NULL)"
            )
        yield

    app = FastAPI(
        title="지하철 칸별 혼잡도 추정",
        version="0.1.0",
        lifespan=lifespan,
        description="2호선 본선 인접 구간. 칸별 값은 위치 배분 시나리오이며 실측 검증되지 않았습니다.",
    )

    @app.get("/health")
    def health():
        return {"status": "ok", "model_version": app.state.model.artifact["version"]}

    @app.get("/v1/segments")
    def segments():
        return {"segments": app.state.model.segments()}

    @app.get("/v1/model")
    def model_info():
        return {
            "version": app.state.model.artifact["version"],
            "metrics": json.loads((ROOT / "artifacts/metrics.json").read_text()),
            "provenance": json.loads((ROOT / "datasets/provenance.json").read_text()),
        }

    @app.post("/v1/predict")
    def predict(body: PredictionRequest):
        try:
            r = app.state.model.predict(
                body.from_station, body.to_station, body.at, body.scenario_strength
            )
        except PredictionError as e:
            raise HTTPException(422, str(e)) from e
        with sqlite3.connect(db, timeout=10) as conn:
            cur = conn.execute(
                "INSERT INTO predictions(result_json) VALUES (?)",
                (json.dumps(r, ensure_ascii=False),),
            )
            r["prediction_id"] = cur.lastrowid
            conn.execute(
                "DELETE FROM predictions WHERE id <= ?", (cur.lastrowid - 10000,)
            )
        return r

    return app


app = create_app()
