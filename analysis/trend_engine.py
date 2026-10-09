"""
Trend Engine — Phase 1

Week-over-week trend classification per PROJECT_SPEC.md section 4
(primary rule). The secondary rule (z-score anomaly detection against a
trailing 8-week window, per region x product) is Phase 4 — deliberately
not implemented here, since the week15_ANOMALY test file's whole point is
that the *company-wide* WoW number should look mild while the localized
problem stays hidden until Phase 4's dimensional z-score exists.
"""
from __future__ import annotations

import pandas as pd

UP_THRESHOLD = 5.0
DOWN_THRESHOLD = -5.0


def add_trend_columns(weekly_kpis: pd.DataFrame) -> pd.DataFrame:
    df = weekly_kpis.sort_values("week_start").reset_index(drop=True).copy()

    df["revenue_pct_change"] = (df["revenue"].pct_change() * 100).round(2)
    df["orders_pct_change"] = (df["orders"].pct_change() * 100).round(2)
    df["aov_pct_change"] = (df["avg_order_value"].pct_change() * 100).round(2)

    def classify(pct: float) -> str:
        if pd.isna(pct):
            return "n/a (no prior week)"
        if pct > UP_THRESHOLD:
            return "up"
        if pct < DOWN_THRESHOLD:
            return "down"
        return "flat"

    df["trend"] = df["revenue_pct_change"].apply(classify)
    return df


def latest_week_summary(weekly_with_trend: pd.DataFrame) -> dict:
    """Flatten the most recent week's row (+ prior week context) into the
    shape the Insight JSON needs (guide section 5, Step 4)."""
    latest = weekly_with_trend.iloc[-1]
    prior = weekly_with_trend.iloc[-2] if len(weekly_with_trend) > 1 else None

    def _get(col, cast=float):
        """Optional columns (only present once Phase 2's expanded
        weekly_kpis view is the source) fall back to None gracefully so
        this function still works against Phase 1's 5-column KPI table."""
        if col not in latest.index or pd.isna(latest[col]):
            return None
        return cast(latest[col])

    return {
        "week_start": str(latest["week_start"]),
        "revenue": float(latest["revenue"]),
        "orders": int(latest["orders"]),
        "avg_order_value": float(latest["avg_order_value"]),
        "refund_rate": float(latest["refund_rate"]),
        "new_customer_rate": float(latest["new_customer_rate"]),
        "gross_profit": _get("gross_profit"),
        "gross_margin": _get("gross_margin"),
        "discount_rate": _get("discount_rate"),
        "repeat_purchase_rate": _get("repeat_purchase_rate"),
        "marketing_spend": _get("marketing_spend"),
        "cac": _get("cac"),
        "roas": _get("roas"),
        "revenue_pct_change": (
            None if pd.isna(latest["revenue_pct_change"])
            else float(latest["revenue_pct_change"])
        ),
        "trend": latest["trend"],
        "prior_week_start": None if prior is None else str(prior["week_start"]),
        "prior_revenue": None if prior is None else float(prior["revenue"]),
    }
