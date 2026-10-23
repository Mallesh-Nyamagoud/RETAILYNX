"""SOH source joins and monthly snapshot calculations."""
from __future__ import annotations

from pathlib import Path
import re

import duckdb
import pandas as pd

from app.core.config import BACKEND_DIR
from app.core.database import execute_df

SOH_DB = BACKEND_DIR / "data" / "soh_data_src.duckdb"


def _norm(value) -> str:
    """Comparison-only normalization shared by the SOH and sales sources."""
    return re.sub(r"\s+", "", str(value or "")).upper()


def get_dates() -> list[str]:
    if not SOH_DB.exists():
        return []
    with duckdb.connect(str(SOH_DB), read_only=True) as con:
        return [str(row[0])[:10] for row in con.execute(
            "select distinct cast(date as date) from data order by 1"
        ).fetchall()]


def get_summary(opening: str, ending: str, threshold: float = 1.0) -> dict:
    if not SOH_DB.exists():
        return {"rows": [], "dates": [], "message": "SOH source is missing."}
    with duckdb.connect(str(SOH_DB), read_only=True) as con:
        df = con.execute("""
            select name as store, brand, code as brand_code, gc as category,
                   pc9 as style, season,
                   sum(qty) filter(where cast(date as date)=cast(? as date)) opening_soh,
                   sum(qty) filter(where cast(date as date)=cast(? as date)) ending_soh,
                   string_agg(cast(correct_size as varchar)||'-'||cast(qty as varchar), ', ')
                     filter(where cast(date as date)=cast(? as date)) end_soh_sizewise,
                   max(mrp) mrp
            from data
            where cast(date as date) in(cast(? as date),cast(? as date))
            group by all
        """, [opening, ending, ending, opening, ending]).df()
    if df.empty:
        return {"rows": [], "dates": get_dates()}
    df[["opening_soh", "ending_soh"]] = df[["opening_soh", "ending_soh"]].fillna(0)

    # SOH.NAME maps to secondary_data.customer_name; SOH.CODE maps to
    # secondary_data.brand_code. Do not route this join through store_master:
    # the supplied master does not contain every retailer in the SOH extract.
    sales = execute_df("""
        select customer_name as store, brand_code, product_code_code as style,
               season,
               sum(qty) filter(where cast(bill_date as date)>cast(? as date)) as sale,
               sum(qty) as total_sale
        from secondary_data.data
        where cast(bill_date as date)<=cast(? as date)
        group by all
    """, [opening, ending])
    if sales.empty:
        df["sale"] = 0
        df["total_sale"] = 0
    else:
        for frame in (df, sales):
            frame["_store"] = frame["store"].map(_norm)
            frame["_brand_code"] = frame["brand_code"].map(_norm)
            frame["_style"] = frame["style"].map(_norm)
            frame["_season"] = frame["season"].map(_norm)
        sales = sales.groupby(
            ["_store", "_brand_code", "_style", "_season"], as_index=False
        )[["sale", "total_sale"]].sum()
        df = df.merge(
            sales, on=["_store", "_brand_code", "_style", "_season"], how="left"
        )
        df[["sale", "total_sale"]] = df[["sale", "total_sale"]].fillna(0)
        df = df.drop(columns=["_store", "_brand_code", "_style", "_season"])

    # Net movement is inferred from snapshots and sales; it is not a transfer ledger.
    df["transferred_between"] = df.ending_soh - df.opening_soh + df.sale
    available_stock = df.opening_soh + df.sale
    df["st_pct"] = (df.sale / available_stock.replace(0, pd.NA)).fillna(0)
    df["opening_soh_clearance"] = (
        df.sale / df.opening_soh.replace(0, pd.NA)
    ).fillna(0)
    return {
        "rows": df[df.st_pct <= threshold].fillna(0).to_dict("records"),
        "dates": get_dates(),
    }
