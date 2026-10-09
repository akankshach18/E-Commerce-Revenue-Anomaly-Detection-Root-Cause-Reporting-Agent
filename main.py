"""
Phase 1 MVP entrypoint: Excel -> KPI Engine -> Trend Engine -> LLM -> Email.
No database yet — see PROJECT_SPEC.md / guide Phase 2 for that.

Simulates 4 pipeline runs on top of each other, exactly matching the test
plan in PROJECT_SPEC.md section 6:
  1. Baseline load        (weeks 1-12)
  2. Incremental load      week 13  (normal)
  3. Incremental load      week 14  (normal)
  4. Incremental load      week 15  (planted anomaly: West x Electronics)

Each run sends (or, without credentials, prints) a weekly digest email, and
additionally a threshold alert email if revenue WoW change or refund rate
crosses the limits in PROJECT_SPEC.md section 5.

Run:
    python main.py
        # LLM: dry-run unless ANTHROPIC_API_KEY is set
        # Email: printed to console unless EMAIL_FROM/EMAIL_TO/EMAIL_APP_PASSWORD are set

    ANTHROPIC_API_KEY=sk-... EMAIL_FROM=you@gmail.com EMAIL_TO=you@gmail.com \\
    EMAIL_APP_PASSWORD=xxxx python main.py
        # fully live: real LLM summary + real email sent
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from etl.load_source_data import incremental_merge
from analysis.kpi_engine import compute_weekly_kpis, compute_dimension_breakdown
from analysis.trend_engine import add_trend_columns, latest_week_summary
from ai.generate_insight import build_insight_payload, generate_insight
from notifications.send_report import build_html, send_email, should_send_threshold_alert

DATA_DIR = Path(__file__).parent / "data"
BASELINE_FILE = DATA_DIR / "ecommerce_sales_baseline_weeks1-12.xlsx"
INCREMENTAL_FILES = [
    DATA_DIR / "ecommerce_sales_incremental_week13.xlsx",
    DATA_DIR / "ecommerce_sales_incremental_week14.xlsx",
    DATA_DIR / "ecommerce_sales_incremental_week15_ANOMALY.xlsx",
]


def run_pipeline_step(sales_raw, label: str) -> dict:
    weekly = compute_weekly_kpis(sales_raw)
    weekly = add_trend_columns(weekly)
    summary = latest_week_summary(weekly)

    print(f"\n{'=' * 78}\nPIPELINE RUN: {label}   (sales_raw rows: {len(sales_raw):,})\n{'=' * 78}")
    print(weekly.tail(4).to_string(index=False))
    print(f"\nLatest week ({summary['week_start']}) trend: {summary['trend']}  "
          f"({summary['revenue_pct_change']}% WoW revenue)")

    # Give the LLM one extra layer of context: revenue by region for the
    # latest week. Full multi-dimension root-cause drill-down is Phase 4 —
    # this is just enough for Phase 1's prompt to reason over "what moved".
    week_start_date = dt.date.fromisoformat(summary["week_start"])
    region_breakdown = compute_dimension_breakdown(sales_raw, week_start_date, "region")
    top_movers = {"revenue_by_region": region_breakdown.to_dict(orient="records")}

    payload = build_insight_payload(summary, top_movers=top_movers)
    insight_text = generate_insight(payload)

    print("\n--- Insight JSON (sent to LLM) ---")
    print(json.dumps(payload, indent=2))
    print("\n--- LLM Summary ---")
    print(insight_text)

    # Step 6 — build + send the weekly digest (always) and a threshold
    # alert (only if it fires), per PROJECT_SPEC.md section 5.
    digest_html = build_html(payload, insight_text, is_alert=False)
    send_email(digest_html, subject="Weekly KPI Report")  # dry-run auto-falls-back if env vars unset

    alert_needed, reasons = should_send_threshold_alert(summary)
    if alert_needed:
        alert_html = build_html(payload, insight_text, is_alert=True, alert_reasons=reasons)
        print(f"\n*** THRESHOLD ALERT TRIGGERED: {'; '.join(reasons)} ***")
        send_email(alert_html, subject="Threshold Alert - E-Commerce KPIs")

    return summary


def main():
    sales_raw = incremental_merge(None, str(BASELINE_FILE))
    run_pipeline_step(sales_raw, "Baseline load (weeks 1-12)")

    for f in INCREMENTAL_FILES:
        sales_raw = incremental_merge(sales_raw, str(f))
        run_pipeline_step(sales_raw, f"Incremental load: {f.name}")


if __name__ == "__main__":
    main()
