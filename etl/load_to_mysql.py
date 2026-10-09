"""
ETL loader — Phase 2, MySQL.

Same logic Phase 1 used in-memory (reuses load_excel() unchanged, same
pre-filter-then-insert de-dup strategy), just pointed at a real MySQL
database via PyMySQL/SQLAlchemy instead of pandas.
"""
from __future__ import annotations

import os
import urllib.parse

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from etl.load_source_data import load_excel  # Phase 1's function, unchanged


def get_engine() -> Engine:
    """
    Reads connection details from environment variables:
        MYSQL_HOST     (default: localhost)
        MYSQL_PORT     (default: 3306)
        MYSQL_DATABASE (default: bi_db)
        MYSQL_USER     (default: root)
        MYSQL_PASSWORD (required)
    """
    host = os.environ.get("MYSQL_HOST", "localhost")
    port = os.environ.get("MYSQL_PORT", "3306")
    database = os.environ.get("MYSQL_DATABASE", "bi_db")
    user = os.environ.get("MYSQL_USER", "root")
    password = os.environ.get("MYSQL_PASSWORD")
    if not password:
        raise RuntimeError("MYSQL_PASSWORD environment variable is required")

    pwd_escaped = urllib.parse.quote_plus(password)
    url = f"mysql+pymysql://{user}:{pwd_escaped}@{host}:{port}/{database}"
    return create_engine(url)


def load_file_to_sql(path: str, engine: Engine) -> int:
    """
    Load one Excel file into sales_raw, inserting only rows whose
    order_id isn't already present. Returns count of rows actually
    inserted (0 on a pure re-run of an already-loaded file).
    """
    df = load_excel(path)

    existing = pd.read_sql("SELECT order_id FROM sales_raw", engine)["order_id"]
    new_rows = df[~df["order_id"].isin(set(existing))]

    if not new_rows.empty:
        new_rows.to_sql("sales_raw", engine, if_exists="append", index=False)
    return len(new_rows)


def row_count(engine: Engine) -> int:
    return int(pd.read_sql("SELECT COUNT(*) AS n FROM sales_raw", engine).iloc[0]["n"])


def load_marketing_spend(path: str, engine: Engine) -> int:
    """
    Loads the weekly (week_start, channel, spend) reference table used for
    CAC and ROAS. De-dup key is the natural key (week_start, channel) —
    a re-run skips rows already present for that week+channel.
    """
    df = pd.read_excel(path, parse_dates=["week_start"])
    df["week_start"] = pd.to_datetime(df["week_start"]).dt.date

    existing = pd.read_sql("SELECT week_start, channel FROM marketing_spend", engine)
    if not existing.empty:
        existing_keys = set(zip(existing["week_start"], existing["channel"]))
        new_rows = df[~df.apply(lambda r: (r["week_start"], r["channel"]) in existing_keys, axis=1)]
    else:
        new_rows = df

    if not new_rows.empty:
        new_rows.to_sql("marketing_spend", engine, if_exists="append", index=False)
    return len(new_rows)
