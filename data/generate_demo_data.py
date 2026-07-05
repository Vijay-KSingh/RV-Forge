"""Generate a synthetic but realistic-looking revenue time series for the demo.

Output: data/raw/demo_revenue.csv with columns timestamp, value.
Two years of daily data with trend + weekly seasonality + a known anomaly
in month 14, so the demo can show both forecasting and anomaly detection
producing the right answers.
"""
import numpy as np
import pandas as pd
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "raw" / "demo_revenue.csv"
OUT.parent.mkdir(parents=True, exist_ok=True)

np.random.seed(42)
N_DAYS = 730
dates = pd.date_range("2024-01-01", periods=N_DAYS, freq="D")

# Components
trend = np.linspace(8000, 14000, N_DAYS)
weekly = 800 * np.sin(2 * np.pi * np.arange(N_DAYS) / 7)
yearly = 1500 * np.sin(2 * np.pi * np.arange(N_DAYS) / 365.25 + 1.2)
noise = np.random.normal(0, 400, N_DAYS)
values = trend + weekly + yearly + noise

# Inject a known anomaly: a 35% revenue drop spanning 5 days at day 420
values[420:425] *= 0.65

df = pd.DataFrame({
    "timestamp": dates,
    "value": values.round(2),
})
df.to_csv(OUT, index=False)
print(f"Wrote {len(df)} rows to {OUT}")
print(f"Date range: {df['timestamp'].min().date()} → {df['timestamp'].max().date()}")
print(f"Value range: {df['value'].min():,.0f} → {df['value'].max():,.0f}")
print(f"Injected anomaly: days 420-424 (around {dates[420].date()})")
