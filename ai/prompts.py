"""
Prompt templates — Phase 1

Kept separate from generate_insight.py so prompt iteration doesn't touch
the API-calling code (and so Phase 5's tool-calling agent can reuse
build_insight_prompt for on-demand Q&A too).
"""

SYSTEM_PROMPT = (
    "You are a senior business analyst producing a weekly executive summary "
    "for an e-commerce company. You write in plain, direct business English. "
    "You never invent numbers or causes that are not present in the data you "
    "are given — if a cause isn't evidenced by the data, say so plainly and "
    "recommend what to check next instead of guessing."
)


def build_insight_prompt(insight_payload: dict) -> str:
    return f"""Given this week's e-commerce KPI data (JSON below), write an executive
summary in at most 180 words, structured as:

1. **What happened** — headline KPI movement(s), stated with the actual numbers.
   The "kpis" object may include core metrics (revenue, orders, AOV, refund
   rate, new customer rate) and, when available, profitability and marketing
   metrics (gross_profit, gross_margin, discount_rate, repeat_purchase_rate,
   marketing_spend, cac, roas). Only discuss the fields actually present —
   don't assume a metric exists if it's missing from "kpis".
2. **Likely why** — based ONLY on the data provided (trend direction, refund
   rate, gross margin movement, discount rate, CAC/ROAS movement, and any
   region/product breakdown included). Do not speculate about causes that
   aren't evidenced in the data.
3. **Recommended action** — one concrete, specific next step.

Data:
{insight_payload}
"""
