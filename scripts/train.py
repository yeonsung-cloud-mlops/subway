"""Fit per-line exponential smoothing from SQLite, with chronological holdout."""

import argparse
import hashlib
import json
import math

from app.database import ROOT, connect, seed_database


def key(r):
    return "|".join(
        str(r.get(c, default))
        for c, default in [
            ("line", 2),
            ("station", ""),
            ("direction", ""),
            ("service", "일반"),
            ("daytype", ""),
            ("time", ""),
        ]
    )


def valid(r):
    try:
        return math.isfinite(float(r["congestion"])) and float(r["congestion"]) > 0
    except (ValueError, TypeError):
        return False


def fit(rows, alpha):
    states = {}
    for r in sorted(rows, key=lambda r: r["period"]):
        if not valid(r):
            continue
        k = key(r)
        v = float(r["congestion"])
        s = states.get(k)
        states[k] = {
            "value": v if s is None else alpha * v + (1 - alpha) * s["value"],
            "n": 1 if s is None else s["n"] + 1,
            "last_period": r["period"],
        }
    return states


def score(states, rows):
    pairs = [
        (states[key(r)]["value"], float(r["congestion"]))
        for r in rows
        if valid(r) and key(r) in states
    ]
    if not pairs:
        return {
            "n": 0,
            "mae_pp": None,
            "rmse_pp": None,
            "positive_targets": sum(valid(r) for r in rows),
        }
    return {
        "n": len(pairs),
        "positive_targets": sum(valid(r) for r in rows),
        "mae_pp": sum(abs(p - y) for p, y in pairs) / len(pairs),
        "rmse_pp": math.sqrt(sum((p - y) ** 2 for p, y in pairs) / len(pairs)),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(ROOT / "var/subway.sqlite3"))
    args = parser.parse_args()
    seed_database(args.db)
    metrics = {
        "target": "survey_period_train_average_not_car_ground_truth",
        "car_accuracy": None,
        "lines": {},
    }
    profiles = {}
    alpha = {}
    with connect(args.db) as conn:
        for line in range(1, 10):
            rows = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM observations WHERE line=? ORDER BY period", (line,)
                )
            ]
            periods = sorted({r["period"] for r in rows})
            val, test = periods[-2:]
            train = [r for r in rows if r["period"] < val]
            validation = [r for r in rows if r["period"] == val]
            testing = [r for r in rows if r["period"] == test]
            candidates = [
                {"alpha": a, **score(fit(train, a), validation)}
                for a in [1.0, 0.75, 0.5, 0.25, 0.1]
            ]
            best = min(candidates, key=lambda r: r["mae_pp"])["alpha"]
            pretest = [r for r in rows if r["period"] < test]
            metrics["lines"][str(line)] = {
                "periods": periods,
                "validation_period": val,
                "test_period": test,
                "selected_alpha": best,
                "validation_candidates": candidates,
                "test": score(fit(pretest, best), testing),
                "baseline": score(fit(pretest, 1), testing),
                "excluded_zero_or_missing": sum(not valid(r) for r in rows),
            }
            alpha[str(line)] = best
            profiles.update(fit(rows, best))
            print(line, metrics["lines"][str(line)]["test"], flush=True)
    artifact = {
        "version": "metro-all-ewma-location-scenario-v2",
        "alpha_by_line": alpha,
        "profiles": profiles,
        "available_after_by_line": {
            str(line_number): "2026-09-09" if line_number == 9 else "2026-06-30"
            for line_number in range(1, 10)
        },
        "training_sha256": hashlib.sha256(
            (ROOT / "datasets/observations.csv.gz").read_bytes()
        ).hexdigest(),
    }
    (ROOT / "artifacts/model.json").write_text(
        json.dumps(artifact, ensure_ascii=False, separators=(",", ":"))
    )
    (ROOT / "artifacts/metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2)
    )


if __name__ == "__main__":
    main()
