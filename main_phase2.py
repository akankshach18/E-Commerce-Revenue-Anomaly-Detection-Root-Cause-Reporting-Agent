"""
Phase 2 entrypoint: Excel -> MySQL -> weekly_kpis view -> Trend -> LLM -> Email.

Power BI is not called from this script — it's a parallel consumer that
reads the same sales_raw / weekly_kpis tables directly (see sql/ and the
implementation guide for the Power BI connection steps). That's the whole
point of Phase 2: one shared data layer, two independent outputs.

Everything from add_trend_columns() onward is copy-pasted from Phase 1's
main.py UNCHANGED — proof that swapping the data source didn't require
touching the trend/AI/email logic at all.

Run:
    export MYSQL_PASSWORD=your_password
    python main_phase2.py
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pandas as pd

from etl.load_to_mysql import get_engine, load_file_to_sql, load_marketing_spend, row_count
from analysis.trend_engine import add_trend_columns, latest_week_summary
from ai.generate_insight import build_insight_payload, generate_insight
from notifications.send_report import build_html, send_email, should_send_threshold_alert

DATA_DIR = Path(__file__).parent / "data"
FILES = [
    DATA_DIR / "ecommerce_sales_baseline_weeks1-12.xlsx",
    DATA_DIR / "ecommerce_sales_incremental_week13.xlsx",
    DATA_DIR / "ecommerce_sales_incremental_week14.xlsx",
    DATA_DIR / "ecommerce_sales_incremental_week15_ANOMALY.xlsx",
]
MARKETING_SPEND_FILE = DATA_DIR / "marketing_spend_weeks1-15.xlsx"


def region_breakdown_for_week(engine, week_start: dt.date) -> pd.DataFrame:
    """SQL-side equivalent of Phase 1's compute_dimension_breakdown() —
    pulls only the one week's rows instead of the whole table.

    Uses SQLAlchemy's text() with a named bind parameter (:week_start)
    rather than a driver-specific placeholder, so this keeps working if
    the underlying driver ever changes."""
    from sqlalchemy import text
    query = text("""
        SELECT region, SUM(revenue) AS revenue, COUNT(DISTINCT order_id) AS orders
        FROM sales_raw
        WHERE DATE_SUB(order_date, INTERVAL WEEKDAY(order_date) DAY) = :week_start
        GROUP BY region
        ORDER BY revenue DESC
    """)
    return pd.read_sql(query, engine, params={"week_start": week_start})


def main():
    engine = get_engine()

    for f in FILES:
        n = load_file_to_sql(str(f), engine)
        print(f"{f.name}: inserted {n} new rows (sales_raw total now {row_count(engine)})")

    n_spend = load_marketing_spend(str(MARKETING_SPEND_FILE), engine)
    print(f"{MARKETING_SPEND_FILE.name}: inserted {n_spend} new rows into marketing_spend")

    # This single query replaces Phase 1's compute_weekly_kpis() —
    # the aggregation now happens in MySQL, not pandas.
    weekly = pd.read_sql("SELECT * FROM weekly_kpis ORDER BY week_start", engine)
    weekly = add_trend_columns(weekly)
    summary = latest_week_summary(weekly)

    print(f"\nLatest week ({summary['week_start']}) trend: {summary['trend']}  "
          f"({summary['revenue_pct_change']}% WoW revenue)")

    week_start_date = dt.date.fromisoformat(summary["week_start"])
    region_breakdown = region_breakdown_for_week(engine, week_start_date)
    top_movers = {"revenue_by_region": region_breakdown.to_dict(orient="records")}

    payload = build_insight_payload(summary, top_movers=top_movers)
    insight_text = generate_insight(payload)

    print("\n--- Insight JSON ---")
    print(json.dumps(payload, indent=2, default=str))
    print("\n--- LLM Summary ---")
    print(insight_text)

    digest_html = build_html(payload, insight_text, is_alert=False)
    send_email(digest_html, subject="Weekly KPI Report")

    alert_needed, reasons = should_send_threshold_alert(summary)
    if alert_needed:
        alert_html = build_html(payload, insight_text, is_alert=True, alert_reasons=reasons)
        print(f"\n*** THRESHOLD ALERT TRIGGERED: {'; '.join(reasons)} ***")
        send_email(alert_html, subject="Threshold Alert - E-Commerce KPIs")


if __name__ == "__main__":
    main()
