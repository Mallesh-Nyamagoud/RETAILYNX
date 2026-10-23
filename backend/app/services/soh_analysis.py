"""SOH source joins, selectors, and monthly snapshot calculations."""
from __future__ import annotations

from pathlib import Path
import logging
import re

import duckdb
import pandas as pd

from app.core.config import BACKEND_DIR
from app.core.database import execute_df

SOH_DB = BACKEND_DIR / "data" / "soh_data_src.duckdb"
log = logging.getLogger(__name__)
FILTER_FIELDS = {
    "store": "name",
    "brand": "brand",
    "category": "gc",
    "style": "pc9",
    "season": "season",
}


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


def get_filter_options() -> dict[str, list[str]]:
    if not SOH_DB.exists():
        return {key: [] for key in FILTER_FIELDS}
    options = {}
    with duckdb.connect(str(SOH_DB), read_only=True) as con:
        for key, column in FILTER_FIELDS.items():
            options[key] = [row[0] for row in con.execute(
                f"select distinct trim(cast({column} as varchar)) as option_value from data "
                f"where {column} is not null and trim(cast({column} as varchar))<>'' "
                "order by 1"
            ).fetchall()]
    return options


def get_summary(
    opening: str,
    ending: str,
    threshold: float = 1.0,
    filters: dict[str, str] | None = None,
) -> dict:
    if not SOH_DB.exists():
        return {"rows": [], "dates": [], "message": "SOH source is missing."}
    where = ["cast(date as date) in(cast(? as date),cast(? as date))"]
    params: list = [opening, ending, opening, ending]
    for key, column in FILTER_FIELDS.items():
        value = (filters or {}).get(key)
        if value:
            where.append(f"trim(cast({column} as varchar)) = ?")
            params.append(value)
    with duckdb.connect(str(SOH_DB), read_only=True) as con:
        df = con.execute(f"""
            select name as store, brand, code as brand_code, gc as category,
                   pc9 as style, season,
                   sum(qty) filter(where cast(date as date)=cast(? as date)) opening_soh,
                   sum(qty) filter(where cast(date as date)=cast(? as date)) ending_soh,
                   max(mrp) mrp
            from data where {' and '.join(where)} group by all
        """, params).df()
        size_where = ["cast(date as date)=cast(? as date)"]
        size_params = [ending]
        for key, column in FILTER_FIELDS.items():
            value = (filters or {}).get(key)
            if value:
                size_where.append(f"trim(cast({column} as varchar)) = ?")
                size_params.append(value)
        size_df = con.execute(f"""
            select store, brand, brand_code, category, style, season,
                   string_agg(cast(correct_size as varchar)||'-'||cast(size_qty as varchar), ', ' order by correct_size) end_soh_sizewise
            from (
                select name as store, brand, code as brand_code, gc as category,
                       pc9 as style, season, correct_size, sum(qty) as size_qty
                from data where {' and '.join(size_where)}
                group by all
            ) by_size
            group by all
        """, size_params).df()
        if not size_df.empty:
            df = df.merge(size_df, on=["store", "brand", "brand_code", "category", "style", "season"], how="left")
    if df.empty:
        return {"rows": [], "dates": get_dates()}
    df[["opening_soh", "ending_soh"]] = df[["opening_soh", "ending_soh"]].fillna(0)

    # SOH.NAME maps to secondary_data.customer_name; SOH.CODE maps to
    # secondary_data.brand_code. Match directly; the store master is incomplete.
    warnings = []
    sales_source_error = False
    try:
        sales = execute_df("""
            select customer_name as store, brand_code, product_code_code as style,
                   season,
                   sum(qty) filter(where upper(tran_type)='SALES' and cast(bill_date as date)>cast(? as date)) as sale,
                   sum(qty) filter(where upper(tran_type)='RETURN' and cast(bill_date as date)>cast(? as date)) as return_qty
            from secondary_data.data
            where cast(bill_date as date)<=cast(? as date)
            group by all
        """, [opening, opening, ending])
    except Exception:
        # SOH stock remains useful when the secondary sales attachment is
        # unavailable; return it with a visible warning instead of failing the
        # whole page with HTTP 500. The exception is retained in server logs.
        log.exception("Could not read secondary sales for SOH analysis")
        sales = pd.DataFrame(columns=["store", "brand_code", "style", "season", "sale", "return_qty"])
        sales_source_error = True

    if sales.empty:
        df["sale"] = 0
        df["return_qty"] = 0
        if sales_source_error:
            warnings.append("Secondary sales data could not be loaded; sales measures are shown as 0.")
        else:
            warnings.append("No secondary sales were found through the selected end month.")
    else:
        for frame in (df, sales):
            frame["_store"] = frame["store"].map(_norm)
            frame["_brand_code"] = frame["brand_code"].map(_norm)
            frame["_style"] = frame["style"].map(_norm)
            frame["_season"] = frame["season"].map(_norm)
        match_keys = ["_store", "_brand_code", "_style", "_season"]
        style_keys = ["_store", "_brand_code", "_style"]
        sales = sales.groupby(match_keys, as_index=False)[["sale", "return_qty"]].sum()
        sales["_sales_match"] = True
        # The billing workbook has no season field. Where its season enrichment
        # is blank, allow a store/brand/style fallback only if this SOH result
        # has exactly one season for that style. This recovers legitimate rows
        # without assigning sales ambiguously across multiple seasons.
        null_season_sales = sales[sales["_season"] == ""].groupby(
            style_keys, as_index=False
        )[["sale", "return_qty"]].sum().rename(columns={
            "sale": "_fallback_sale", "return_qty": "_fallback_return_qty",
        })
        null_season_sales["_fallback_match"] = True
        df["_soh_season_count"] = df.groupby(style_keys)["_season"].transform("nunique")
        df = df.merge(sales, on=match_keys, how="left")
        df = df.merge(null_season_sales, on=style_keys, how="left")
        fallback = df["_sales_match"].isna() & df["_fallback_match"].notna() & (df["_soh_season_count"] == 1)
        df.loc[fallback, "sale"] = df.loc[fallback, "_fallback_sale"]
        df.loc[fallback, "return_qty"] = df.loc[fallback, "_fallback_return_qty"]
        df.loc[fallback, "_sales_match"] = True
        matched_keys = int(df["_sales_match"].notna().sum())
        total_keys = len(df)
        df[["sale", "return_qty"]] = df[["sale", "return_qty"]].fillna(0)
        df = df.drop(columns=match_keys + style_keys + [
            "_sales_match", "_fallback_sale", "_fallback_return_qty",
            "_fallback_match", "_soh_season_count",
        ])
        if matched_keys < total_keys:
            warnings.append(
                f"Sales matched {matched_keys:,} of {total_keys:,} SOH rows. Blank-season billing rows use a unique store/brand/style fallback; unmatched rows show 0 sales."
            )

    df["net_sold"] = df.sale - df.return_qty
    style_keys = ["brand", "brand_code", "category", "style", "season"]
    df["total_style_sold"] = df.groupby(style_keys)["net_sold"].transform("sum")
    # No transfer ledger is supplied: this is net stock movement left
    # unexplained after billing, not a confirmed transfer quantity.
    df["net_stock_movement"] = df.ending_soh - df.opening_soh + df.net_sold
    sell_through_base = df.net_sold + df.ending_soh
    df["st_pct"] = (df.net_sold / sell_through_base.where(sell_through_base > 0)).fillna(0)
    df["opening_soh_clearance"] = (
        df.net_sold / df.opening_soh.replace(0, pd.NA)
    ).fillna(0)
    return {
        "rows": df[df.st_pct <= threshold].fillna(0).to_dict("records"),
        "dates": get_dates(),
        "warnings": warnings,
    }
