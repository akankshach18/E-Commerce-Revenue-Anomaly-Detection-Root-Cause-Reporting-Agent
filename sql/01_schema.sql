-- Phase 2 -- schema for sales_raw (MySQL version)
-- Run this once against your existing MySQL server.
-- Works on MySQL 8.0+ (needed for the window function used in
-- 02_weekly_kpis_view.sql later -- check with: SELECT VERSION();

CREATE DATABASE IF NOT EXISTS bi_db;
USE bi_db;

CREATE TABLE IF NOT EXISTS sales_raw (
    order_id          VARCHAR(50)    NOT NULL PRIMARY KEY,  -- unique -> free de-dup on insert
    order_date        DATE           NOT NULL,
    region            VARCHAR(50)    NOT NULL,
    product_category  VARCHAR(50)    NOT NULL,
    channel           VARCHAR(50)    NOT NULL,
    customer_id       VARCHAR(50)    NOT NULL,
    customer_type     VARCHAR(20)    NOT NULL,               -- 'New' / 'Returning'
    units             INT            NOT NULL,
    unit_price        DECIMAL(10,2)  NOT NULL,
    unit_cost         DECIMAL(10,2)  NOT NULL DEFAULT 0,     -- COGS per unit, drives gross margin
    discount_amount   DECIMAL(12,2)  NOT NULL DEFAULT 0,     -- drives discount rate
    revenue           DECIMAL(12,2)  NOT NULL,               -- net of discount
    refund_flag       TINYINT(1)     NOT NULL,               -- MySQL has no BIT(1) boolean like SQL Server; TINYINT(1) is the standard MySQL boolean
    refund_amount     DECIMAL(12,2)  NOT NULL DEFAULT 0
);

-- Weekly marketing spend per channel, feeds CAC and ROAS. This is
-- reference/lookup data, not transaction data, so its "primary key" is the
-- natural key (week_start, channel) rather than a surrogate order_id.
CREATE TABLE IF NOT EXISTS marketing_spend (
    week_start  DATE           NOT NULL,
    channel     VARCHAR(50)    NOT NULL,
    spend       DECIMAL(12,2)  NOT NULL,
    PRIMARY KEY (week_start, channel)
);

-- Speeds up the weekly_kpis view's GROUP BY and the region/category
-- breakdown queries main_phase2.py runs for the LLM prompt.
CREATE INDEX ix_sales_raw_order_date ON sales_raw (order_date);
CREATE INDEX ix_sales_raw_region_category ON sales_raw (region, product_category);
CREATE INDEX ix_sales_raw_customer_date ON sales_raw (customer_id, order_date);  -- for repeat-purchase logic
