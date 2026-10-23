"""SOH source joins, selectors, and monthly snapshot calculations."""
from __future__ import annotations

from pathlib import Path
import logging
import re
from difflib import SequenceMatcher

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


def _store_code_lookup(stock: pd.DataFrame, warnings: list[str]) -> pd.DataFrame:
    """Resolve SOH retailer labels to canonical Adonis store codes."""
    try:
        master = execute_df("""
            select retailer_name as master_store, brand_code,
                   adonis_store_code as store_code
            from store_master.store_details
            where retailer_name is not null and adonis_store_code is not null
        """)
    except Exception:
        log.exception("Could not read Store Master mappings for SOH")
        stock["store_code"] = stock["store"]
        warnings.append("Store Master mapping could not be loaded; matching by retailer name.")
        return stock
    if master.empty:
        stock["store_code"] = stock["store"]
        warnings.append("Store Master has no store mappings; matching by retailer name.")
        return stock

    master = master.drop_duplicates().copy()
    master["_master_store"] = master["master_store"].map(_norm)
    master["_brand_code"] = master["brand_code"].map(_norm)
    master["store_code"] = master["store_code"].astype(str)
    brand_candidates = {
        code: part[["master_store", "_master_store", "store_code"]].drop_duplicates("store_code").to_dict("records")
        for code, part in master.groupby("_brand_code")
    }
    all_candidates = master[["master_store", "_master_store", "store_code"]].drop_duplicates("store_code").to_dict("records")

    resolved: dict[tuple[str, str], str] = {}
    missing = 0
    pairs = stock[["store", "brand_code"]].drop_duplicates()
    for _, row in pairs.iterrows():
        store_name, brand_code = str(row["store"]), _norm(row["brand_code"])
        store_norm = _norm(store_name)
        candidates = brand_candidates.get(brand_code, [])
        if candidates:
            exact = [item for item in candidates if item["_master_store"] == store_norm]
            if len(exact) == 1:
                chosen = exact[0]
            elif len(candidates) == 1:
                chosen = candidates[0]
            else:
                ranked = sorted(candidates, key=lambda item: SequenceMatcher(None, store_norm, item["_master_store"]).ratio(), reverse=True)
                best = SequenceMatcher(None, store_norm, ranked[0]["_master_store"]).ratio()
                second = SequenceMatcher(None, store_norm, ranked[1]["_master_store"]).ratio()
                chosen = ranked[0] if best >= 0.55 and best - second >= 0.08 else None
        else:
            exact = [item for item in all_candidates if item["_master_store"] == store_norm]
            ranked = sorted(all_candidates, key=lambda item: SequenceMatcher(None, store_norm, item["_master_store"]).ratio(), reverse=True)
            if len(exact) == 1:
                chosen = exact[0]
            elif len(ranked) > 1:
                best = SequenceMatcher(None, store_norm, ranked[0]["_master_store"]).ratio()
                second = SequenceMatcher(None, store_norm, ranked[1]["_master_store"]).ratio()
                chosen = ranked[0] if best >= 0.70 and best - second >= 0.10 else None
            else:
                chosen = None
        if chosen:
            resolved[(store_norm, brand_code)] = chosen["store_code"]

    # SOH often splits one retailer into gender-specific brand codes, while
    # Store Master has only one of those brand-code rows. Reuse the resolved
    # physical store code for the same SOH retailer label.
    by_name: dict[str, set[str]] = {}
    for (store_norm, _brand), store_code in resolved.items():
        by_name.setdefault(store_norm, set()).add(store_code)
    for _, row in pairs.iterrows():
        key = (_norm(row["store"]), _norm(row["brand_code"]))
        if key not in resolved:
            name_codes = by_name.get(key[0], set())
            if len(name_codes) == 1:
                resolved[key] = next(iter(name_codes))
    missing = sum((_norm(row["store"]), _norm(row["brand_code"])) not in resolved for _, row in pairs.iterrows())
    stock["store_code"] = [resolved.get((_norm(r.store), _norm(r.brand_code)), r.store) for r in stock.itertuples()]
    if missing:
        warnings.append(f"Store Master could not resolve {missing} SOH retailer/brand combinations; those rows use their retailer names.")
    return stock


def _merge_measures(
    stock: pd.DataFrame,
    source: pd.DataFrame,
    measures: list[str],
    label: str,
    warnings: list[str],
) -> pd.DataFrame:
    """Join on exact season, then use a unique SOH style season when needed."""
    match_keys = ["_store", "_brand_code", "_style", "_season"]
    style_keys = ["_store", "_brand_code", "_style"]
    if source.empty:
        for measure in measures:
            stock[measure] = 0
        warnings.append(f"No {label} records were found between the selected snapshots.")
        return stock

    for frame in (stock, source):
        frame["_store"] = frame["store_code"].map(_norm) if "store_code" in frame else frame["store"].map(_norm)
        frame["_brand_code"] = frame["brand_code"].map(_norm)
        frame["_style"] = frame["style"].map(_norm)
        frame["_season"] = frame["season"].map(_norm)
    source = source.groupby(match_keys, as_index=False)[measures].sum()
    source["_exact_match"] = True
    by_style = source.groupby(style_keys, as_index=False)[measures].sum()
    by_style["_style_match"] = True
    stock["_soh_season_count"] = stock.groupby(style_keys)["_season"].transform("nunique")
    stock = stock.merge(source, on=match_keys, how="left")
    stock = stock.merge(by_style, on=style_keys, how="left", suffixes=("", "_style_total"))
    unique_season = stock["_soh_season_count"] == 1
    matched = stock["_exact_match"].notna() | (unique_season & stock["_style_match"].notna())
    for measure in measures:
        style_total = f"{measure}_style_total"
        stock.loc[unique_season, measure] = stock.loc[unique_season, style_total]
    matched_rows = int(matched.sum())
    total_rows = len(stock)
    stock[measures] = stock[measures].fillna(0)
    stock = stock.drop(columns=match_keys + style_keys + [
        "_exact_match", "_style_match", "_soh_season_count",
        *[f"{m}_style_total" for m in measures],
    ])
    if matched_rows < total_rows:
        warnings.append(f"{label} matched {matched_rows:,} of {total_rows:,} SOH rows; unmatched rows show 0 {label.lower()}.")
    return stock


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
        return {"rows": [], "dates": get_dates(), "warnings": []}
    df[["opening_soh", "ending_soh"]] = df[["opening_soh", "ending_soh"]].fillna(0)
    if "end_soh_sizewise" not in df:
        df["end_soh_sizewise"] = ""
    warnings: list[str] = []
    df = _store_code_lookup(df, warnings)

    # Tertiary is the retailer's actual point-of-sale data. Positive quantities
    # are sales; negative lines are customer returns/reversals.
    try:
        tertiary = execute_df("""
            select adonis_store_code as store_code, brand_code, "Style_Code" as style,
                   "SEASON" as season,
                   sum(case when qty > 0 then qty else 0 end) as sale,
                   sum(case when qty < 0 then -qty else 0 end) as return_qty
            from tertiary_data.data
            where cast(date as date)>cast(? as date) and cast(date as date)<=cast(? as date)
            group by all
        """, [opening, ending])
    except Exception:
        log.exception("Could not read tertiary sales for SOH analysis")
        tertiary = pd.DataFrame(columns=["store", "brand_code", "style", "season", "sale", "return_qty"])
        warnings.append("Tertiary sales could not be loaded; sales measures are shown as 0.")
    if tertiary.empty and not any("Tertiary sales could not be loaded" in w for w in warnings):
        warnings.append("No tertiary sales were found between the selected snapshots.")
    df = _merge_measures(df, tertiary, ["sale", "return_qty"], "tertiary sales", warnings)

    # Secondary is warehouse-to-retailer movement: positive quantity is sent to
    # the retailer; negative quantity is returned from the retailer to WH.
    try:
        transfers = execute_df("""
            select adonis_store_code as store_code, brand_code, product_code_code as style,
                   season,
                   sum(case when qty > 0 then qty else 0 end) as transfer_in,
                   sum(case when qty < 0 then -qty else 0 end) as transfer_out
            from secondary_data.data
            where cast(bill_date as date)>cast(? as date) and cast(bill_date as date)<=cast(? as date)
            group by all
        """, [opening, ending])
    except Exception:
        log.exception("Could not read secondary stock transfers for SOH analysis")
        transfers = pd.DataFrame(columns=["store", "brand_code", "style", "season", "transfer_in", "transfer_out"])
        warnings.append("Secondary transfer data could not be loaded; transfer measures are shown as 0.")
    if transfers.empty and not any("Secondary transfer data could not be loaded" in w for w in warnings):
        warnings.append("No secondary stock transfers were found between the selected snapshots.")
    df = _merge_measures(df, transfers, ["transfer_in", "transfer_out"], "secondary transfers", warnings)

    df["net_sold"] = df.sale - df.return_qty
    style_keys = ["brand", "brand_code", "category", "style", "season"]
    df["total_style_sold"] = df.groupby(style_keys)["net_sold"].transform("sum")
    df["net_transfer"] = df.transfer_in - df.transfer_out
    df["available_stock"] = (df.opening_soh + df.net_transfer).clip(lower=0)
    df["st_pct"] = (df.net_sold / df.available_stock.replace(0, pd.NA)).clip(lower=0, upper=1).fillna(0)
    opening_available = df.opening_soh.clip(lower=0)
    opening_clearance_qty = df[["net_sold"]].clip(lower=0)["net_sold"].where(
        df.net_sold < opening_available, opening_available
    )
    df["opening_soh_clearance"] = (opening_clearance_qty / opening_available.replace(0, pd.NA)).fillna(0)
    df["net_stock_movement"] = df.ending_soh - df.opening_soh - df.net_transfer + df.net_sold
    return {
        "rows": df[df.st_pct <= threshold].drop(columns=["store_code"], errors="ignore").fillna(0).to_dict("records"),
        "dates": get_dates(),
        "warnings": warnings,
    }
