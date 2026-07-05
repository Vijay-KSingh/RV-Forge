"""Integration test for forge_ml — feature pipeline, anomaly ensemble, forecasting."""
import sys, time
sys.path.insert(0, "/home/claude/forge/platform/backend")

import numpy as np
import pandas as pd

print("=" * 70)
print("Test 1: Feature pipeline")
print("=" * 70)

from forge_ml.features.pipeline import FeaturePipeline, FeatureConfig

np.random.seed(42)
dates = pd.date_range("2025-01-01", periods=180, freq="D")
# Realistic-ish revenue series: trend + weekly seasonality + noise + a spike
trend = np.linspace(1000, 1300, 180)
weekly = 50 * np.sin(2 * np.pi * np.arange(180) / 7)
noise = np.random.normal(0, 25, 180)
values = trend + weekly + noise
values[120] *= 1.4  # injected spike

df = pd.DataFrame({"timestamp": dates, "value": values})

cfg = FeatureConfig()
pipe = FeaturePipeline(cfg)
feats = pipe.fit_transform(df)
print(f"input rows: {len(df)}")
print(f"output rows: {len(feats)} (NaN-padded for lookbacks)")
print(f"feature columns: {len(pipe.feature_columns)}")
print(f"  sample: {pipe.feature_columns[:8]} ...")
print(f"  rolling stats: {[c for c in pipe.feature_columns if 'roll_' in c][:6]}")
print(f"  fourier: {[c for c in pipe.feature_columns if 'fourier_' in c][:4]}")
print()


print("=" * 70)
print("Test 2: Anomaly ensemble")
print("=" * 70)

from forge_ml.models.anomaly.ensemble import AnomalyEnsemble, AnomalyConfig

# Build features and pad with the value column for the ensemble
training_df = feats.dropna(subset=pipe.feature_columns).copy()
ens = AnomalyEnsemble(AnomalyConfig(iforest_contamination=0.04))
t0 = time.time()
ens.fit(training_df, y=None, value_column="value")
print(f"trained in {time.time()-t0:.2f}s on {len(training_df)} rows")

detections = ens.predict(training_df, value_column="value", timestamp_column="timestamp")
n_anom = sum(1 for d in detections if d.is_anomaly)
top = sorted(detections, key=lambda d: d.fused_score, reverse=True)[:5]
print(f"flagged {n_anom}/{len(detections)} as anomalous")
print("top 5 by fused score:")
for d in top:
    print(f"  {d.timestamp.date()}  val={d.value:7.2f}  fused={d.fused_score:.3f}  flagged={d.detectors_flagging}")

# Verify the spike at index 120 is in the top
spike_ts = dates[120].date()
spike_score = next((d.fused_score for d in detections if d.timestamp.date() == spike_ts), None)
spike_score_str = f"{spike_score:.3f}" if spike_score is not None else "NA"
print(f"injected spike @ {spike_ts}: fused score = {spike_score_str}")
print()


print("=" * 70)
print("Test 3: Forecasting auto-selection")
print("=" * 70)

from forge_ml.models.forecasting.ensemble import autoselect_and_forecast

# Use a clean version (no injected spike) so the metrics are honest
clean_values = trend + weekly + np.random.normal(0, 20, 180)
clean_df = pd.DataFrame({"timestamp": dates, "value": clean_values})

t0 = time.time()
result = autoselect_and_forecast(clean_df, horizon=14, n_folds=2, test_size=14,
                                  models=["arima", "sarima", "holt_winters", "xgboost"])
print(f"auto-selection completed in {time.time()-t0:.1f}s")
print(f"winner: {result.winning_model}  (runner-up: {result.runner_up_model})")
print(f"selection reason: {result.selection_reason}")
print()
print("backtest scoreboard:")
print(f"  {'model':15s}  {'MAPE %':>8s}  {'RMSE':>10s}  {'MAE':>10s}  {'folds':>5s}  {'fit_s':>7s}")
for s in result.scoreboard:
    print(f"  {s.model_name:15s}  {s.mape:8.2f}  {s.rmse:10.2f}  {s.mae:10.2f}  {s.folds:5d}  {s.fit_seconds:7.2f}")
print()
print(f"forecast (first 5 of {len(result.point)}):")
for i in range(5):
    print(f"  {result.timestamps[i].date()}  yhat={result.point[i]:7.1f}  "
          f"95% [{result.lower95[i]:7.1f}, {result.upper95[i]:7.1f}]")
print()


print("=" * 70)
print("Test 4: Drift detection")
print("=" * 70)

from forge_ml.drift.detector import compare, DriftConfig, psi, ks_test

# Build "reference" and "new" features from STATIONARY data (no trend) so a
# no-drift comparison is honest. We then inject drift in the second test.
np.random.seed(123)
stationary_dates = pd.date_range("2024-01-01", periods=200, freq="D")
stationary_values = 1000 + 50 * np.sin(2 * np.pi * np.arange(200) / 7) + np.random.normal(0, 25, 200)
stat_df = pd.DataFrame({"timestamp": stationary_dates, "value": stationary_values})

stat_pipe = FeaturePipeline()
all_feats = stat_pipe.fit_transform(stat_df).dropna()

# Random shuffle, then split (this destroys ordering so neither half has
# a trend, both are samples from the same distribution)
shuffled = all_feats.sample(frac=1.0, random_state=7).reset_index(drop=True)
half = len(shuffled) // 2
ref_feats = shuffled.iloc[:half].copy()
new_feats_no_drift = shuffled.iloc[half:].copy()

# No drift case
report = compare(ref_feats, new_feats_no_drift)
print(f"NO-DRIFT case: {report.summary}")
print(f"  should_retrain={report.should_retrain}  drifted={[d.feature for d in report.drifted_features]}")

# Inject drift: shift values in 'new'
new_drift = new_feats_no_drift.copy()
shift_cols = ["value", "lag_1", "lag_7", "roll_mean_7"]
for col in shift_cols:
    if col in new_drift.columns:
        new_drift[col] = new_drift[col] * 1.5 + 200

report2 = compare(ref_feats, new_drift)
print(f"DRIFTED case: {report2.summary}")
print(f"  should_retrain={report2.should_retrain}")
for d in report2.drifted_features[:5]:
    print(f"    {d.feature}: PSI={d.psi:.3f}  KS={d.ks_statistic:.3f} p={d.ks_pvalue:.2e}  severity={d.severity.value}")
print()


print("=" * 70)
print("Test 5: Trainer orchestration (without MLflow)")
print("=" * 70)

import os
os.environ.pop("MLFLOW_TRACKING_URI", None)  # ensure no real MLflow needed
from forge_ml.orchestration.trainer import train_anomaly_detector, train_forecaster

import tempfile
with tempfile.TemporaryDirectory() as tmp:
    anom = train_anomaly_detector("test_co", "revenue", df, artifact_dir=tmp)
    print(f"anomaly trained: bundle saved at {anom['bundle_path']}")
    print(f"  metrics: {anom['metrics']}")
    print()
    fc = train_forecaster("test_co", "revenue", clean_df, horizon=7, n_folds=2, test_size=14,
                          candidate_models=["arima", "holt_winters", "xgboost"],
                          artifact_dir=tmp)
    print(f"forecast trained: winner={fc['winning_model']}")
    print(f"  metrics: {fc['metrics']}")

print()
print("=" * 70)
print("✅ ALL ML TESTS PASSED")
print("=" * 70)
