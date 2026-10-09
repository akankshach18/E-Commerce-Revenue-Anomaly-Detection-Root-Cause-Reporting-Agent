# PROJECT_SPEC.md
## AI-Powered BI Agent — E-Commerce Sales & Customer Performance

---

## 1. Business Scenario

**"Weekly E-Commerce Sales Performance & Root-Cause Alerting"**

An online retailer sells across 5 product categories, 5 regions, and 4 sales channels
(website, mobile app, marketplace, social commerce). Leadership wants a weekly automated
read on how the business is performing, with early warning when something breaks
(a channel outage, a regional stockout, a refund spike) — without anyone manually
opening a dashboard.

E-commerce was picked over a generic "sales" scenario because it naturally gives you:
- High transaction volume (good for trend/anomaly statistics to be meaningful)
- Multiple clean dimensions for root-cause breakdown (region x product x channel)
- Widely-understood KPIs that translate directly to a resume bullet
- A trending, recognizable use case for interviews ("I built an AI agent that monitors
  e-commerce KPIs and explains anomalies automatically")

---

## 2. KPIs (5)

| # | KPI | Formula | Why it matters |
|---|---|---|---|
| 1 | **Revenue** | `SUM(revenue)` | Top-line health |
| 2 | **Orders** | `COUNT(DISTINCT order_id)` | Volume / demand signal |
| 3 | **Average Order Value (AOV)** | `Revenue / Orders` | Basket-size trend, pricing/promo effect |
| 4 | **Refund Rate** | `SUM(refund_amount) / SUM(revenue)` | Product quality / fulfillment health |
| 5 | **New Customer Rate** | `COUNT(DISTINCT customer_id WHERE customer_type='New') / COUNT(DISTINCT customer_id)` | Acquisition vs. retention mix |

*(Conversion Rate is intentionally deferred — it requires a traffic/sessions source
that isn't in the order-level Excel export. Add it in a later phase if a
`daily_sessions_by_channel` table becomes available.)*

---

## 3. Excel / Source Structure

**Grain:** one row per **order** (transaction-level) — matches the guide's recommendation
so daily/weekly aggregation and dimensional root-cause breakdowns both work off the same table.

| Column | Type | Notes |
|---|---|---|
| `order_id` | string | Unique, e.g. `ORD-0001234` |
| `order_date` | date | Used for all time aggregation |
| `region` | string | North / South / East / West / Central |
| `product_category` | string | Electronics / Apparel / Home & Kitchen / Beauty & Personal Care / Sports & Outdoors |
| `channel` | string | Website / Mobile App / Marketplace / Social Commerce |
| `customer_id` | string | For new-vs-returning logic |
| `customer_type` | string | New / Returning (derived, but shipped pre-computed for simplicity) |
| `units` | int | Quantity in the order |
| `unit_price` | float | Price per unit |
| `revenue` | float | `units x unit_price` |
| `refund_flag` | bool | Whether any part of the order was refunded |
| `refund_amount` | float | Dollar amount refunded (0 if none) |

`region`, `product_category`, and `channel` are the three dimensions used for root-cause
breakdown in Phase 4 — exactly the pattern the guide describes.

---

## 4. Trend Rule

**Primary rule:** *week-over-week comparison*, matching the guide's Phase 1 default.

```
pct_change = (this_week_revenue - last_week_revenue) / last_week_revenue * 100
trend = "up"   if pct_change > 5
        "down" if pct_change < -5
        "flat" otherwise
```

**Secondary rule (Phase 4, for anomaly detection):** z-score against the trailing
8-week mean/stdev per (region x product_category) combination — this is what catches
a localized problem (e.g. one region/category pair breaking) that a single
company-wide week-over-week number would dilute and miss.

```
z = (week_revenue - rolling_8wk_mean) / rolling_8wk_std
anomaly = abs(z) > 2
```

---

## 5. Email Rule

Two-tier, so the inbox isn't noisy but nothing important is missed:

1. **Weekly digest** — every Monday 7am, regardless of performance. Always includes
   the 5 KPIs, WoW trend, and a one-paragraph LLM summary. (Keeps stakeholders in the
   habit of reading it even in a "flat" week.)
2. **Threshold-triggered alert** — sent immediately (outside the weekly schedule) if
   ANY of these fire on a given day's incremental load:
   - Revenue WoW change beyond +/-10%
   - Refund rate > 8% (baseline ~4%)
   - Any (region x product_category) z-score anomaly with |z| > 2

Both emails reuse the same Insight JSON -> LLM -> HTML pipeline; only the trigger
condition and subject line differ (`"Weekly KPI Report"` vs. `"Anomaly Alert: <metric>"`).

---

## 6. Incremental Data Strategy (how new data arrives / gets loaded)

Real companies don't hand you one static Excel file — new data shows up on a cadence.
This project simulates that with a **watermark-based incremental load**:

- `sales_raw.order_date` is the watermark column.
- Each ETL run does: `MAX(order_date)` already in the database -> only load source rows
  with `order_date > watermark` (or `order_id NOT IN (SELECT order_id FROM sales_raw)`
  as a belt-and-suspenders de-dup check, since `order_id` is unique).
- In production this "new file arriving" step is what Power Automate (Phase 3) watches
  for on OneDrive/SharePoint, or what Airflow polls for via a sensor.

**Test data provided (4 files):**

| File | Period | Purpose |
|---|---|---|
| `ecommerce_sales_baseline_weeks1-12.xlsx` | Weeks 1-12 (~20k rows) | Initial historical load — run once to seed `sales_raw` and give the z-score rolling window enough history |
| `ecommerce_sales_incremental_week13.xlsx` | Week 13 | Normal incremental load #1 |
| `ecommerce_sales_incremental_week14.xlsx` | Week 14 | Normal incremental load #2 |
| `ecommerce_sales_incremental_week15_ANOMALY.xlsx` | Week 15 | **Planted anomaly**: West region x Electronics has a simulated 3-day stockout (Wed-Fri) with order volume down ~75% and refund rate spiked to ~22% that window. West/Electronics weekly revenue drops from ~$42.3k (week 14) to ~$23.6k (week 15) — a ~44% localized drop that the company-wide number will mostly hide, which is exactly what root-cause breakdown is for. |

**How to test the whole pipeline with this data:**
1. Load `baseline` -> run Phase 1/2 pipeline -> confirm dashboard/email reflect ~12 weeks of history.
2. Load `week13` -> re-run -> confirm append-only load worked (row counts grew, no duplicates) and WoW trend is "flat/normal."
3. Load `week14` -> re-run -> same check.
4. Load `week15_ANOMALY` -> re-run -> this is the real test:
   - Company-wide revenue WoW change should look mild (the drop is diluted at the total level).
   - Z-score anomaly detection (Phase 4) should flag `(West, Electronics)` specifically.
   - Root-cause query grouped by region/product should surface West/Electronics as the driver.
   - Refund rate KPI should also cross the 8% alert threshold.
   - This should trigger the threshold-based alert email, not just the Monday digest.

---

## 7. Phase 1 Implementation Status

| Guide Step | File | Status |
|---|---|---|
| Step 1 — Load/clean Excel | `etl/load_source_data.py` | Done. Also implements the incremental watermark merge from section 6 (beyond what Phase 1 strictly requires, but needed to test the incremental files). |
| Step 2 — KPI Engine | `analysis/kpi_engine.py` | Done. All 5 KPIs from section 2, weekly grain. |
| Step 3 — Trend Engine | `analysis/trend_engine.py` | Done. WoW % change + up/flat/down per section 4's primary rule. |
| Step 4 — Insight JSON | `ai/generate_insight.py::build_insight_payload()` | Done. |
| Step 5 — LLM call | `ai/generate_insight.py::generate_insight()` | Code complete, model set to `claude-sonnet-5`. **Not yet verified against a live API call** — this sandbox has no `ANTHROPIC_API_KEY`, so only the dry-run path (payload construction, prompt formatting) has been tested. Run locally with a real key to confirm the actual model output before treating this as fully proven. |
| Step 6 — HTML email + send | `notifications/send_report.py`, wired into `main.py` | Done. Implements the two-tier policy from section 5: a weekly digest every run, plus a threshold alert when triggered. **Partial**: only checks revenue WoW (>±10%) and refund rate (>8%) — the third condition (region x product z-score anomaly) can't be checked yet because it depends on the Phase 4 anomaly detector, which doesn't exist yet. `should_send_threshold_alert()` has a `TODO` marking exactly where to plug that in. |

**Phase 1 is now functionally complete end-to-end** (Excel -> KPI -> Trend -> LLM -> Email), pending the live-API-key verification of Step 5 noted above.

### How to run it

```bash
cd bi-agent
pip install -r requirements.txt

# Dry run (no external calls, everything printed to console):
python main.py

# Fully live (real LLM summary + real email sent):
export ANTHROPIC_API_KEY=sk-ant-...
export EMAIL_FROM=you@gmail.com
export EMAIL_TO=you@gmail.com
export EMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx   # Gmail app password, not your login password
python main.py
```

`EMAIL_FROM`/`EMAIL_TO`/`EMAIL_APP_PASSWORD` must all be set or `send_email()` falls back to printing the HTML — same dry-run posture as the LLM call, so the pipeline is always testable without live credentials.

### Test results against the provided data (dry run)

Running `main.py` against the 4 provided files in sequence produced:

| Run | Latest week | Revenue WoW | Trend | Threshold alert fired? |
|---|---|---|---|---|
| Baseline (weeks 1-12) | 2026-07-20 | +6.29% | up | No |
| + week13 | 2026-07-27 | +1.04% | flat | No |
| + week14 | 2026-08-03 | +1.68% | flat | No |
| + week15 (ANOMALY) | 2026-08-10 | **-10.55%** | down | **Yes** — "Revenue WoW change is -10.55% (down more than 10.0% threshold)" |

This confirms the threshold-alert logic in Step 6 fires correctly on the planted anomaly. Note this is a **correction** to the original framing in section 6: the West/Electronics stockout was expected to be diluted and invisible at the company-wide level, requiring Phase 4's root-cause breakdown to surface it — in practice it dropped total weekly revenue enough (-10.55%) to trip the company-wide alert on its own. Root-cause breakdown is still needed to explain *why* (which dimension drove it), but the "hidden at the top level" framing wasn't accurate for this dataset.

### Known data-generation limitation

`new_customer_rate` collapses to 0.0000 from week 10 onward across all test files (baseline weeks 10-12, and all of weeks 13-15). This is a synthetic-data artifact — the generator's customer pool (6,000 IDs, ~35% new-customer draw rate) exhausts after roughly 9 weeks of the simulated order volume, not a bug in `kpi_engine.py` (verified correct against weeks 1-9, where it moves 100% -> 55% -> 43% -> ... as expected). If this KPI needs to stay meaningful for testing Phase 4/5 later, the data generator should be re-run with either a larger customer pool or an ongoing trickle of brand-new IDs each week.

### Environment variables reference

| Variable | Required for | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | Real LLM summaries | From console.anthropic.com. Without it, `generate_insight()` returns a dry-run payload dump instead of calling the API. |
| `EMAIL_FROM` | Sending real email | The sending mailbox address |
| `EMAIL_TO` | Sending real email | Recipient address (can be same as `EMAIL_FROM` for a self-alert) |
| `EMAIL_APP_PASSWORD` | Sending real email | An app-specific password (Gmail/Outlook), not the account login password |
| `SMTP_HOST` | Optional | Defaults to `smtp.gmail.com` |
| `SMTP_PORT` | Optional | Defaults to `465` |

---

## 8. Resume-Bullet Draft (fill in real numbers once built)

> Built an end-to-end AI-powered BI agent that ingests e-commerce transaction data,
> computes 12 KPIs (revenue, profitability, and marketing-efficiency metrics) across
> region/product/channel dimensions in MySQL, detects statistical anomalies (z-score),
> performs automated root-cause breakdown, and uses Claude to generate executive-ready
> natural-language summaries delivered via scheduled HTML email — orchestrated
> end-to-end with Apache Airflow alongside a live Power BI dashboard reading the same
> data layer.
