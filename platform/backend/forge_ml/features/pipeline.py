"""Feature engineering pipeline.

Produces a feature matrix from a raw time-indexed dataframe. Designed for
both forecasting and anomaly-detection models.

Features produced:
  - Lag features: lag_1, lag_7, lag_14, lag_28
  - Rolling stats: roll_mean_7/14/28, roll_std_7/14/28, roll_min/max
  - Calendar: day-of-week, day-of-month, week, month, quarter, year, is_month_end
  - Fourier seasonality: sin/cos pairs for weekly and yearly cycles
  - Difference features: diff_1, diff_7
  - Lag interaction: ema_alpha=0.3, ema_alpha=0.1

The pipeline is fittable (so we can persist it via joblib for serving),
and the output schema is stable across calls (training-serving consistency).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class FeatureConfig:
    """How to build features. Different KPIs benefit from different lags
    (e.g. weekly business cycles vs daily transaction patterns)."""
    lags: list[int] = field(default_factory=lambda: [1, 7, 14, 28])
    rolling_windows: list[int] = field(default_factory=lambda: [7, 14, 28])
    diff_periods: list[int] = field(default_factory=lambda: [1, 7])
    fourier_periods: list[int] = field(default_factory=lambda: [7, 365])  # weekly, yearly
    fourier_orders: int = 3
    ema_alphas: list[float] = field(default_factory=lambda: [0.3, 0.1])
    add_calendar: bool = True
    timestamp_col: str = "timestamp"
    target_col: str = "value"
    extra_features: list[str] = field(default_factory=list)  # passthrough columns


class FeaturePipeline:
    """Stateless transformation. Holds a config + the schema of generated
    features (locked at fit time for training-serving consistency)."""

    def __init__(self, config: Optional[FeatureConfig] = None):
        self.config = config or FeatureConfig()
        self._feature_columns: list[str] | None = None  # locked at fit

    @property
    def feature_columns(self) -> list[str]:
        if self._feature_columns is None:
            raise RuntimeError("Pipeline not yet fitted. Call fit_transform first.")
        return list(self._feature_columns)

    def fit_transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Build features from raw time series. Locks the feature schema."""
        out = self._build(df)
        # Lock the schema (ordered) — never include the target in features
        self._feature_columns = [c for c in out.columns
                                  if c not in (self.config.timestamp_col, self.config.target_col)]
        return out

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply same feature build, conform to locked schema (handles
        missing/extra columns gracefully — critical for serving where
        the input row may not yet have all lookbacks)."""
        out = self._build(df)
        if self._feature_columns is not None:
            for col in self._feature_columns:
                if col not in out.columns:
                    out[col] = np.nan
            # Drop any columns the original schema didn't have
            keep = [self.config.timestamp_col, self.config.target_col, *self._feature_columns]
            out = out[[c for c in keep if c in out.columns]]
        return out

    # ── implementation ────────────────────────────────────────────────

    def _build(self, df: pd.DataFrame) -> pd.DataFrame:
        cfg = self.config
        if cfg.timestamp_col not in df.columns:
            raise ValueError(f"DataFrame missing timestamp column '{cfg.timestamp_col}'")

        df = df.copy()
        df[cfg.timestamp_col] = pd.to_datetime(df[cfg.timestamp_col])
        df = df.sort_values(cfg.timestamp_col).reset_index(drop=True)

        target = df[cfg.target_col] if cfg.target_col in df.columns else None

        # Lag features
        if target is not None:
            for lag in cfg.lags:
                df[f"lag_{lag}"] = target.shift(lag)

            # Rolling stats — use shift(1) so we don't leak the current value
            for w in cfg.rolling_windows:
                shifted = target.shift(1)
                df[f"roll_mean_{w}"] = shifted.rolling(w, min_periods=max(2, w // 2)).mean()
                df[f"roll_std_{w}"] = shifted.rolling(w, min_periods=max(2, w // 2)).std()
                df[f"roll_min_{w}"] = shifted.rolling(w, min_periods=max(2, w // 2)).min()
                df[f"roll_max_{w}"] = shifted.rolling(w, min_periods=max(2, w // 2)).max()

            # Differences
            for d in cfg.diff_periods:
                df[f"diff_{d}"] = target.diff(d)

            # Exponential moving averages
            for alpha in cfg.ema_alphas:
                df[f"ema_{alpha}"] = target.shift(1).ewm(alpha=alpha, adjust=False).mean()

        # Calendar features
        if cfg.add_calendar:
            ts = df[cfg.timestamp_col].dt
            df["dow"] = ts.dayofweek
            df["dom"] = ts.day
            df["week"] = ts.isocalendar().week.astype(int)
            df["month"] = ts.month
            df["quarter"] = ts.quarter
            df["year"] = ts.year
            df["is_month_end"] = ts.is_month_end.astype(int)
            df["is_month_start"] = ts.is_month_start.astype(int)
            df["is_weekend"] = (ts.dayofweek >= 5).astype(int)

        # Fourier seasonality
        # Encode cyclical position with sin/cos so models can learn periodicity
        # without one-hot blowing up dimensionality
        epoch_days = (df[cfg.timestamp_col] - df[cfg.timestamp_col].min()).dt.total_seconds() / 86400.0
        for period in cfg.fourier_periods:
            for order in range(1, cfg.fourier_orders + 1):
                df[f"fourier_sin_{period}_{order}"] = np.sin(2 * np.pi * order * epoch_days / period)
                df[f"fourier_cos_{period}_{order}"] = np.cos(2 * np.pi * order * epoch_days / period)

        # Passthrough extras (must already be in df)
        for col in cfg.extra_features:
            if col not in df.columns:
                df[col] = np.nan

        return df

    def to_dict(self) -> dict:
        return {
            "config": self.config.__dict__,
            "feature_columns": self._feature_columns,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FeaturePipeline":
        cfg = FeatureConfig(**d["config"])
        p = cls(cfg)
        p._feature_columns = d.get("feature_columns")
        return p
