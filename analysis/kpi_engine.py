"""
KPI Engine — Phase 1

Computes the 5 KPIs defined in PROJECT_SPEC.md section 2, aggregated by
calendar week (Monday-start), directly from the transaction-level sales_raw
table produced by etl/load_source_data.py.
"""
from __future__ import annotations

import pandas as pd

KPI_COLUMNS = [
    "week_start", "revenue", "orders", "avg_order_value",
    "refund_rate", "new_customer_rate",
]


def _week_start(date_series: pd.Series) -> pd.Series:
    dt = pd.to_datetime(date_series)
    return (dt - pd.to_timedelta(dt.dt.weekday, unit="D")).dt.date


def compute_weekly_kpis(sales_raw: pd.DataFrame) -> pd.DataFrame:
    """KPI #1-5: Revenue, Orders, AOV, Refund Rate, New Customer Rate."""
    df = sales_raw.copy()
    df["week_start"] = _week_start(df["order_date"])

    weekly = df.groupby("week_start").agg(
        revenue=("revenue", "sum"),
        orders=("order_id", "nunique"),
        refund_amount=("refund_amount", "sum"),
    ).reset_index()

    weekly["avg_order_value"] = (weekly["revenue"] / weekly["orders"]).round(2)
    weekly["refund_rate"] = (weekly["refund_amount"] / weekly["revenue"]).round(4)

    new_customers = (
        df[df["customer_type"] == "New"]
        .groupby("week_start")["customer_id"].nunique()
    )
    all_customers = df.groupby("week_start")["customer_id"].nunique()

    weekly["new_customer_rate"] = (
        weekly["week_start"].map(new_customers).fillna(0)
        / weekly["week_start"].map(all_customers)
    ).round(4)

    weekly["revenue"] = weekly["revenue"].round(2)
    return weekly[KPI_COLUMNS].sort_values("week_start").reset_index(drop=True)


def compute_dimension_breakdown(
    sales_raw: pd.DataFrame, week_start, dimension: str
) -> pd.DataFrame:
    """
    Revenue/orders for one week, grouped by a single dimension
    (region / product_category / channel).

    This is a lightweight preview of the root-cause logic — full anomaly
    detection + multi-dimension drill-down is Phase 4. Here it's just used
    to give the LLM prompt more than one number ("what moved") in Phase 1.
    """
    df = sales_raw.copy()
    df["week_start"] = _week_start(df["order_date"])
    week_df = df[df["week_start"] == week_start]

    return (
        week_df.groupby(dimension)
        .agg(revenue=("revenue", "sum"), orders=("order_id", "nunique"))
        .round(2)
        .sort_values("revenue", ascending=False)
        .reset_index()
    )
