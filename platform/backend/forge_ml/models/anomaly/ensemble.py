"""Anomaly detection ensemble.

Combines three detectors and fuses their scores:

  1. Isolation Forest (unsupervised) — scikit-learn
       - Good at "global" anomalies in feature space
       - Works without labels
       - Robust to feature scaling

  2. XGBoost classifier (supervised, when labels available)
       - Trained on (features, is_anomaly_label) when historical labels exist
       - Produces a probability score
       - Falls back to "not used" when labels < threshold

  3. Statistical baseline (z-score + IQR)
       - The original forge.intelligence.insights detector
       - Catches univariate anomalies the other two might miss

Score fusion:
  Each detector outputs an "anomaly score" in [0, 1] (higher = more anomalous).
  We rank-aggregate via mean of normalized scores. A point is flagged if the
  fused score exceeds the configured threshold OR if 2+ detectors flag it
  individually (intersection criterion catches strong agreement).

Why an ensemble:
  Single detectors have systematic blind spots. IForest misses local
  contextual anomalies (right value, wrong time-of-week). The statistical
  detector misses multivariate patterns. XGBoost is excellent when labels
  exist but useless when they don't. Combining gets you the best of all.

Trusted OSS: scikit-learn, xgboost, numpy, pandas. No proprietary deps.
"""
from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

try:
    from xgboost import XGBClassifier
    HAVE_XGB = True
except ImportError:
    HAVE_XGB = False

log = logging.getLogger(__name__)


@dataclass
class AnomalyConfig:
    iforest_contamination: float = 0.05
    iforest_n_estimators: int = 200
    iforest_random_state: int = 42

    z_threshold: float = 2.5
    z_window: int = 14

    xgb_min_labels: int = 50  # need at least this many positive labels
    xgb_n_estimators: int = 300
    xgb_max_depth: int = 6
    xgb_learning_rate: float = 0.05
    xgb_random_state: int = 42

    # Fusion
    fusion_threshold: float = 0.55  # flag if fused score > this
    min_detectors_agreeing: int = 2  # OR if at least this many detectors flag it


@dataclass
class AnomalyDetection:
    timestamp: pd.Timestamp
    value: float
    fused_score: float
    detector_scores: dict[str, float]
    detectors_flagging: list[str]
    is_anomaly: bool
    severity: float  # [0, 1]
    explanation: str = ""


class AnomalyEnsemble:
    """Train once, score many. Stateful: holds fitted IForest, scaler, and
    optionally XGBoost. Also remembers training-time mean/std for the
    statistical detector."""

    def __init__(self, config: Optional[AnomalyConfig] = None):
        self.config = config or AnomalyConfig()
        self.iforest: Optional[IsolationForest] = None
        self.scaler: Optional[StandardScaler] = None
        self.xgb: Optional[object] = None  # XGBClassifier when fitted
        self.trained_features: list[str] = []
        # for the z-score / IQR component we use the value column only
        self.value_mean: float = 0.0
        self.value_std: float = 1.0
        self.value_q1: float = 0.0
        self.value_q3: float = 0.0

    def fit(self, X: pd.DataFrame, y: Optional[pd.Series] = None,
             value_column: str = "value",
             timestamp_column: str = "timestamp") -> "AnomalyEnsemble":
        """Fit all available detectors. y is the optional anomaly label
        (1 = anomaly, 0 = normal). If absent or sparse, XGB is skipped."""
        # 1) Build feature matrix: drop value, timestamp, and any non-numeric columns
        excluded = {value_column, timestamp_column}
        feature_cols = [c for c in X.columns
                          if c not in excluded
                          and pd.api.types.is_numeric_dtype(X[c])]
        if not feature_cols:
            raise ValueError("No numeric feature columns found for anomaly model")
        self.trained_features = feature_cols
        Xf = X[feature_cols].copy()
        # Replace inf/nan with column medians (same handling at predict time)
        Xf = Xf.replace([np.inf, -np.inf], np.nan)
        Xf = Xf.fillna(Xf.median(numeric_only=True)).fillna(0)

        # 2) Scale features (helps IForest in some regimes)
        self.scaler = StandardScaler()
        Xs = self.scaler.fit_transform(Xf)

        # 3) Isolation Forest
        self.iforest = IsolationForest(
            n_estimators=self.config.iforest_n_estimators,
            contamination=self.config.iforest_contamination,
            random_state=self.config.iforest_random_state,
            n_jobs=-1,
        )
        self.iforest.fit(Xs)

        # 4) XGBoost classifier — only if we have enough positive labels
        if HAVE_XGB and y is not None:
            y_arr = np.asarray(y).astype(int)
            n_pos = int(y_arr.sum())
            if n_pos >= self.config.xgb_min_labels:
                self.xgb = XGBClassifier(
                    n_estimators=self.config.xgb_n_estimators,
                    max_depth=self.config.xgb_max_depth,
                    learning_rate=self.config.xgb_learning_rate,
                    random_state=self.config.xgb_random_state,
                    eval_metric="logloss",
                    use_label_encoder=False,
                    n_jobs=-1,
                    tree_method="hist",
                    # handle class imbalance
                    scale_pos_weight=max(1.0, (len(y_arr) - n_pos) / max(1, n_pos)),
                )
                self.xgb.fit(Xs, y_arr)
                log.info("Anomaly XGB trained on %d positives / %d total", n_pos, len(y_arr))
            else:
                log.info("Skipping XGB (only %d positive labels, need %d)",
                         n_pos, self.config.xgb_min_labels)

        # 5) Statistical baseline params (computed on the value column)
        if value_column in X.columns:
            vals = X[value_column].dropna().values.astype(float)
        else:
            # if no explicit value column, fall back to the first feature
            vals = Xf.iloc[:, 0].dropna().values.astype(float)
        if len(vals) > 0:
            self.value_mean = float(np.mean(vals))
            self.value_std = float(np.std(vals)) or 1e-9
            self.value_q1 = float(np.percentile(vals, 25))
            self.value_q3 = float(np.percentile(vals, 75))

        return self

    def predict(self, X: pd.DataFrame, value_column: str = "value",
                 timestamp_column: str = "timestamp") -> list[AnomalyDetection]:
        """Score each row and return one AnomalyDetection per row."""
        if self.iforest is None or self.scaler is None:
            raise RuntimeError("Ensemble not fitted. Call fit() first.")

        feature_cols = self.trained_features
        # Align columns to training schema (insert missing as NaN)
        Xf = pd.DataFrame({c: X[c] if c in X.columns else np.nan for c in feature_cols},
                          index=X.index)
        Xf = Xf.replace([np.inf, -np.inf], np.nan)
        Xf = Xf.fillna(Xf.median(numeric_only=True)).fillna(0)
        Xs = self.scaler.transform(Xf)

        # IForest score: convert to [0,1] where higher = more anomalous.
        # decision_function: higher = more normal. Invert + min-max normalize.
        if_scores_raw = self.iforest.decision_function(Xs)
        if_scores = self._normalize_inverse(if_scores_raw)

        # XGB score (if available)
        if self.xgb is not None:
            xgb_scores = self.xgb.predict_proba(Xs)[:, 1]
        else:
            xgb_scores = None

        # Statistical score: z-score normalized to [0,1] using a soft sigmoid
        if value_column in X.columns:
            vals = X[value_column].astype(float).fillna(self.value_mean).values
        else:
            vals = Xf.iloc[:, 0].astype(float).fillna(0).values
        z = (vals - self.value_mean) / self.value_std
        stat_scores = self._z_to_score(np.abs(z))
        # IQR component: anything outside [Q1-1.5*IQR, Q3+1.5*IQR] gets boosted
        iqr = max(self.value_q3 - self.value_q1, 1e-9)
        iqr_low = self.value_q1 - 1.5 * iqr
        iqr_high = self.value_q3 + 1.5 * iqr
        outside_iqr = (vals < iqr_low) | (vals > iqr_high)
        stat_scores = np.maximum(stat_scores, np.where(outside_iqr, 0.7, 0.0))

        # Fusion
        detections: list[AnomalyDetection] = []
        ts_series = X[timestamp_column] if timestamp_column in X.columns else pd.Series(X.index)
        for i in range(len(X)):
            scores = {
                "isolation_forest": float(if_scores[i]),
                "statistical": float(stat_scores[i]),
            }
            if xgb_scores is not None:
                scores["xgboost"] = float(xgb_scores[i])

            score_values = list(scores.values())
            fused = float(np.mean(score_values))

            individual_flags = [name for name, s in scores.items() if s > 0.5]
            is_anom = (
                fused >= self.config.fusion_threshold
                or len(individual_flags) >= self.config.min_detectors_agreeing
            )

            severity = float(np.clip(fused, 0.0, 1.0))
            ts_val = ts_series.iloc[i] if hasattr(ts_series, "iloc") else ts_series[i]
            detections.append(AnomalyDetection(
                timestamp=pd.Timestamp(ts_val),
                value=float(vals[i]),
                fused_score=fused,
                detector_scores=scores,
                detectors_flagging=individual_flags,
                is_anomaly=is_anom,
                severity=severity,
                explanation=self._explain(scores, individual_flags, fused, vals[i]),
            ))
        return detections

    @staticmethod
    def _normalize_inverse(arr: np.ndarray) -> np.ndarray:
        """IForest decision_function: higher = more normal. Invert + minmax."""
        inv = -arr
        lo, hi = np.min(inv), np.max(inv)
        if hi - lo < 1e-9:
            return np.zeros_like(inv)
        return (inv - lo) / (hi - lo)

    @staticmethod
    def _z_to_score(abs_z: np.ndarray) -> np.ndarray:
        """Soft sigmoid: |z|=2 → ~0.5, |z|=4 → ~0.88. Bounded [0, 1]."""
        return 1 / (1 + np.exp(-(abs_z - 2.0)))

    @staticmethod
    def _explain(scores: dict[str, float], flagged: list[str],
                  fused: float, value: float) -> str:
        if not flagged:
            return f"Normal point (fused score {fused:.2f})."
        parts = []
        if "isolation_forest" in flagged:
            parts.append("isolation forest detected feature-space outlier")
        if "xgboost" in flagged:
            parts.append("supervised model classified as anomalous")
        if "statistical" in flagged:
            parts.append("value is statistically extreme vs history")
        joined = "; ".join(parts)
        return f"⚠️ Anomaly @ {value:.2f}: {joined}. Fused confidence: {fused:.2f}."
