"""
LLM Insight Generation — Phase 1

Builds the Insight JSON (the contract between the data layer and the AI
layer — guide section 5, Step 4) and sends it to Gemini for a structured
executive summary.

Requires GEMINI_API_KEY in the environment. Without it (or with
dry_run=True), generate_insight() returns the payload it *would* have sent,
so the rest of the pipeline is fully testable offline.
"""
from __future__ import annotations

import json
import os

from ai.prompts import SYSTEM_PROMPT, build_insight_prompt

MODEL = "gemini-3.8-flash" # free-tier eligible; swap to "gemini-2.5-pro" for higher quality


def build_insight_payload(kpi_summary: dict, top_movers: dict | None = None) -> dict:
    # Core 5 KPIs are always present (Phase 1 or Phase 2). The expanded
    # KPIs (gross margin, discount rate, repeat purchase rate, CAC, ROAS)
    # are only there once the caller is reading from Phase 2's
    # weekly_kpis view — .get() keeps this payload builder working
    # against either source without a branch.
    kpis = {
        "revenue": kpi_summary["revenue"],
        "orders": kpi_summary["orders"],
        "avg_order_value": kpi_summary["avg_order_value"],
        "refund_rate": kpi_summary["refund_rate"],
        "new_customer_rate": kpi_summary["new_customer_rate"],
    }
    for extra in ("gross_profit", "gross_margin", "discount_rate",
                  "repeat_purchase_rate", "marketing_spend", "cac", "roas"):
        if kpi_summary.get(extra) is not None:
            kpis[extra] = kpi_summary[extra]

    payload = {
        "period": kpi_summary["week_start"],
        "kpis": kpis,
        "trend": kpi_summary["trend"],
        "revenue_pct_change_wow": kpi_summary["revenue_pct_change"],
        "prior_week": {
            "week_start": kpi_summary["prior_week_start"],
            "revenue": kpi_summary["prior_revenue"],
        },
    }
    if top_movers:
        payload["top_movers"] = top_movers
    return payload


def generate_insight(insight_payload: dict, dry_run: bool = False) -> str:
    """
    dry_run=True (or no GEMINI_API_KEY set) skips the real API call and
    returns the payload that would have been sent — lets you test/demo the
    whole pipeline without an API key or without burning free-tier quota.
    """
    if dry_run or not os.environ.get("GEMINI_API_KEY"):
        return (
            "[DRY RUN — set GEMINI_API_KEY to get a real summary] "
            f"Would call {MODEL} with this payload:\n"
            f"{json.dumps(insight_payload, indent=2)}"
        )

    from google import genai            # imported lazily so dry-run mode
    from google.genai import types      # works without the package installed

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    response = client.models.generate_content(
        model=MODEL,
        contents=build_insight_prompt(insight_payload),
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=400,
        ),
    )
    return response.text