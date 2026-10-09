-- Phase 2 (v3) -- weekly_kpis view, MySQL version.
-- Requires MySQL 8.0+ (CTEs and window functions). Check with SELECT VERSION();
-- Both Python and Power BI (via a MySQL connector) read this same view, so
-- there's exactly one definition of every metric in the whole project.
USE bi_db;

CREATE OR REPLACE VIEW weekly_kpis AS
WITH weekly_base AS (
    SELECT
        -- MySQL's WEEKDAY() already returns 0=Monday..6=Sunday, so this is
        -- simpler than the SQL Server version (no +5 %7 offset needed).
        DATE_SUB(order_date, INTERVAL WEEKDAY(order_date) DAY) AS week_start,
        order_id,
        customer_id,
        customer_type,
        revenue,
        refund_amount,
        discount_amount,
        unit_cost * units AS cogs
    FROM sales_raw
),
weekly_agg AS (
    SELECT
        week_start,
        SUM(revenue)                                            AS revenue,
        COUNT(DISTINCT order_id)                                AS orders,
        ROUND(SUM(revenue) / COUNT(DISTINCT order_id), 2)       AS avg_order_value,
        ROUND(SUM(refund_amount) / NULLIF(SUM(revenue), 0), 4)  AS refund_rate,
        ROUND(
            COUNT(DISTINCT CASE WHEN customer_type = 'New' THEN customer_id END)
            / NULLIF(COUNT(DISTINCT customer_id), 0), 4
        )                                                        AS new_customer_rate,
        COUNT(DISTINCT CASE WHEN customer_type = 'New' THEN customer_id END) AS new_customers,
        SUM(revenue - cogs)                                     AS gross_profit,
        ROUND(SUM(revenue - cogs) / NULLIF(SUM(revenue), 0), 4) AS gross_margin,
        ROUND(
            SUM(discount_amount) / NULLIF(SUM(revenue + discount_amount), 0), 4
        )                                                        AS discount_rate
    FROM weekly_base
    GROUP BY week_start
),
-- Repeat purchase rate: of the customers who ordered THIS week, what
-- fraction had already ordered before their first-ever order date.
-- Computed from raw order history, not the customer_type label.
cust_orders AS (
    SELECT
        customer_id,
        order_date,
        DATE_SUB(order_date, INTERVAL WEEKDAY(order_date) DAY) AS week_start,
        MIN(order_date) OVER (PARTITION BY customer_id) AS first_order_date
    FROM sales_raw
),
repeat_agg AS (
    SELECT
        week_start,
        ROUND(
            COUNT(DISTINCT CASE WHEN order_date > first_order_date THEN customer_id END)
            / NULLIF(COUNT(DISTINCT customer_id), 0), 4
        ) AS repeat_purchase_rate
    FROM cust_orders
    GROUP BY week_start
),
spend_agg AS (
    SELECT week_start, SUM(spend) AS marketing_spend
    FROM marketing_spend
    GROUP BY week_start
)
SELECT
    a.week_start,
    a.revenue,
    a.orders,
    a.avg_order_value,
    a.refund_rate,
    a.new_customer_rate,
    a.gross_profit,
    a.gross_margin,
    a.discount_rate,
    r.repeat_purchase_rate,
    s.marketing_spend,
    CASE WHEN s.marketing_spend IS NULL OR a.new_customers = 0 THEN NULL
         ELSE ROUND(s.marketing_spend / a.new_customers, 2) END AS cac,
    CASE WHEN s.marketing_spend IS NULL OR s.marketing_spend = 0 THEN NULL
         ELSE ROUND(a.revenue / s.marketing_spend, 2) END AS roas
FROM weekly_agg a
LEFT JOIN repeat_agg r ON r.week_start = a.week_start
LEFT JOIN spend_agg s ON s.week_start = a.week_start
ORDER BY a.week_start;

-- Sanity check after loading data:
-- SELECT * FROM weekly_kpis;
