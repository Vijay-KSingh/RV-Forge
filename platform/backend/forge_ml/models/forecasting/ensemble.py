"""Forecasting ensemble with backtest-based auto-selection.

Models supported (each with a uniform `.fit(history)` / `.predict(horizon)` interface):
  - XGBoost regressor       — feature-engineered direct-multistep
  - CatBoost regressor      — same approach, often better with categoricals
  - ARIMA / SARIMA          — classical, statsmodels
  - Prophet                 — Meta's, handles holidays + multi-seasonality
  - Holt-Winters (ETS)      — robust, simple, good baseline

Selection algorithm:
  1) Walk-forward expanding-window backtest with N folds on the history.
  2) Compute MAPE, RMSE, MAE per fold.
  3) Score each model by mean MAPE (with RMSE tiebreaker).
  4) Return the winning model PLUS the next-best (kept warm for ensemble).

Output of forecast():
  ForecastResult with point predictions, prediction intervals (95%), the
  winning model name, and the full backtest scoreboard so the user can see
  WHY a particular model was chosen.
"""
from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from typing import Optional, Protocol

import numpy as np
import pandas as pd

from forge_ml.features.pipeline import FeaturePipeline, FeatureConfig

log = logging.getLogger(__name__)
warnings.filterwarnings("ignore")


# ──────────────────────────────────────────────────────────────────────
# Model protocol — all underlying models conform to this
# ──────────────────────────────────────────────────────────────────────

class ForecastModel(Protocol):
    name: str
    def fit(self, history: pd.DataFrame) -> "ForecastModel": ...
    def predict(self, horizon: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Returns (point, lower95, upper95) arrays of length `horizon`."""
        ...


# ──────────────────────────────────────────────────────────────────────
# 1) XGBoost / CatBoost - feature-based direct multi-step
# ──────────────────────────────────────────────────────────────────────

class _GBMBase:
    """Common feature-based regressor wrapper."""
    def __init__(self, name: str):
        self.name = name
        self.pipeline: Optional[FeaturePipeline] = None
        self.model = None
        self._last_history: Optional[pd.DataFrame] = None
        self._residual_std: float = 0.0

    def _make_model(self):
        raise NotImplementedError

    def fit(self, history: pd.DataFrame):
        self._last_history = history.copy()
        cfg = FeatureConfig(timestamp_col="timestamp", target_col="value")
        self.pipeline = FeaturePipeline(cfg)
        feats = self.pipeline.fit_transform(history)
        feats = feats.dropna(subset=self.pipeline.feature_columns + ["value"])
        if len(feats) < 20:
            raise ValueError(f"{self.name}: too few rows after feature build ({len(feats)})")
        X = feats[self.pipeline.feature_columns].values
        y = feats["value"].values
        self.model = self._make_model()
        self.model.fit(X, y)
        # Residual std for prediction intervals
        preds = self.model.predict(X)
        self._residual_std = float(np.std(y - preds)) or 1e-9
        return self

    def predict(self, horizon: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        if self.pipeline is None or self.model is None:
            raise RuntimeError(f"{self.name} not fitted")
        # Recursive multi-step: extend the history by predicting one step,
        # then refeaturizing, then predicting the next.
        hist = self._last_history.copy()
        last_ts = pd.to_datetime(hist["timestamp"]).max()
        freq = self._infer_freq(hist["timestamp"])
        out = []
        for i in range(horizon):
            next_ts = last_ts + (i + 1) * freq
            row = pd.DataFrame({"timestamp": [next_ts], "value": [np.nan]})
            window = pd.concat([hist, row], ignore_index=True)
            feats = self.pipeline.transform(window)
            x = feats.iloc[-1][self.pipeline.feature_columns].values.reshape(1, -1)
            x = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
            yhat = float(self.model.predict(x)[0])
            out.append(yhat)
            # append predicted value back into history for the next step
            hist = pd.concat([hist, pd.DataFrame({"timestamp": [next_ts], "value": [yhat]})],
                              ignore_index=True)
        point = np.array(out)
        # 95% interval via residual std (assumes Gaussian residuals)
        ci = 1.96 * self._residual_std * np.sqrt(np.arange(1, horizon + 1))
        return point, point - ci, point + ci

    @staticmethod
    def _infer_freq(ts: pd.Series) -> pd.Timedelta:
        diffs = pd.to_datetime(ts).diff().dropna()
        if len(diffs) == 0:
            return pd.Timedelta(days=1)
        return pd.Timedelta(diffs.median())


class XGBoostForecaster(_GBMBase):
    def __init__(self):
        super().__init__("xgboost")

    def _make_model(self):
        from xgboost import XGBRegressor
        return XGBRegressor(
            n_estimators=400, max_depth=6, learning_rate=0.05,
            subsample=0.85, colsample_bytree=0.85,
            tree_method="hist", random_state=42, n_jobs=-1,
            objective="reg:squarederror",
        )


class CatBoostForecaster(_GBMBase):
    def __init__(self):
        super().__init__("catboost")

    def _make_model(self):
        from catboost import CatBoostRegressor
        return CatBoostRegressor(
            iterations=400, depth=6, learning_rate=0.05,
            verbose=False, random_state=42,
            loss_function="RMSE", thread_count=-1,
        )


# ──────────────────────────────────────────────────────────────────────
# 2) ARIMA / SARIMA via statsmodels
# ──────────────────────────────────────────────────────────────────────

class ARIMAForecaster:
    name = "arima"

    def __init__(self, order=(2, 1, 2)):
        self.order = order
        self.model_fit = None
        self._last_history: Optional[pd.DataFrame] = None

    def fit(self, history: pd.DataFrame):
        from statsmodels.tsa.arima.model import ARIMA
        self._last_history = history.copy()
        ts = self._to_series(history)
        self.model_fit = ARIMA(ts, order=self.order).fit()
        return self

    def predict(self, horizon: int):
        if self.model_fit is None:
            raise RuntimeError("ARIMA not fitted")
        fc = self.model_fit.get_forecast(steps=horizon)
        point = fc.predicted_mean.values
        ci = fc.conf_int(alpha=0.05).values
        return point, ci[:, 0], ci[:, 1]

    @staticmethod
    def _to_series(history: pd.DataFrame) -> pd.Series:
        return pd.Series(history["value"].values,
                          index=pd.to_datetime(history["timestamp"]))


class SARIMAForecaster:
    name = "sarima"

    def __init__(self, order=(1, 1, 1), seasonal_order=(1, 1, 1, 7)):
        self.order = order
        self.seasonal_order = seasonal_order
        self.model_fit = None

    def fit(self, history: pd.DataFrame):
        from statsmodels.tsa.statespace.sarimax import SARIMAX
        ts = pd.Series(history["value"].values,
                       index=pd.to_datetime(history["timestamp"]))
        self.model_fit = SARIMAX(
            ts, order=self.order, seasonal_order=self.seasonal_order,
            enforce_stationarity=False, enforce_invertibility=False,
        ).fit(disp=False, maxiter=200)
        return self

    def predict(self, horizon: int):
        if self.model_fit is None:
            raise RuntimeError("SARIMA not fitted")
        fc = self.model_fit.get_forecast(steps=horizon)
        point = fc.predicted_mean.values
        ci = fc.conf_int(alpha=0.05).values
        return point, ci[:, 0], ci[:, 1]


# ──────────────────────────────────────────────────────────────────────
# 3) Prophet
# ──────────────────────────────────────────────────────────────────────

class ProphetForecaster:
    name = "prophet"

    def __init__(self):
        self.model = None
        self._freq: Optional[pd.Timedelta] = None

    def fit(self, history: pd.DataFrame):
        from prophet import Prophet
        self.model = Prophet(daily_seasonality=False, weekly_seasonality=True,
                              yearly_seasonality=True, interval_width=0.95)
        df = pd.DataFrame({
            "ds": pd.to_datetime(history["timestamp"]),
            "y": history["value"].astype(float),
        })
        self.model.fit(df)
        diffs = df["ds"].diff().dropna()
        self._freq = pd.Timedelta(diffs.median()) if len(diffs) else pd.Timedelta(days=1)
        return self

    def predict(self, horizon: int):
        if self.model is None:
            raise RuntimeError("Prophet not fitted")
        future = self.model.make_future_dataframe(periods=horizon, freq=self._freq)
        fc = self.model.predict(future)
        tail = fc.tail(horizon)
        return (tail["yhat"].values, tail["yhat_lower"].values, tail["yhat_upper"].values)


# ──────────────────────────────────────────────────────────────────────
# 4) Holt-Winters (ETS)
# ──────────────────────────────────────────────────────────────────────

class HoltWintersForecaster:
    name = "holt_winters"

    def __init__(self, seasonal_periods: int = 7, trend: str = "add",
                  seasonal: str = "add"):
        self.seasonal_periods = seasonal_periods
        self.trend = trend
        self.seasonal = seasonal
        self.model_fit = None
        self._residual_std: float = 0.0

    def fit(self, history: pd.DataFrame):
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
        ts = pd.Series(history["value"].astype(float).values,
                       index=pd.to_datetime(history["timestamp"]))
        # Need at least 2 full seasons
        if len(ts) < 2 * self.seasonal_periods:
            raise ValueError(f"holt_winters: need ≥{2*self.seasonal_periods} points, got {len(ts)}")
        self.model_fit = ExponentialSmoothing(
            ts, trend=self.trend, seasonal=self.seasonal,
            seasonal_periods=self.seasonal_periods,
            initialization_method="estimated",
        ).fit()
        # Residual std for intervals
        resids = self.model_fit.resid.dropna().values
        self._residual_std = float(np.std(resids)) or 1e-9
        return self

    def predict(self, horizon: int):
        if self.model_fit is None:
            raise RuntimeError("Holt-Winters not fitted")
        point = self.model_fit.forecast(steps=horizon).values
        ci = 1.96 * self._residual_std * np.sqrt(np.arange(1, horizon + 1))
        return point, point - ci, point + ci


# ──────────────────────────────────────────────────────────────────────
# Backtest scoring + auto-selection
# ──────────────────────────────────────────────────────────────────────

@dataclass
class BacktestScore:
    model_name: str
    mape: float
    rmse: float
    mae: float
    folds: int
    fit_seconds: float = 0.0


@dataclass
class ForecastResult:
    horizon: int
    timestamps: list[pd.Timestamp]
    point: list[float]
    lower95: list[float]
    upper95: list[float]
    winning_model: str
    runner_up_model: Optional[str]
    scoreboard: list[BacktestScore]
    trained_on: int  # rows used for final fit
    selection_reason: str


def _metrics(y_true: np.ndarray, y_pred: np.ndarray) -> tuple[float, float, float]:
    err = y_true - y_pred
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err ** 2)))
    # Avoid divide-by-zero for MAPE
    nonzero = np.abs(y_true) > 1e-9
    if nonzero.any():
        mape = float(np.mean(np.abs(err[nonzero] / y_true[nonzero])) * 100.0)
    else:
        mape = float("inf")
    return mape, rmse, mae


def walk_forward_backtest(model_factory, history: pd.DataFrame,
                          n_folds: int = 4, test_size: int = 14) -> Optional[BacktestScore]:
    """Expanding-window backtest. Returns None if model can't be fit."""
    import time
    n = len(history)
    if n < test_size * 3:
        return None
    fold_starts = np.linspace(n - n_folds * test_size, n - test_size, n_folds, dtype=int)
    mapes, rmses, maes = [], [], []
    fit_times = []
    for start in fold_starts:
        if start < test_size * 2:
            continue
        train = history.iloc[:start]
        test = history.iloc[start:start + test_size]
        try:
            t0 = time.time()
            m = model_factory().fit(train)
            fit_times.append(time.time() - t0)
            point, _, _ = m.predict(len(test))
            point = np.asarray(point[:len(test)])
            mape, rmse, mae = _metrics(test["value"].values, point)
            mapes.append(mape); rmses.append(rmse); maes.append(mae)
        except Exception as e:
            log.warning("Backtest fold failed for %s: %s", model_factory().name, e)
            continue
    if not mapes:
        return None
    return BacktestScore(
        model_name=model_factory().name,
        mape=float(np.mean(mapes)),
        rmse=float(np.mean(rmses)),
        mae=float(np.mean(maes)),
        folds=len(mapes),
        fit_seconds=float(np.mean(fit_times)) if fit_times else 0.0,
    )


# Registry of available model factories. Some are optional (depend on packages
# being installed); we degrade gracefully when a model isn't available.
def _available_factories() -> dict[str, callable]:
    factories: dict[str, callable] = {}
    factories["arima"] = lambda: ARIMAForecaster()
    factories["sarima"] = lambda: SARIMAForecaster()
    factories["holt_winters"] = lambda: HoltWintersForecaster()
    try:
        import xgboost  # noqa
        factories["xgboost"] = lambda: XGBoostForecaster()
    except ImportError:
        pass
    try:
        import catboost  # noqa
        factories["catboost"] = lambda: CatBoostForecaster()
    except ImportError:
        pass
    try:
        import prophet  # noqa
        factories["prophet"] = lambda: ProphetForecaster()
    except ImportError:
        pass
    return factories


def autoselect_and_forecast(
    history: pd.DataFrame,
    horizon: int,
    n_folds: int = 4,
    test_size: int = 14,
    models: Optional[list[str]] = None,
) -> ForecastResult:
    """Backtest each candidate model, pick the winner by MAPE, then refit on
    full history and produce the final forecast."""
    if "timestamp" not in history.columns or "value" not in history.columns:
        raise ValueError("history must have 'timestamp' and 'value' columns")
    history = history.sort_values("timestamp").reset_index(drop=True)
    factories = _available_factories()
    if models:
        factories = {k: v for k, v in factories.items() if k in models}
    if not factories:
        raise RuntimeError("No forecasting models available — install statsmodels at minimum")

    # Backtest each
    scores: list[BacktestScore] = []
    for name, factory in factories.items():
        log.info("Backtesting %s …", name)
        score = walk_forward_backtest(factory, history, n_folds=n_folds, test_size=test_size)
        if score is not None:
            scores.append(score)

    if not scores:
        raise RuntimeError("All models failed backtest. Check input data.")

    # Sort by MAPE (lower better), break ties by RMSE
    scores.sort(key=lambda s: (s.mape, s.rmse))
    winner = scores[0]
    runner_up = scores[1] if len(scores) > 1 else None

    # Refit winner on full history
    best_factory = factories[winner.model_name]
    best_model = best_factory().fit(history)
    point, lo, hi = best_model.predict(horizon)

    # Future timestamps
    last_ts = pd.to_datetime(history["timestamp"]).max()
    diffs = pd.to_datetime(history["timestamp"]).diff().dropna()
    freq = pd.Timedelta(diffs.median()) if len(diffs) else pd.Timedelta(days=1)
    future_ts = [last_ts + (i + 1) * freq for i in range(horizon)]

    reason = (f"Selected {winner.model_name}: lowest MAPE ({winner.mape:.2f}%) across "
              f"{winner.folds} backtest folds. Runner-up "
              f"{runner_up.model_name if runner_up else 'n/a'} had MAPE "
              f"{runner_up.mape:.2f}%." if runner_up else
              f"Selected {winner.model_name} (only model that backtested cleanly).")

    return ForecastResult(
        horizon=horizon,
        timestamps=future_ts,
        point=[float(x) for x in point],
        lower95=[float(x) for x in lo],
        upper95=[float(x) for x in hi],
        winning_model=winner.model_name,
        runner_up_model=runner_up.model_name if runner_up else None,
        scoreboard=scores,
        trained_on=len(history),
        selection_reason=reason,
    )
