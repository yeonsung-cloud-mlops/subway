"""Exercise the running Nginx -> Next.js -> FastAPI stack (stdlib only)."""

import argparse
import json
from datetime import datetime
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument("--require-originals", action="store_true")
    args = parser.parse_args()

    def request(path, body=None, status=200):
        req = Request(
            args.url.rstrip("/") + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"},
        )
        try:
            response = urlopen(req, timeout=60)
        except HTTPError as error:
            response = error
        with response:
            payload = response.read()
            assert response.status == status, (path, response.status, payload[:300])
            if "application/json" in response.headers.get("Content-Type", ""):
                return json.loads(payload)
            return payload.decode()

    assert request("/nginx-health").strip() == "ok"
    assert "<html" in request("/")
    assert request("/health")["status"] == "ok"
    assert "/v1/journeys/predict" in request("/openapi.json")["paths"]
    assert "swagger-ui" in request("/docs")
    assert len(request("/v1/stations")["stations"]) == 315
    assert len(request("/api/metro/segments")["segments"]) == 640
    assert request("/v1/stations/2:226/observations?limit=2")["total"] > 0
    if args.require_originals:
        assert request("/v1/stations/2:226/ridership?service_date=2025-01-01")[
            "records"
        ]
    body = {
        "from_station": "건대",
        "to_station": "고속터미널",
        "at": "2026-09-21T08:15:00+09:00",
    }
    direct = request("/v1/journeys/predict", body)
    proxied = request("/api/metro/journey", body)
    for result in (direct, proxied):
        assert result["status"] == "complete"
        assert result["from_station"] == "건대입구"
        assert result["to_station"] == "고속터미널"
        rides = [step for step in result["steps"] if step["kind"] == "ride"]
        assert len(rides) == result["ride_segments"] > 1
        assert result["timetable"]["route_search_basis"] == "time_expanded_earliest_arrival"
        times = [datetime.fromisoformat(step["forecast_at"]) for step in rides]
        assert all(a < b for a, b in zip(times, times[1:]))
        assert all(leg["cars"] for leg in result["legs"])
    request("/api/metro/journey", {**body, "from_station": "없는역"}, status=422)
    print(
        "PASS: Nginx, UI, API docs, stations, observations, Next.js proxy, journey and validation"
    )


if __name__ == "__main__":
    main()
