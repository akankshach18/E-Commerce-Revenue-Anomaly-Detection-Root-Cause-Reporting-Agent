"""
ETL loader — Phase 1 (Excel source, no DB yet).

Simulates the watermark-based incremental load described in PROJECT_SPEC.md
section 6: each new weekly Excel file is merged into a running in-memory
`sales_raw` table, de-duplicated by order_id, keeping only rows at or after
the current watermark (max order_date already loaded).

In Phase 2 this same watermark logic moves into the database side (a MySQL
`INSERT ... WHERE order_date > @watermark`-style pre-filter) — the function
signatures here are written so that swap is a drop-in replacement, not a
rewrite (see PROJECT_SPEC.md section 6 and the guide's Phase 2 section).
"""
from __future__ import annotations

import pandas as pd

REQUIRED_COLUMNS = [
    "order_id", "order_date", "region", "product_category", "channel",
    "customer_id", "customer_type", "units", "unit_price", "unit_cost",
    "discount_amount", "revenue", "refund_flag", "refund_amount",
]


def load_excel(path: str) -> pd.DataFrame:
    """Read one source Excel file and validate/clean it (Phase 1 Step 1)."""
    df = pd.read_excel(path, parse_dates=["order_date"])

    missing = set(REQUIRED_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"{path} is missing required columns: {sorted(missing)}")

    df = df.dropna(subset=["order_date", "revenue", "order_id"]).copy()
    df["order_date"] = pd.to_datetime(df["order_date"]).dt.date
    return df[REQUIRED_COLUMNS]


def incremental_merge(existing: pd.DataFrame | None, new_file: str) -> pd.DataFrame:
    """
    Append a new source file onto the running sales_raw table.

    - First call (existing is None): load everything, this is the baseline seed.
    - Subsequent calls: only accept incoming rows with order_date >= watermark
      (>= rather than > guards against a source day split across two file
      drops near a boundary), then de-dup on order_id as a belt-and-suspenders
      check since order_id is guaranteed unique.
    """
    new_df = load_excel(new_file)

    if existing is None or existing.empty:
        return new_df.drop_duplicates(subset="order_id").reset_index(drop=True)

    watermark = existing["order_date"].max()
    incoming = new_df[new_df["order_date"] >= watermark]

    combined = pd.concat([existing, incoming], ignore_index=True)
    combined = combined.drop_duplicates(subset="order_id").reset_index(drop=True)
    return combined


def load_full_history(file_paths: list[str]) -> pd.DataFrame:
    """Convenience wrapper: replay a list of files in chronological order."""
    sales_raw = None
    for path in file_paths:
        sales_raw = incremental_merge(sales_raw, path)
    return sales_raw
