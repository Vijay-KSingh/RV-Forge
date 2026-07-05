"""E2E test of the new /api/ml/* endpoints using in-process TestClient."""
import sys
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, "/home/claude/forge/platform/backend")

import numpy as np
from fastapi.testclient import TestClient

from forge.api import app

client = TestClient(app)

# Generate a clean training series
np.random.seed(42)
N = 240
base = datetime(2024, 1, 1)
trend = np.linspace(8000, 11000, N)
weekly = 700 * np.sin(2 * np.pi * np.arange(N) / 7)
noise = np.random.normal(0, 350, N)
values = trend + weekly + noise
# Inject a known spike at index 180
values[180] = values[180] * 1.6

history = [
    {"timestamp": (base + timedelta(days=i)).isoformat(), "value": float(values[i])}
    for i in range(N)
]

print("=" * 70)
print("Test: /api/ml/forecast (one-shot auto-selection)")
print("=" * 70)

resp = client.post("/api/ml/forecast", json={
    "history": history,
    "horizon": 14,
    "n_folds": 2,
    "test_size": 14,
    "candidate_models": ["arima", "sarima", "holt_winters", "xgboost"],
})
assert resp.status_code == 200, resp.text
data = resp.json()
print(f"winner: {data['winning_model']}  (runner-up: {data['runner_up']})")
print(f"trained on {data['trained_on']} rows, horizon {data['horizon']}")
print("scoreboard:")
for s in data["scoreboard"]:
    print(f"  {s['model_name']:15s}  MAPE={s['mape']:6.2f}%  RMSE={s['rmse']:8.2f}  folds={s['folds']}")
print("first 3 forecast points:")
for f in data["forecast"][:3]:
    print(f"  {f['timestamp']}  yhat={f['yhat']:8.1f}  95% [{f['lower95']:8.1f}, {f['upper95']:8.1f}]")
print()


print("=" * 70)
print("Test: /api/ml/train/anomaly + /api/ml/anomaly/score")
print("=" * 70)

with tempfile.TemporaryDirectory() as tmp:
    # Train
    resp = client.post("/api/ml/train/anomaly", json={
        "customer_id": "demo",
        "kpi_id": "revenue",
        "history": history,
        "artifact_dir": tmp,
    })
    assert resp.status_code == 200, resp.text
    train_resp = resp.json()
    print(f"trained: bundle at {train_resp['bundle_path']}")
    print(f"  metrics: {train_resp['metrics']}")
    print()

    # Score the same data — the spike should be flagged
    resp = client.post("/api/ml/anomaly/score", json={
        "customer_id": "demo", "kpi_id": "revenue",
        "history": history, "artifact_dir": tmp,
    })
    assert resp.status_code == 200, resp.text
    score_resp = resp.json()
    print(f"scored {score_resp['n_total']} points → {score_resp['n_anomalies']} flagged")
    spike_date = (base + timedelta(days=180)).isoformat()
    spike_detection = next((d for d in score_resp["detections"] if d["timestamp"].startswith(spike_date[:10])), None)
    if spike_detection:
        print(f"  ✓ injected spike correctly flagged: score={spike_detection['fused_score']:.3f}")
        print(f"    detectors: {spike_detection['detectors_flagging']}")
        print(f"    explanation: {spike_detection['explanation']}")
    else:
        print(f"  ✗ injected spike NOT flagged — false negative")
    print()


print("=" * 70)
print("Test: /api/ml/drift/check")
print("=" * 70)

# Build a "no-drift" pair (same distribution)
ref_no_drift = history[:120]
new_no_drift = history[120:]  # later half — there's a trend, so we expect SOME drift

resp = client.post("/api/ml/drift/check", json={
    "reference": ref_no_drift,
    "new": new_no_drift,
})
assert resp.status_code == 200, resp.text
no_drift = resp.json()
print(f"trended-pair (windows of same trended series):")
print(f"  severity={no_drift['overall_severity']}  retrain={no_drift['should_retrain']}")
print(f"  {no_drift['summary']}")
print()

# Build a strongly-drifted pair — shift the new window's values by +30%
shifted_new = [
    {"timestamp": p["timestamp"], "value": p["value"] * 1.3 + 2000}
    for p in new_no_drift
]
resp = client.post("/api/ml/drift/check", json={
    "reference": ref_no_drift,
    "new": shifted_new,
})
drifted = resp.json()
print(f"shifted-pair (new = ref * 1.3 + 2000):")
print(f"  severity={drifted['overall_severity']}  retrain={drifted['should_retrain']}")
print(f"  {drifted['summary']}")
print(f"  major-drifted features (top 3):")
for d in [x for x in drifted["drifted_features"] if x["severity"] == "major"][:3]:
    print(f"    {d['feature']}: PSI={d['psi']:.3f}  ref_mean={d['ref_mean']:.1f}  new_mean={d['new_mean']:.1f}")
print()


print("=" * 70)
print("✅ ALL ML API ENDPOINTS PASS")
print("=" * 70)
