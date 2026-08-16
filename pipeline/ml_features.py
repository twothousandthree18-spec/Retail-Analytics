"""Customer churn feature & target engineering for the Phase 6 ML layer.

Problem
-------
Binary customer churn prediction. A customer "churns" when they made at least
one purchase during an observation window but made no purchase during the
following label window.

Window design (time-aware, zero leakage)
----------------------------------------
* ``observation`` window  -- the only data used to compute features.
* ``label`` window        -- strictly *after* the observation window; the
  target is derived exclusively from this window. Features never see label
  data, so there is no temporal leakage by construction.

Two fixed windows used by the Phase 6 run:

* **W1 (train / validation)**  obs Dec-2010 .. May-2011,  label Jun-2011 .. Aug-2011
* **W2 (temporal test)**       obs Mar-2011 .. Aug-2011,  label Sep-2011 .. Nov-2011
  (model trained on W1 is applied to W2 without retraining -> out-of-time test)

Only rows with a non-null ``CustomerID`` are used; ``CustomerID`` is required
for a customer-level problem and cannot be imputed (no invented labels).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
CLEANED_CSV = REPO_ROOT / "data" / "cleaned_retail_data.csv"

DATE_FORMAT = "%y/%m/%d"


@dataclass(frozen=True)
class Window:
    """A (observation, label) pair of date ranges."""
    obs_start: date
    obs_end: date
    label_start: date
    label_end: date

    @property
    def obs_days(self) -> int:
        return (self.obs_end - self.obs_start).days + 1


# W1: train/validation, W2: temporal holdout test.
WINDOW_W1 = Window(date(2010, 12, 1), date(2011, 5, 31),
                   date(2011, 6, 1), date(2011, 8, 31))
WINDOW_W2 = Window(date(2011, 3, 1), date(2011, 8, 31),
                   date(2011, 9, 1), date(2011, 11, 30))

FEATURE_COLUMNS = [
    "recency_days",          # days since last purchase at obs_end
    "frequency",             # distinct invoices in observation window
    "monetary",              # total spend in observation window
    "tenure_days",           # days from first purchase to obs_end
    "avg_order_value",       # monetary / frequency
    "distinct_products",     # distinct stock codes
    "total_quantity",        # total units purchased
    "avg_items_per_order",   # total_quantity / frequency
    "avg_unit_price",        # revenue-weighted mean unit price
    "active_months",         # distinct calendar months with purchases
    "weekend_ratio",         # share of purchase rows on Sat/Sun
    "hour_mean",             # mean purchase hour
    "hour_std",              # std purchase hour (NaN for single-order)
    "gap_mean_days",         # mean days between order dates (NaN if <2 orders)
    "gap_std_days",          # std of inter-order gaps (NaN if <3 orders)
    "orders_last_30d",       # orders within 30 days before obs_end
    "is_uk",                 # 1 if United Kingdom, else 0
    "cohort_month",          # months from obs_start to first purchase
]


def load_cleaned(path: Path | str | None = None) -> pd.DataFrame:
    """Load the cleaned dataset with the analytic date parsed correctly."""
    df = pd.read_csv(Path(path) if path else CLEANED_CSV,
                     low_memory=False, dtype={"InvoiceNo": str, "StockCode": str})
    df["dt"] = pd.to_datetime(df["Invoice Date"], format=DATE_FORMAT, errors="coerce")
    df = df.dropna(subset=["CustomerID", "dt"])
    df["CustomerID"] = df["CustomerID"].astype("int64")
    return df


def _inter_order_gaps(order_days: np.ndarray) -> tuple[float, float]:
    """Mean / std of gaps between consecutive distinct order dates (in days)."""
    if len(order_days) < 2:
        return np.nan, np.nan
    gaps = np.diff(order_days)
    mean_gap = float(gaps.mean())
    std_gap = float(gaps.std()) if len(gaps) >= 2 else np.nan
    return mean_gap, std_gap


def build_features(df: pd.DataFrame, window: Window) -> pd.DataFrame:
    """Compute one row per customer using ONLY observation-window data.

    Leakage guard: rows are filtered to ``[obs_start, obs_end]`` before any
    aggregation; label-window rows are never touched here.
    """
    t0 = pd.Timestamp(window.obs_start)
    t1 = pd.Timestamp(window.obs_end)
    obs = df[(df["dt"] >= t0) & (df["dt"] <= t1)].copy()
    if obs.empty:
        raise ValueError(f"observation window {window.obs_start}..{window.obs_end} has no rows")

    obs["is_weekend"] = obs["dt"].dt.dayofweek >= 5

    def agg(group: pd.DataFrame) -> pd.Series:
        orders = np.sort(group["dt"].dt.normalize().unique())
        order_ts = (orders - np.datetime64(t1, "D")).astype("timedelta64[D]").astype(int)
        # recency: days since the MOST RECENT order (max order_ts is closest to end)
        recency = float(-np.max(order_ts))
        # orders_last_30d: orders strictly after (obs_end - 30 days)
        last30 = int(np.sum(order_ts >= -30))
        gap_mean, gap_std = _inter_order_gaps(
            (orders - np.datetime64(t0, "D")).astype("timedelta64[D]").astype(int))
        wm = float(group["TotalPrice"].sum() / group["Quantity"].sum()) if group["Quantity"].sum() else np.nan
        return pd.Series({
            "recency_days": recency,
            "frequency": int(group["InvoiceNo"].nunique()),
            "monetary": float(group["TotalPrice"].sum()),
            "tenure_days": float((np.datetime64(t1, "D") - np.datetime64(group["dt"].min(), "D"))
                                 / np.timedelta64(1, "D")),
            "distinct_products": int(group["StockCode"].nunique()),
            "total_quantity": float(group["Quantity"].sum()),
            "avg_unit_price": wm,
            "active_months": int(group["dt"].dt.to_period("M").nunique()),
            "weekend_ratio": float(group["is_weekend"].mean()),
            "hour_mean": float(group["Hour"].mean()),
            "hour_std": float(group["Hour"].std()),
            "gap_mean_days": gap_mean,
            "gap_std_days": gap_std,
            "orders_last_30d": last30,
        })

    feats = obs.groupby("CustomerID", sort=True).apply(agg, include_groups=False)
    feats = feats.reset_index()
    feats["avg_order_value"] = feats["monetary"] / feats["frequency"].replace(0, np.nan)
    feats["avg_items_per_order"] = feats["total_quantity"] / feats["frequency"].replace(0, np.nan)
    feats["is_uk"] = (obs.groupby("CustomerID")["Country"].first().reindex(feats["CustomerID"])
                      == "United Kingdom").astype(int).to_numpy()
    # cohort_month: calendar months from obs_start to the customer's first purchase
    first_month = obs.groupby("CustomerID")["dt"].min().dt.to_period("M").reindex(feats["CustomerID"])
    start_ym = t0.year * 12 + t0.month
    ym = first_month.dt.year * 12 + first_month.dt.month
    feats["cohort_month"] = (ym - start_ym).astype(int).fillna(0).to_numpy()

    feats = feats[["CustomerID"] + FEATURE_COLUMNS]
    return feats.reset_index(drop=True)


def build_target(df: pd.DataFrame, window: Window,
                 eligible: pd.DataFrame) -> pd.Series:
    """Churn label: 1 if eligible customer made no purchase in the label window.

    ``eligible`` is the observation-window feature frame (customer-level).
    """
    lt0 = pd.Timestamp(window.label_start)
    lt1 = pd.Timestamp(window.label_end)
    label_rows = df[(df["dt"] >= lt0) & (df["dt"] <= lt1)]
    buyers = set(label_rows["CustomerID"].unique())
    return eligible["CustomerID"].map(lambda c: int(c not in buyers))


def make_dataset(df: pd.DataFrame, window: Window) -> pd.DataFrame:
    """Features + churn target for one window (customer-level, no leakage)."""
    feats = build_features(df, window)
    target = build_target(df, window, feats)
    feats["churn"] = target.to_numpy()
    return feats


def featurize_frames(df: pd.DataFrame, window: Window) -> tuple[pd.DataFrame, pd.Series]:
    """Return (X with only FEATURE_COLUMNS, y) for a window."""
    feats = build_features(df, window)
    y = build_target(df, window, feats)
    X = feats[FEATURE_COLUMNS]
    return X, y.to_numpy()
