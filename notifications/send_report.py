"""
Email step — Phase 1 Step 6.

Implements the two-tier send policy from PROJECT_SPEC.md section 5:
  1. Weekly digest — always built for the latest week; caller decides
     whether "today" is the scheduled Monday send (that scheduling
     decision belongs to Phase 3's orchestrator, not this module).
  2. Threshold-triggered alert — sent immediately if the latest week's
     numbers cross a threshold, independent of the weekly schedule.

IMPORTANT — partial threshold implementation in Phase 1:
  The spec defines three alert conditions:
    (a) revenue WoW change beyond +/-10%
    (b) refund rate > 8%
    (c) any (region x product_category) z-score anomaly with |z| > 2
  Only (a) and (b) are checked here. (c) requires the z-score anomaly
  detector that is explicitly Phase 4 work (PROJECT_SPEC.md section 4,
  "secondary rule") and does not exist yet. should_send_threshold_alert()
  is written to be extended with a z-score input once that lands —
  see the TODO in that function.

send_email() reads credentials from environment variables so nothing
sensitive lives in code:
    EMAIL_FROM, EMAIL_TO, EMAIL_APP_PASSWORD,
    SMTP_HOST (default smtp.gmail.com), SMTP_PORT (default 465)
If those aren't all set, it prints the HTML instead of sending — this is
what lets the whole pipeline be tested end-to-end without a real mailbox.
"""
from __future__ import annotations

import os
import smtplib
from email.mime.text import MIMEText

REVENUE_WOW_ALERT_THRESHOLD = 10.0   # percent, PROJECT_SPEC.md section 5
REFUND_RATE_ALERT_THRESHOLD = 0.08   # 8%, PROJECT_SPEC.md section 5
GROSS_MARGIN_ALERT_FLOOR = 0.35      # NEW (v2): below this, profitability is at risk
                                      # even if revenue itself looks fine


def should_send_threshold_alert(kpi_summary: dict) -> tuple[bool, list[str]]:
    """
    Returns (should_alert, reasons). Checks conditions (a) and (b) from the
    spec. Condition (c) — region x product z-score anomaly — is Phase 4;
    once analysis/anomaly_detection.py exists, pass its output in here as
    an extra argument and append to `reasons` the same way.
    """
    reasons = []

    pct_change = kpi_summary.get("revenue_pct_change")
    if pct_change is not None and abs(pct_change) > REVENUE_WOW_ALERT_THRESHOLD:
        direction = "up" if pct_change > 0 else "down"
        reasons.append(f"Revenue WoW change is {pct_change}% ({direction} more than "
                        f"{REVENUE_WOW_ALERT_THRESHOLD}% threshold)")

    refund_rate = kpi_summary.get("refund_rate")
    if refund_rate is not None and refund_rate > REFUND_RATE_ALERT_THRESHOLD:
        reasons.append(f"Refund rate is {refund_rate:.2%} "
                        f"(above {REFUND_RATE_ALERT_THRESHOLD:.0%} threshold)")

    # NEW (v2): only present once reading from Phase 2's expanded weekly_kpis view.
    gross_margin = kpi_summary.get("gross_margin")
    if gross_margin is not None and gross_margin < GROSS_MARGIN_ALERT_FLOOR:
        reasons.append(f"Gross margin is {gross_margin:.2%} "
                        f"(below {GROSS_MARGIN_ALERT_FLOOR:.0%} floor)")

    # TODO (Phase 4): if anomalies: reasons.append(f"Anomaly detected in {...}: z={...}")

    return (len(reasons) > 0, reasons)


# NEW (v2): label + formatter for every KPI that can appear in the payload,
# so the table renders whatever's present (5 core KPIs from Phase 1, or all
# 12 once reading from Phase 2's expanded weekly_kpis view) without an
# if/elif per metric.
_KPI_DISPLAY = {
    "revenue":              ("Revenue", lambda v: f"${v:,.2f}"),
    "orders":                ("Orders", lambda v: f"{v:,}"),
    "avg_order_value":      ("Avg order value", lambda v: f"${v:,.2f}"),
    "refund_rate":          ("Refund rate", lambda v: f"{v:.2%}"),
    "new_customer_rate":    ("New customer rate", lambda v: f"{v:.2%}"),
    "gross_profit":         ("Gross profit", lambda v: f"${v:,.2f}"),
    "gross_margin":         ("Gross margin", lambda v: f"{v:.2%}"),
    "discount_rate":        ("Discount rate", lambda v: f"{v:.2%}"),
    "repeat_purchase_rate": ("Repeat purchase rate", lambda v: f"{v:.2%}"),
    "marketing_spend":      ("Marketing spend", lambda v: f"${v:,.2f}"),
    "cac":                   ("CAC", lambda v: f"${v:,.2f}"),
    "roas":                  ("ROAS", lambda v: f"{v:,.2f}x"),
}


def build_html(insight_payload: dict, summary_text: str, *, is_alert: bool,
                alert_reasons: list[str] | None = None) -> str:
    kpis = insight_payload["kpis"]
    title = "Weekly Business Insight" if not is_alert else "Threshold Alert — E-Commerce KPIs"
    trend = insight_payload["trend"]
    trend_color = {"up": "#0F6E56", "down": "#993C1D", "flat": "#5F5E5A"}.get(trend, "#5F5E5A")
    header_bg = "#FAECE7" if is_alert else "#E1F5EE"

    reasons_html = ""
    if is_alert and alert_reasons:
        items = "".join(f"<li>{r}</li>" for r in alert_reasons)
        reasons_html = f"<p><strong>Triggered by:</strong></p><ul>{items}</ul>"

    rows_html = "".join(
        f"<tr><td>{label}</td><td>{fmt(kpis[key])}</td></tr>"
        for key, (label, fmt) in _KPI_DISPLAY.items() if key in kpis
    )

    return f"""
<div style="background:{header_bg};padding:12px 16px;border-radius:6px;">
<h2 style="margin:0 0 6px;">{title}</h2>
<p style="margin:0;"><strong>Period:</strong> {insight_payload['period']} &nbsp;|&nbsp;
<strong>Trend:</strong> <span style="color:{trend_color};font-weight:bold;">{trend}</span> &nbsp;|&nbsp;
<strong>WoW Revenue Change:</strong> {insight_payload.get('revenue_pct_change_wow')}%</p>
</div>
{reasons_html}
<table cellpadding="6" cellspacing="0" border="1" style="border-collapse:collapse;margin-top:10px;">
  <tr style="background:#F1EFE8;"><th align="left">KPI</th><th align="left">Value</th></tr>
  {rows_html}
</table>
<h3>Executive Summary</h3>
<p>{summary_text}</p>
""".strip()


def send_email(html: str, subject: str, dry_run: bool = False) -> bool:
    """
    Sends the HTML email via SMTP_SSL. Returns True if actually sent.

    dry_run=True (or missing env vars) prints the HTML instead of sending —
    this is the default posture for local testing, matching how
    ai/generate_insight.py handles the missing-API-key case.
    """
    env_from = os.environ.get("EMAIL_FROM")
    env_to = os.environ.get("EMAIL_TO")
    env_pass = os.environ.get("EMAIL_APP_PASSWORD")
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "465"))

    if dry_run or not all([env_from, env_to, env_pass]):
        print(f"\n[DRY RUN — email not sent, set EMAIL_FROM/EMAIL_TO/EMAIL_APP_PASSWORD "
              f"to send for real]\nSubject: {subject}\n{html}\n")
        return False

    msg = MIMEText(html, "html")
    msg["Subject"] = subject
    msg["From"] = env_from
    msg["To"] = env_to

    with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
        server.login(env_from, env_pass)
        server.send_message(msg)
    return True
