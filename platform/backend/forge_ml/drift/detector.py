"""Drift detection.

Three complementary detectors:

  1. PSI (Population Stability Index) — feature-level, used in lending/credit
     industry as the standard distribution-shift metric. Bins reference + new
     samples, computes Σ (new_pct - ref_pct) * ln(new_pct / ref_pct).
       PSI < 0.1   = no shift
       0.1 ≤ PSI < 0.2 = minor shift
       PSI ≥ 0.2   = major shift, retrain

  2. KS (Kolmogorov-Smirnov) — non-parametric, sensitive to any distribution
     change. Scipy ks_2samp returns a p-value; we flag if p < threshold.

  3. ADWIN (Adaptive Windowing) — for KPI residual streams (predicted vs
     actual). Detects concept drift incrementally, online. We use a simple
     reimplementation since the river library isn't always available.

Output: a DriftReport with per-feature scores, severity, and a clear
"should we retrain?" recommendation. Pluggable thresholds.

Trusted OSS: scipy, numpy, pandas. River is optional and used if installed.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats

log = logging.getLogger(__name__)


class DriftSeverity(str, Enum):
    NONE = "none"
    MINOR = "minor"
    MAJOR = "major"


@dataclass
class FeatureDrift:
    feature: str
    psi: float
    ks_statistic: float
    ks_pvalue: float
    severity: DriftSeverity
    ref_summary: dict
    new_summary: dict


@dataclass
class DriftReport:
    n_features_checked: int
    drifted_features: list[FeatureDrift]
    should_retrain: bool
    overall_severity: DriftSeverity
    summary: str
    timestamp: pd.Timestamp = field(default_factory=pd.Timestamp.utcnow)


# ──────────────────────────────────────────────────────────────────────
# PSI
# ──────────────────────────────────────────────────────────────────────

def psi(ref: np.ndarray, new: np.ndarray, n_bins: int = 10) -> float:
    """Compute PSI between reference and new distributions.

    Uses quantile-based bin edges from the reference (avoids issues with
    open-ended bins). Adds a small epsilon to avoid log(0).
    """
    ref = np.asarray(ref, dtype=float)
    new = np.asarray(new, dtype=float)
    ref = ref[~np.isnan(ref)]
    new = new[~np.isnan(new)]
    if len(ref) == 0 or len(new) == 0:
        return float("inf")

    # Quantile edges from reference
    edges = np.unique(np.quantile(ref, np.linspace(0, 1, n_bins + 1)))
    if len(edges) < 3:
        # near-constant reference; fall back to linspace
        lo, hi = float(min(ref.min(), new.min())), float(max(ref.max(), new.max()))
        if hi - lo < 1e-9:
            return 0.0
        edges = np.linspace(lo, hi, n_bins + 1)

    # Histograms
    ref_counts, _ = np.histogram(ref, bins=edges)
    new_counts, _ = np.histogram(new, bins=edges)
    ref_pct = ref_counts / (ref_counts.sum() or 1)
    new_pct = new_counts / (new_counts.sum() or 1)

    eps = 1e-6
    ref_pct = np.where(ref_pct == 0, eps, ref_pct)
    new_pct = np.where(new_pct == 0, eps, new_pct)
    return float(np.sum((new_pct - ref_pct) * np.log(new_pct / ref_pct)))


def psi_severity(value: float) -> DriftSeverity:
    if value < 0.1:
        return DriftSeverity.NONE
    if value < 0.2:
        return DriftSeverity.MINOR
    return DriftSeverity.MAJOR


# ──────────────────────────────────────────────────────────────────────
# KS test
# ──────────────────────────────────────────────────────────────────────

def ks_test(ref: np.ndarray, new: np.ndarray) -> tuple[float, float]:
    """Returns (statistic, p-value)."""
    ref = np.asarray(ref, dtype=float)
    new = np.asarray(new, dtype=float)
    ref = ref[~np.isnan(ref)]
    new = new[~np.isnan(new)]
    if len(ref) < 5 or len(new) < 5:
        return 0.0, 1.0
    res = stats.ks_2samp(ref, new)
    return float(res.statistic), float(res.pvalue)


# ──────────────────────────────────────────────────────────────────────
# ADWIN — adaptive windowing for residual streams
# ──────────────────────────────────────────────────────────────────────

class ADWIN:
    """Simple ADWIN for online drift detection on a 1-D stream.

    Maintains a window; when a sub-window's mean differs from the rest by
    more than a confidence-bound-derived threshold, drops the older portion
    and signals drift.

    Reference: Bifet & Gavaldà 2007. This is a lightweight reimplementation;
    use river.drift.ADWIN for production.
    """

    def __init__(self, delta: float = 0.002, max_window: int = 1024):
        self.delta = delta
        self.max_window = max_window
        self.window: list[float] = []
        self.last_drift_index: int = -1

    def update(self, x: float) -> bool:
        """Adds a value to the stream; returns True if drift detected."""
        self.window.append(float(x))
        if len(self.window) > self.max_window:
            self.window.pop(0)
        if len(self.window) < 32:
            return False
        return self._check_drift()

    def _check_drift(self) -> bool:
        n = len(self.window)
        # Try several split points; if any sub-window pair is divergent enough, drift.
        # We sample split points at powers of 2 for efficiency.
        x = np.asarray(self.window)
        for split in range(8, n - 8):
            if split & (split - 1) != 0 and split % 32 != 0:
                continue
            left, right = x[:split], x[split:]
            n0, n1 = len(left), len(right)
            mu0, mu1 = float(np.mean(left)), float(np.mean(right))
            var0, var1 = float(np.var(left)), float(np.var(right))
            m = 1 / (1 / n0 + 1 / n1)
            # Hoeffding/Bernstein-style bound
            eps = float(np.sqrt(2 / m * np.log(2 * n / self.delta)) * np.sqrt(var0 + var1)
                        + 2 / (3 * m) * np.log(2 * n / self.delta))
            if abs(mu0 - mu1) > eps:
                # Drift: drop the older portion
                self.window = self.window[split:]
                self.last_drift_index += split
                return True
        return False


# ──────────────────────────────────────────────────────────────────────
# Top-level: compare reference vs new dataframe
# ──────────────────────────────────────────────────────────────────────

@dataclass
class DriftConfig:
    psi_minor_threshold: float = 0.1
    psi_major_threshold: float = 0.2
    ks_alpha: float = 0.01  # p < this → significant
    # Retrain triggers:
    # - any single MAJOR drift (with PSI+KS corroboration), OR
    # - many minor drifts (default 6, raised to avoid small-sample noise tripping it)
    min_features_drifted_for_retrain: int = 1  # any major
    minor_features_for_retrain: int = 6        # OR many minors


# Names that are deterministic functions of the timestamp — these will
# always look "drifted" between two time windows and are not informative
# about real distribution change.
_DETERMINISTIC_PREFIXES = ("fourier_", "dow", "dom", "month", "week",
                            "quarter", "year", "is_month", "is_weekend")


def _is_informative(col: str) -> bool:
    return not col.startswith(_DETERMINISTIC_PREFIXES)


def compare(reference: pd.DataFrame, new: pd.DataFrame,
            features: Optional[list[str]] = None,
            config: Optional[DriftConfig] = None,
            include_deterministic: bool = False) -> DriftReport:
    """Compute drift between two dataframes column-wise.

    By default we exclude deterministic-from-timestamp features (calendar,
    Fourier) since their distributions inevitably differ between any two
    time windows and that's not real drift.
    """
    cfg = config or DriftConfig()
    cols = features or [c for c in reference.columns
                          if pd.api.types.is_numeric_dtype(reference[c]) and c in new.columns]
    if not include_deterministic:
        cols = [c for c in cols if _is_informative(c)]

    drifts: list[FeatureDrift] = []
    for col in cols:
        ref_vals = reference[col].dropna().values
        new_vals = new[col].dropna().values
        if len(ref_vals) < 30 or len(new_vals) < 30:
            continue
        psi_val = psi(ref_vals, new_vals)
        ks_stat, ks_p = ks_test(ref_vals, new_vals)
        psi_sev = psi_severity(psi_val)
        ks_sev = (DriftSeverity.MAJOR if ks_p < cfg.ks_alpha / 10 else
                  DriftSeverity.MINOR if ks_p < cfg.ks_alpha else
                  DriftSeverity.NONE)

        # Corroboration rule: PSI and KS must AGREE on the existence of drift.
        # PSI alone is unreliable below ~200 samples per group; KS alone can
        # over-fire with very large samples. Requiring both protects against
        # both failure modes.
        #
        # Rule:
        #   both major          → MAJOR
        #   both at least minor → MINOR
        #   only one of them    → NONE (noise)
        if psi_sev == DriftSeverity.MAJOR and ks_sev == DriftSeverity.MAJOR:
            sev = DriftSeverity.MAJOR
        elif psi_sev != DriftSeverity.NONE and ks_sev != DriftSeverity.NONE:
            sev = DriftSeverity.MINOR
        else:
            sev = DriftSeverity.NONE

        if sev != DriftSeverity.NONE:
            drifts.append(FeatureDrift(
                feature=col,
                psi=psi_val,
                ks_statistic=ks_stat,
                ks_pvalue=ks_p,
                severity=sev,
                ref_summary={"mean": float(np.mean(ref_vals)), "std": float(np.std(ref_vals)),
                              "n": len(ref_vals)},
                new_summary={"mean": float(np.mean(new_vals)), "std": float(np.std(new_vals)),
                              "n": len(new_vals)},
            ))

    n_major = sum(1 for d in drifts if d.severity == DriftSeverity.MAJOR)
    n_minor = sum(1 for d in drifts if d.severity == DriftSeverity.MINOR)
    overall = (DriftSeverity.MAJOR if n_major > 0 else
               DriftSeverity.MINOR if n_minor > 0 else
               DriftSeverity.NONE)
    should_retrain = (n_major >= cfg.min_features_drifted_for_retrain
                      or n_minor >= cfg.minor_features_for_retrain)

    summary_parts = [
        f"Checked {len(cols)} numeric features",
        f"{n_major} major drift, {n_minor} minor",
        f"recommendation: {'RETRAIN' if should_retrain else 'no action'}"
    ]
    return DriftReport(
        n_features_checked=len(cols),
        drifted_features=drifts,
        should_retrain=should_retrain,
        overall_severity=overall,
        summary=" · ".join(summary_parts),
    )


def _max_severity(*svs: DriftSeverity) -> DriftSeverity:
    rank = {DriftSeverity.NONE: 0, DriftSeverity.MINOR: 1, DriftSeverity.MAJOR: 2}
    return max(svs, key=lambda s: rank[s])


# ──────────────────────────────────────────────────────────────────────
# KPI residual drift — use ADWIN on prediction errors
# ──────────────────────────────────────────────────────────────────────

def detect_residual_drift(predictions: list[float], actuals: list[float],
                            delta: float = 0.002) -> dict:
    """Run ADWIN over the residual stream. If drift detected,
    the model's accuracy has shifted and a retrain should be triggered."""
    adwin = ADWIN(delta=delta)
    drift_points = []
    for i, (p, a) in enumerate(zip(predictions, actuals)):
        residual = a - p
        if adwin.update(residual):
            drift_points.append(i)
    return {
        "drift_detected": len(drift_points) > 0,
        "drift_points": drift_points,
        "n_observations": len(predictions),
    }
