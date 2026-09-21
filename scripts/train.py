"""Fit exponential smoothing directly, chronological validation and untouched last test."""

import csv
import gzip
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_rows():
    with gzip.open(ROOT / "datasets/congestion.csv.gz", "rt") as f:
        return list(csv.DictReader(f))


def key(r):
    return "|".join(r[c] for c in ["station", "direction", "daytype", "time"])


def valid(r):
    try:
        return math.isfinite(float(r["congestion"])) and float(r["congestion"]) > 0
    except ValueError:
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
    return {
        "n": len(pairs),
        "positive_targets": sum(valid(r) for r in rows),
        "mae_pp": sum(abs(p - y) for p, y in pairs) / len(pairs),
        "rmse_pp": math.sqrt(sum((p - y) ** 2 for p, y in pairs) / len(pairs)),
    }


def main():
    rows = read_rows()
    periods = sorted({r["period"] for r in rows})
    val, test = periods[-2:]
    train = [r for r in rows if r["period"] < val]
    validation = [r for r in rows if r["period"] == val]
    testing = [r for r in rows if r["period"] == test]
    candidates = [
        {"alpha": a, **score(fit(train, a), validation)}
        for a in [0.1, 0.25, 0.5, 0.75, 1.0]
    ]
    best = min(candidates, key=lambda r: r["mae_pp"])["alpha"]
    pretest = [r for r in rows if r["period"] < test]
    metrics = {
        "target": "survey_period_train_average_not_car_ground_truth",
        "periods": periods,
        "validation_period": val,
        "test_period": test,
        "validation_candidates": candidates,
        "selected_alpha": best,
        "test": score(fit(pretest, best), testing),
        "test_previous_snapshot_baseline": score(fit(pretest, 1), testing),
        "excluded_nonpositive_or_missing": sum(not valid(r) for r in rows),
        "car_accuracy": None,
        "limitations": [
            "Snapshots are published aggregates, not independent daily observations.",
            "Zero may indicate no service; excluded rather than treated as empty train.",
            "No car labels: location weights are scenario assumptions, not learned.",
        ],
    }
    artifact = {
        "version": "survey-ewma-location-scenario-v1",
        "trained_through": test,
        "alpha": best,
        "profiles": fit(rows, best),
        "training_sha256": hashlib.sha256(
            (ROOT / "datasets/congestion.csv.gz").read_bytes()
        ).hexdigest(),
    }
    (ROOT / "artifacts/model.json").write_text(
        json.dumps(artifact, ensure_ascii=False, separators=(",", ":"))
    )
    (ROOT / "artifacts/metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2)
    )
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
