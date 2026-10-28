"""
Generic, schema-driven Sales Analysis engine.

Both "Secondary Billing Analysis" and "Tertiary Sales Analysis" (Modules I
and IV of the requirements doc) need the *exact* same shape of output - a
pivot table with a user-chosen, re-orderable set of dimensions plus:

    LFY FULL, LFYTD, CFYTD, GROWTH%, BALANCE, LFAPM, CFAPM, APM GROWTH%,
    TRENDING, PROJ.GROWTH%  (each in QTY and VAL)

...and both draw their dimension slicers (Retailer/Brand/Store
Type/Department/Group/State/Store Status) from the same place: whatever
columns currently exist on store_master.store_details. So this module is
written once, parameterised by which fact table/date column/qty & value
expressions to use, and is not aware of "secondary" vs "tertiary" at all.

APM denominators follow the active filter scope: overall, per brand,
per store, or per brand-store pair. Per-scope values are computed before
pivot rollups so every subtotal and grand total stays consistent.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from typing import Any

import pandas as pd

from app.core.config import FY_START_MONTH
from app.core.database import (
    cache_token,
    column_exists,
    execute,
    execute_df,
    filter_key,
    quote_ident,
)
from app.services.fy import build_fy_context, safe_div, safe_growth, safe_pct

# Columns on store_master.store_details that are eligible to be used as
# analysis dimensions / slicers. Discovered dynamically - nothing here is a
# hard business assumption, it is simply "which columns look categorical".
_EXCLUDED_DIMENSION_COLUMNS = {
    "adonis_store_code",
    "brand_code",
    "ter_min_date",
    "ter_max_date",
}
_DIMENSION_ELIGIBLE_TYPES = {"VARCHAR", "BIGINT", "INTEGER", "BOOLEAN"}


@dataclass(frozen=True)
class FactSpec:
    """Describes one fact table for the generic pivot engine."""

    schema: str
    table: str
    date_column: str
    qty_expr: str  # raw SQL expression, validated columns only
    val_expr: str  # raw SQL expression evaluated as the "taxable/bill value"
    brand_column: str = "brand_code"
    store_column: str = "adonis_store_code"


@lru_cache(maxsize=1)
def _dimension_catalog_cached() -> tuple[tuple[str, str, str], ...]:
    """(column, label, type) for every pivot dimension / slicer.

    The `store_details` column set is fixed for the process lifetime, so this
    catalog is read from `information_schema` exactly once instead of on every
    catalog / slicer / validation call.
    """
    rows = execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_catalog='store_master' AND table_name='store_details' "
        "ORDER BY ordinal_position"
    )
    out: list[tuple[str, str, str]] = []
    for name, dtype in rows:
        if name in _EXCLUDED_DIMENSION_COLUMNS:
            continue
        if dtype not in _DIMENSION_ELIGIBLE_TYPES:
            continue
        out.append((name, _prettify(name), dtype))
    return tuple(out)


def get_dimension_catalog() -> list[dict]:
    """Every column on store_master.store_details that can be used as a
    pivot dimension / slicer, discovered live from the schema.

    Served from the memoised catalog above (fresh dicts every call, so callers
    can never mutate the cached tuples)."""
    return [{"column": col, "label": label, "type": dtype} for col, label, dtype in _dimension_catalog_cached()]


def _prettify(col: str) -> str:
    return col.replace("_", " ").upper()


def _validate_dimensions(dims: list[str]) -> list[str]:
    valid = {d["column"] for d in get_dimension_catalog()}
    bad = [d for d in dims if d not in valid]
    if bad:
        raise ValueError(f"Unknown/ineligible dimension(s): {bad}")
    return dims


def _distinct_values(column: str) -> list[str]:
    if not column_exists("store_master", "store_details", column):
        raise ValueError(f"Unknown filter column: {column}")
    col = quote_ident(column)
    rows = execute(
        f"SELECT DISTINCT {col} FROM store_master.store_details "
        f"WHERE {col} IS NOT NULL ORDER BY 1"
    )
    return [r[0] for r in rows]


def get_slicer_options() -> dict[str, list[str]]:
    """Cross-request memoised distinct values per dimension column.

    Keyed on the data token, so a Store-Master edit / status recompute rebuilds
    it and nothing else does - the payload is identical to the old per-request
    `_distinct_values` loop.
    """
    return {col: list(values) for col, values in _slicer_options_cached(cache_token())}


@lru_cache(maxsize=8)
def _slicer_options_cached(_token: tuple) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Body of `get_slicer_options` (the `_token` argument is the cache key)."""
    out: list[tuple[str, tuple[str, ...]]] = []
    for d in get_dimension_catalog():
        col = quote_ident(d["column"])
        rows = execute(
            f"SELECT DISTINCT {col} FROM store_master.store_details "
            f"WHERE {col} IS NOT NULL ORDER BY 1"
        )
        out.append((d["column"], tuple(r[0] for r in rows)))
    return tuple(out)


def _get_global_max_date(fact: FactSpec) -> date | None:
    """MAX(date) of the fact table, memoised on the data token (this was one
    extra full-table aggregate on every pivot / bill request)."""
    return _global_max_date_cached(fact, cache_token())


@lru_cache(maxsize=8)
def _global_max_date_cached(fact: FactSpec, _token: tuple) -> date | None:
    row = execute(f"SELECT MAX({quote_ident(fact.date_column)}) FROM {fact.schema}.{fact.table}")
    val = row[0][0] if row else None
    if val is None:
        return None
    return val.date() if hasattr(val, "date") else val


def _fiscal_month_index(m: int) -> int:
    """Map a calendar month to its index inside the FY (April=1 ... March=12)."""
    if m >= FY_START_MONTH:
        return m - FY_START_MONTH + 1
    return m + (12 - FY_START_MONTH) + 1


def _apm_run_months(first_ts) -> int:
    """Number of months from the month containing `first_ts` through the FY-end
    month (March) - the LFY (prior-year) APM annualisation period.

    A first sale in August -> 8 (Aug..Mar), in April -> 12, in March -> 1.
    No sales in the window -> 0 months (and thus 0 APM)."""
    if first_ts is None or pd.isna(first_ts):
        return 0
    return (12 - _fiscal_month_index(first_ts.month)) + 1


def _apm_elapsed_months(ts) -> int:
    """Number of months that have elapsed in the financial year as of the month
    containing `ts` (April=1 ... March=12). This is the denominator for CFAPM
    ("CFYTD / months elapsed in the current FY" per the README / module doc).

    Data through July -> 4 (Apr..Jul), through December -> 9, through March -> 12.
    A combination with no sales in the FY window -> 0 (and thus 0 APM).
    """
    if ts is None or pd.isna(ts):
        return 0
    return _fiscal_month_index(ts.month)


def _apm_month_map(fact: FactSpec, fy, filters: dict[str, list[str]]) -> pd.DataFrame:
    """Month denominators for the overall or selected Brand/Store scope."""
    return _apm_month_map_cached(fact, fy, filter_key(filters), cache_token())


@lru_cache(maxsize=32)
def _apm_month_map_cached(
    fact: FactSpec, fy, filters_key: tuple, _token: tuple
) -> pd.DataFrame:
    """Active month denominators at the selected overall/brand/store scope."""
    filters = {col: list(values) for col, values in filters_key}
    filter_sql, filter_params = _build_filter_sql(filters)
    store_q = quote_ident(fact.store_column)
    brand_q = quote_ident(fact.brand_column)
    date_q = quote_ident(fact.date_column)

    selected = {str(k).lower() for k, values in filters.items() if values}
    brand_scope = any("brand" in key for key in selected)
    store_scope = any(key in {fact.store_column.lower(), "store_code", "store_name"} for key in selected)
    scope_cols = []
    if brand_scope:
        scope_cols.append("brand_code")
    if store_scope:
        scope_cols.append("store_code")
    select_scope = (", ".join(scope_cols) + ",") if scope_cols else "1 AS _scope,"
    group_scope = ", ".join(scope_cols) if scope_cols else "1"

    sql = f"""
    WITH j AS (
        SELECT f.{store_q} AS store_code, f.{brand_q} AS brand_code,
               f.{date_q} AS tx_date
        FROM {fact.schema}.{fact.table} f
        LEFT JOIN store_master.store_details dim
          ON f.{store_q} = dim.adonis_store_code AND f.{brand_q} = dim.brand_code
        WHERE 1=1 {filter_sql}
          AND f.{date_q} BETWEEN ?::DATE AND ?::DATE
    )
    SELECT {select_scope}
      MIN(CASE WHEN tx_date BETWEEN ?::DATE AND ?::DATE THEN tx_date END) AS cf_first,
      MIN(CASE WHEN tx_date BETWEEN ?::DATE AND ?::DATE THEN tx_date END) AS pf_first,
      MIN(CASE WHEN tx_date BETWEEN ?::DATE AND ?::DATE THEN tx_date END) AS lfytd_first
    FROM j GROUP BY {group_scope}
    """
    params = (filter_params + [fy.last_fy_start, fy.current_fy_end]
              + [fy.current_fy_start, fy.current_fy_end]
              + [fy.last_fy_start, fy.last_fy_end]
              + [fy.last_fy_start, fy.lfy_ytd_end])
    df = execute_df(sql, params)
    if df.empty:
        return df
    for col in ("cf_first", "pf_first", "lfytd_first"):
        df[col] = pd.to_datetime(df[col])

    def active_months(first, end):
        if first is None or pd.isna(first):
            return 0
        return max(0, _fiscal_month_index(end.month) - _fiscal_month_index(first.month) + 1)

    # The unfiltered annual total is always a simple 12-month average. YTD
    # overall denominators are the elapsed fiscal months in each YTD window.
    if not scope_cols:
        df["months_pf"] = 12
        df["months_cf"] = _fiscal_month_index(fy.max_date.month)
        df["months_lfytd"] = _fiscal_month_index(fy.lfy_ytd_end.month)
    else:
        df["months_pf"] = df["pf_first"].apply(_apm_run_months)
        df["months_cf"] = df["cf_first"].apply(lambda d: active_months(d, fy.max_date))
        df["months_lfytd"] = df["lfytd_first"].apply(lambda d: active_months(d, fy.lfy_ytd_end))
    return df[scope_cols + ["months_cf", "months_pf", "months_lfytd"]]

def _build_filter_sql(filters: dict[str, list[str]]) -> tuple[str, list[Any]]:
    clauses, params = [], []
    for col, values in (filters or {}).items():
        if not values:
            continue
        if not column_exists("store_master", "store_details", col):
            raise ValueError(f"Unknown filter column: {col}")
        placeholders = ",".join(["?"] * len(values))
        clauses.append(f"dim.{quote_ident(col)} IN ({placeholders})")
        params.extend(values)
    if not clauses:
        return "", []
    return " AND " + " AND ".join(clauses), params


def run_pivot(fact: FactSpec, dimensions: list[str], filters: dict[str, list[str]]) -> dict:
    """Pivot / rollup payload for the selected dimension hierarchy.

    Memoised on (fact, dimension order, filters, data token) - the pivot is the
    most-hit endpoint in the app (it renders the grid AND every KPI card), and
    identical view states (re-mounts, React StrictMode double-render, toggling a
    slicer back, Excel export right after a page render) now cost a dict lookup
    instead of a full fact-table aggregate.  The key is normalised (sorted
    filter keys/values, dimension order preserved), which cannot change the
    result: filters are AND-ed `IN (...)` clauses and dimension order is kept
    exactly as sent, so the payload is byte-identical to the un-memoised run.
    """
    return _pivot_cached(fact, tuple(dimensions or []), filter_key(filters), cache_token())


@lru_cache(maxsize=64)
def _pivot_cached(fact: FactSpec, dims_key: tuple, filters_key: tuple, _token: tuple) -> dict:
    """Body of `run_pivot` (the `_token` argument is the cache key only)."""
    dims = _validate_dimensions(list(dims_key))
    filters = {col: list(values) for col, values in filters_key}
    max_date = _get_global_max_date(fact)
    if max_date is None:
        return {"rows": [], "columns": _pivot_column_meta(dims), "fy_context": None}

    fy = build_fy_context(max_date)
    filter_sql, filter_params = _build_filter_sql(filters)

    dim_select = ", ".join(f"dim.{quote_ident(d)} AS {quote_ident(d)}" for d in dims) or ""
    dim_group_fine = ", ".join(
        quote_ident(d) for d in dims + ["brand_code", "fine_store"]
    ) or "brand_code, fine_store"

    base_sql = f"""
    WITH dim_joined AS (
        SELECT
            f.{quote_ident(fact.date_column)} AS tx_date,
            f.{quote_ident(fact.brand_column)} AS brand_code,
            f.{quote_ident(fact.store_column)} AS fine_store,
            ({fact.qty_expr}) AS qty_val,
            ({fact.val_expr}) AS val_val,
            {"" if not dims else dim_select + ","}
            1 AS _one
        FROM {fact.schema}.{fact.table} f
        LEFT JOIN store_master.store_details dim
            ON f.{quote_ident(fact.store_column)} = dim.adonis_store_code
           AND f.{quote_ident(fact.brand_column)} = dim.brand_code
        WHERE 1=1 {filter_sql}
    ),
    fine AS (
        SELECT
            {("" if not dims else ", ".join(quote_ident(d) for d in dims) + ",")}
            brand_code,
            fine_store,
            SUM(CASE WHEN tx_date BETWEEN ?::DATE AND ?::DATE THEN qty_val ELSE 0 END) AS lfy_full_qty,
            SUM(CASE WHEN tx_date BETWEEN ?::DATE AND ?::DATE THEN val_val ELSE 0 END) AS lfy_full_val,
            SUM(CASE WHEN tx_date BETWEEN ?::DATE AND ?::DATE THEN qty_val ELSE 0 END) AS lfytd_qty,
            SUM(CASE WHEN tx_date BETWEEN ?::DATE AND ?::DATE THEN val_val ELSE 0 END) AS lfytd_val,
            SUM(CASE WHEN tx_date >= ?::DATE THEN qty_val ELSE 0 END) AS cfytd_qty,
            SUM(CASE WHEN tx_date >= ?::DATE THEN val_val ELSE 0 END) AS cfytd_val
        FROM dim_joined
        GROUP BY {dim_group_fine}
    )
    SELECT * FROM fine
    """

    params = (
        filter_params
        + [fy.last_fy_start, fy.last_fy_end, fy.last_fy_start, fy.last_fy_end]
        + [fy.last_fy_start, fy.lfy_ytd_end, fy.last_fy_start, fy.lfy_ytd_end]
        + [fy.current_fy_start, fy.current_fy_start]
    )
    fine_df = execute_df(base_sql, params)

    if fine_df.empty:
        return {"rows": [], "columns": _pivot_column_meta(dims), "fy_context": fy.to_dict()}

    brand_months = _apm_month_map(fact, fy, filters)
    if not brand_months.empty:
        selected = {str(k).lower() for k, values in filters.items() if values}
        apm_keys = []
        if any("brand" in key for key in selected):
            apm_keys.append("brand_code")
        if any(key in {fact.store_column.lower(), "store_code", "store_name"} for key in selected):
            fine_df["store_code"] = fine_df["fine_store"]
            apm_keys.append("store_code")
        if apm_keys:
            fine_df = fine_df.merge(brand_months, on=apm_keys, how="left")
        else:
            for col in ("months_cf", "months_pf", "months_lfytd"):
                fine_df[col] = brand_months.iloc[0][col]
    else:
        fine_df["months_cf"] = fine_df["months_pf"] = fine_df["months_lfytd"] = 0
    fine_df["months_cf"] = fine_df["months_cf"].fillna(0)
    fine_df["months_pf"] = fine_df["months_pf"].fillna(0)
    fine_df["months_lfytd"] = fine_df["months_lfytd"].fillna(0)

    # Annualise at the selected scope: overall, brand, store, or brand/store.
    fine_df["brand_apm_qty"] = fine_df.apply(
        lambda r: safe_div(r["cfytd_qty"], r["months_cf"]), axis=1
    )
    fine_df["brand_apm_val"] = fine_df.apply(
        lambda r: safe_div(r["cfytd_val"], r["months_cf"]), axis=1
    )
    fine_df["pf_apm_qty"] = fine_df.apply(
        lambda r: safe_div(r["lfy_full_qty"], r["months_pf"]), axis=1
    )
    fine_df["pf_apm_val"] = fine_df.apply(
        lambda r: safe_div(r["lfy_full_val"], r["months_pf"]), axis=1
    )
    fine_df["lfytd_apm_qty"] = fine_df.apply(
        lambda r: safe_div(r["lfytd_qty"], r["months_lfytd"]), axis=1
    )
    fine_df["lfytd_apm_val"] = fine_df.apply(
        lambda r: safe_div(r["lfytd_val"], r["months_lfytd"]), axis=1
    )

    if dims:
        rollup_rows = _rollup(fine_df, dims)
    else:
        rollup_rows = pd.DataFrame(
            [
                {
                    "lfy_full_qty": fine_df["lfy_full_qty"].sum(),
                    "lfy_full_val": fine_df["lfy_full_val"].sum(),
                    "lfytd_qty": fine_df["lfytd_qty"].sum(),
                    "lfytd_val": fine_df["lfytd_val"].sum(),
                    "cfytd_qty": fine_df["cfytd_qty"].sum(),
                    "cfytd_val": fine_df["cfytd_val"].sum(),
                    "cfapm_qty": float(fine_df["brand_apm_qty"].sum()),
                    "cfapm_val": float(fine_df["brand_apm_val"].sum()),
                    "pfapm_qty": float(fine_df["pf_apm_qty"].sum()),
                    "pfapm_val": float(fine_df["pf_apm_val"].sum()),
                    "lfytd_apm_qty": float(fine_df["lfytd_apm_qty"].sum()),
                    "lfytd_apm_val": float(fine_df["lfytd_apm_val"].sum()),
                    "_level": 0,
                    "_is_total": True,
                }
            ]
        )

    rows = _finalise_measures(rollup_rows, fy, dims)
    return {"rows": rows, "columns": _pivot_column_meta(dims), "fy_context": fy.to_dict()}


def _rollup(fine_df: pd.DataFrame, dims: list[str]) -> pd.DataFrame:
    agg_map = {
        "lfy_full_qty": "sum",
        "lfy_full_val": "sum",
        "lfytd_qty": "sum",
        "lfytd_val": "sum",
        "cfytd_qty": "sum",
        "cfytd_val": "sum",
        "brand_apm_qty": "sum",
        "brand_apm_val": "sum",
        "pf_apm_qty": "sum",
        "pf_apm_val": "sum",
        "lfytd_apm_qty": "sum",
        "lfytd_apm_val": "sum",
    }
    frames = []
    # Detail level = full dimension grain (grouped, brand_code collapsed)
    for level in range(len(dims), -1, -1):
        group_cols = dims[:level]
        if group_cols:
            g = fine_df.groupby(group_cols, dropna=False, as_index=False).agg(agg_map)
        else:
            g = fine_df.agg(agg_map).to_frame().T
        for d in dims:
            if d not in group_cols:
                g[d] = None
        g["_level"] = level
        g["_is_total"] = level == 0
        frames.append(g)
    out = pd.concat(frames, ignore_index=True)
    out = out.rename(
        columns={
            "brand_apm_qty": "cfapm_qty",
            "brand_apm_val": "cfapm_val",
            "pf_apm_qty": "pfapm_qty",
            "pf_apm_val": "pfapm_val",
        }
    )
    sort_cols = dims
    out = out.sort_values(
        by=sort_cols, na_position="last", kind="stable"
    ).reset_index(drop=True)
    return out


def _finalise_measures(df: pd.DataFrame, fy, dims: list[str]) -> list[dict]:
    df = df.copy()
    df["growth_pct_qty"] = df.apply(
        lambda r: safe_growth(r["cfytd_qty"], r["lfytd_qty"]), axis=1
    )
    df["growth_pct_val"] = df.apply(
        lambda r: safe_growth(r["cfytd_val"], r["lfytd_val"]), axis=1
    )
    df["balance_qty"] = df["lfy_full_qty"] - df["cfytd_qty"]
    df["balance_val"] = df["lfy_full_val"] - df["cfytd_val"]
    # Map the prior-FY APM field to LFAPM; the selected-scope denominator
    # was applied before the dimension rollups.
    df["lfapm_qty"] = df["pfapm_qty"]
    df["lfapm_val"] = df["pfapm_val"]
    df["lfytd_apm_qty"] = df["lfytd_apm_qty"]
    df["lfytd_apm_val"] = df["lfytd_apm_val"]
    df["apm_growth_pct_qty"] = df.apply(
        lambda r: safe_growth(r["cfapm_qty"], r["lfytd_apm_qty"]), axis=1
    )
    df["apm_growth_pct_val"] = df.apply(
        lambda r: safe_growth(r["cfapm_val"], r["lfytd_apm_val"]), axis=1
    )
    def compute_trending(cfytd, lfytd, lfy_full, days_elapsed, total_days):
        """'Last year same period, adjusted for growth' - standard retail
        forecasting method. Applies this year's YTD-vs-same-period growth rate
        to last year's ACTUAL full-year total, inheriting last year's real
        seasonal shape instead of assuming sales are flat across all 12 months
        (which the old flat-linear run-rate did)."""
        if lfytd is None or lfytd <= 0:
            # Fallback: flat-linear run-rate (original method) when the
            # seasonality ratio is undefined/unreliable for this row
            return safe_div(cfytd, days_elapsed) * total_days
        return cfytd * (lfy_full / lfytd)

    df["trending_qty"] = df.apply(
        lambda r: compute_trending(r["cfytd_qty"], r["lfytd_qty"], r["lfy_full_qty"],
                                     fy.days_elapsed_current_fy, fy.total_days_current_fy), axis=1)
    df["trending_val"] = df.apply(
        lambda r: compute_trending(r["cfytd_val"], r["lfytd_val"], r["lfy_full_val"],
                                     fy.days_elapsed_current_fy, fy.total_days_current_fy), axis=1)
    df["proj_growth_pct_qty"] = df.apply(
        lambda r: safe_growth(r["trending_qty"], r["lfy_full_qty"]), axis=1
    )
    df["proj_growth_pct_val"] = df.apply(
        lambda r: safe_growth(r["trending_val"], r["lfy_full_val"]), axis=1
    )

    for d in dims:
        df[d] = df[d].apply(lambda v: None if pd.isna(v) else v)
    df = df.where(pd.notnull(df), None)
    return df.to_dict(orient="records")


def _pivot_column_meta(dims: list[str]) -> dict:
    # Labels are display-only metadata and intentionally mirror the KPI-card
    # labels in the frontend so the KPI cards and the pivot/summary table show
    # identical names for every measure. No calculation logic lives here.
    return {
        "dimensions": dims,
        "measures": [
            {"key": "lfy_full", "label": "LFY Full"},
            {"key": "lfytd", "label": "LFYTD"},
            {"key": "cfytd", "label": "CFYTD"},
            {"key": "growth_pct", "label": "Growth %"},
            {"key": "balance", "label": "Balance"},
            {"key": "lfapm", "label": "LFAPM"},
            {"key": "lfytd_apm", "label": "LFYTD APM"},
            {"key": "cfapm", "label": "CFAPM"},
            {"key": "apm_growth_pct", "label": "APM Growth %"},
            {"key": "trending", "label": "Trending (Proj. Full Year)"},
            {"key": "proj_growth_pct", "label": "Proj. Growth %"},
        ],
        "units": ["qty", "val"],
    }


# ---------------------------------------------------------------------------
# Monthwise Sales (2nd requirement of Modules I & IV)
#
# Generalised over an arbitrary list of "measures" (raw summable columns) and
# optional "ratio_measures" (computed AFTER summation, e.g. Discount Outflow
# % = SUM(discount)/SUM(mrp_value)*100 - never sum the per-row percentages).
# growth_keys controls which of those (measure or ratio) keys get an
# LFY-vs-CFY GROWTH% column, per the requirements doc's differing asks for
# Secondary (qty & val growth) vs Tertiary (qty, bill_val, discount-outflow
# growth) monthwise tables.
# ---------------------------------------------------------------------------
def _measures_key(measures: list[dict] | None) -> tuple:
    """Hashable, order-preserving cache key for a list of measure definitions.

    (name, value) pairs are sorted inside each measure so a dict built in a
    different key order still hits the same cache entry; the ORDER of the
    measures themselves is preserved because it drives the output columns.
    """
    return tuple(tuple(sorted((str(k), str(v)) for k, v in m.items())) for m in (measures or []))


def run_monthwise(
    fact: FactSpec,
    dimensions: list[str],
    filters: dict[str, list[str]],
    measures: list[dict],
    ratio_measures: list[dict] | None = None,
    growth_keys: list[str] | None = None,
) -> dict:
    """Month-as-COLUMNS monthwise table (Secondary Sales Analysis).

    Memoised on (fact, dimensions, filters, measure definitions, data token) -
    the monthwise tab sits next to the pivot tab and is re-requested on every
    slicer / hierarchy change, so identical view states now cost a dict lookup.
    `growth_keys=None` is part of the key as an empty tuple (the "default to
    every measure key" rule is applied inside the cached body, exactly as
    before).
    """
    return _monthwise_cached(
        fact,
        tuple(dimensions or []),
        filter_key(filters),
        _measures_key(measures),
        _measures_key(ratio_measures or []),
        tuple(growth_keys) if growth_keys else None,
        cache_token(),
    )


@lru_cache(maxsize=32)
def _monthwise_cached(
    fact: FactSpec,
    dims_key: tuple,
    filters_key: tuple,
    measures_key: tuple,
    ratio_key: tuple,
    growth_key: tuple | None,
    _token: tuple,
) -> dict:
    """Body of `run_monthwise` (the `_token` argument is the cache key only)."""
    dimensions = list(dims_key)
    filters = {col: list(values) for col, values in filters_key}
    measures = [dict(m) for m in measures_key]
    ratio_measures = [dict(m) for m in ratio_key]
    growth_keys = list(growth_key) if growth_key else None
    dims = _validate_dimensions(dimensions)
    ratio_measures = ratio_measures or []
    growth_keys = growth_keys or [m["key"] for m in measures]

    max_date = _get_global_max_date(fact)
    if max_date is None:
        return {"rows": [], "months": [], "fy_context": None}

    fy = build_fy_context(max_date)
    filter_sql, filter_params = _build_filter_sql(filters)
    # Internal aliases (dim__<col>) keep dimension columns from ever colliding
    # with a same-named raw fact column (e.g. tertiary_data.data.brand vs the
    # store_master.brand dimension) - collision-safe regardless of future
    # schema changes.
    dim_select = "".join(
        f"dim.{quote_ident(d)} AS {quote_ident('dim__' + d)}, " for d in dims
    )
    dim_group_internal = ", ".join(quote_ident("dim__" + d) for d in dims)
    measure_select = ", ".join(f"SUM({m['expr']}) AS {quote_ident(m['key'])}" for m in measures)

    sql = f"""
    WITH dim_joined AS (
        SELECT
            f.{quote_ident(fact.date_column)} AS tx_date,
            {dim_select}
            f.*
        FROM {fact.schema}.{fact.table} f
        LEFT JOIN store_master.store_details dim
            ON f.{quote_ident(fact.store_column)} = dim.adonis_store_code
           AND f.{quote_ident(fact.brand_column)} = dim.brand_code
        WHERE 1=1 {filter_sql}
          AND f.{quote_ident(fact.date_column)} BETWEEN ?::DATE AND ?::DATE
    )
    SELECT
        {(dim_group_internal + ",") if dims else ""}
        CASE WHEN tx_date >= ?::DATE THEN 'CFY' ELSE 'LFY' END AS fy_bucket,
        EXTRACT(YEAR FROM tx_date)::INT AS cal_year,
        EXTRACT(MONTH FROM tx_date)::INT AS cal_month,
        {measure_select}
    FROM dim_joined
    GROUP BY {(dim_group_internal + ",") if dims else ""} fy_bucket, cal_year, cal_month
    """
    params = filter_params + [fy.last_fy_start, fy.current_fy_end, fy.current_fy_start]
    df = execute_df(sql, params)
    df = df.rename(columns={f"dim__{d}": d for d in dims})

    months_seq = _fy_month_sequence(fy)
    measure_keys = [m["key"] for m in measures]

    if df.empty:
        return {"rows": [], "months": months_seq_public(months_seq), "dimensions": dims, "fy_context": fy.to_dict()}

    group_cols = dims
    pivot_rows: list[dict] = []
    grouping_keys = (
        [tuple(r) for r in df[group_cols].drop_duplicates().values.tolist()]
        if group_cols
        else [()]
    )

    for key in grouping_keys:
        if group_cols:
            mask = pd.Series(True, index=df.index)
            for col, val in zip(group_cols, key):
                mask &= df[col] == val
            sub = df[mask]
        else:
            sub = df
        row = {col: val for col, val in zip(group_cols, key)}
        for m in months_seq:
            lfy_mask = (sub["fy_bucket"] == "LFY") & (sub["cal_month"] == m["cal_month"]) & (
                sub["cal_year"] == m["lfy_cal_year"]
            )
            cfy_mask = (sub["fy_bucket"] == "CFY") & (sub["cal_month"] == m["cal_month"]) & (
                sub["cal_year"] == m["cfy_cal_year"]
            )
            is_future = m["month_start"] > fy.max_date

            lfy_vals: dict[str, float] = {}
            cfy_vals: dict[str, float | None] = {}
            for mk in measure_keys:
                lfy_vals[mk] = float(sub.loc[lfy_mask, mk].sum()) if lfy_mask.any() else 0.0
                cfy_vals[mk] = None if is_future else (
                    float(sub.loc[cfy_mask, mk].sum()) if cfy_mask.any() else 0.0
                )

            for rm in ratio_measures:
                num, den = rm["numerator"], rm["denominator"]
                lfy_vals[rm["key"]] = safe_pct(lfy_vals[num], lfy_vals[den])
                cfy_vals[rm["key"]] = (
                    None if cfy_vals[num] is None else safe_pct(cfy_vals[num], cfy_vals[den])
                )

            for mk, v in lfy_vals.items():
                row[f"{m['key']}__lfy_{mk}"] = v
            for mk, v in cfy_vals.items():
                row[f"{m['key']}__cfy_{mk}"] = v
            for gk in growth_keys:
                cfy_v, lfy_v = cfy_vals.get(gk), lfy_vals.get(gk)
                row[f"{m['key']}__growth_pct_{gk}"] = (
                    None if cfy_v is None else safe_growth(cfy_v, lfy_v)
                )
        pivot_rows.append(row)

    return {
        "rows": pivot_rows,
        "months": months_seq_public(months_seq),
        "dimensions": dims,
        "measure_keys": measure_keys,
        "ratio_keys": [rm["key"] for rm in ratio_measures],
        "growth_keys": growth_keys,
        "fy_context": fy.to_dict(),
    }


def run_monthwise_rows(
    fact: FactSpec,
    dimensions: list[str],
    filters: dict[str, list[str]],
    measures: list[dict],
    ratio_measures: list[dict] | None = None,
    growth_keys: list[str] | None = None,
) -> dict:
    """Month-as-ROWS variant of the monthwise analysis (used by Tertiary Sales).

    Each output row is one dimension combination + one month (April..March),
    with every measure as a COLUMN alongside:
      - a `*_growth_pct` per growth key (CFY vs LFY for that calendar month)
      - a `discount_pct`-style ratio (computed from underlying aggregates)
      - `ms_cumulative_pct`: cumulative contribution % of that row's Value
        (Bill Value) against the filtered dataset's total, accumulated in
        fiscal-month order (the natural row dimension), respecting active
        filters. Future months (no CFY data) are blank and contribute 0.

    Memoised on (fact, dimensions, filters, measure definitions, data token).
    The measure/ratio/growth definitions are part of the key (hashed as ordered
    name/value tuples), so two different measure sets can never collide.
    """
    return _monthwise_rows_cached(
        fact,
        tuple(dimensions or []),
        filter_key(filters),
        _measures_key(measures),
        _measures_key(ratio_measures or []),
        tuple(growth_keys or []),
        cache_token(),
    )


@lru_cache(maxsize=32)
def _monthwise_rows_cached(
    fact: FactSpec,
    dims_key: tuple,
    filters_key: tuple,
    measures_key: tuple,
    ratio_key: tuple,
    growth_key: tuple,
    _token: tuple,
) -> dict:
    """Body of `run_monthwise_rows` (the `_token` argument is the cache key)."""
    dimensions = list(dims_key)
    filters = {col: list(values) for col, values in filters_key}
    measures = [dict(m) for m in measures_key]
    ratio_measures = [dict(m) for m in ratio_key]
    growth_keys = list(growth_key)
    ratio_measures = ratio_measures or []
    growth_keys = growth_keys or []
    dims = _validate_dimensions(dimensions)
    selected_months = [int(value) for value in filters.pop("month", []) if str(value).isdigit()]
    selected_fys = [int(value) for value in filters.pop("fy", []) if str(value).isdigit()]
    filter_sql, filter_params = _build_filter_sql(filters)

    dim_select = "".join(
        f"dim.{quote_ident(d)} AS {quote_ident('dim__' + d)}, " for d in dims
    )
    dim_group_internal = ", ".join(quote_ident("dim__" + d) for d in dims)
    measure_select = ", ".join(
        f"SUM({quote_ident(m['key'])}) AS {quote_ident(m['key'])}" for m in measures
    )
    raw_measure_select = ", ".join(
        f"({m['expr']}) AS {quote_ident(m['key'])}" for m in measures
    )

    max_date = _get_global_max_date(fact)
    if max_date is None:
        return {"rows": [], "months": [], "dimensions": dims, "measure_keys": [m["key"] for m in measures], "ratio_keys": [m["key"] for m in ratio_measures], "growth_keys": growth_keys, "fy_context": None}
    current_fy = max_date.year if max_date.month >= FY_START_MONTH else max_date.year - 1
    anchor_fy = max(selected_fys) if selected_fys else current_fy
    # Use the selected fiscal year as the comparison anchor. A historical
    # selection is a completed year; the live FY retains its actual max date.
    anchor_max_date = max_date if anchor_fy >= current_fy else date(anchor_fy + 1, 3, 31)
    fy = build_fy_context(anchor_max_date)
    month_filter = ""
    if selected_months:
        month_filter = " AND month(f." + quote_ident(fact.date_column) + ") IN (" + ",".join("?" for _ in selected_months) + ")"

    sql = f"""
    WITH dim_joined AS (
        SELECT
            f.{quote_ident(fact.date_column)} AS tx_date,
            {dim_select}
            {raw_measure_select}
        FROM {fact.schema}.{fact.table} f
        LEFT JOIN store_master.store_details dim
            ON f.{quote_ident(fact.store_column)} = dim.adonis_store_code
           AND f.{quote_ident(fact.brand_column)} = dim.brand_code
        WHERE 1=1 {filter_sql}
          AND f.{quote_ident(fact.date_column)} BETWEEN ?::DATE AND ?::DATE{month_filter}
    )
    SELECT
        {(dim_group_internal + ",") if dims else ""}
        CASE WHEN tx_date >= ?::DATE THEN 'CFY' ELSE 'LFY' END AS fy_bucket,
        EXTRACT(YEAR FROM tx_date)::INT AS cal_year,
        EXTRACT(MONTH FROM tx_date)::INT AS cal_month,
        {measure_select}
    FROM dim_joined
    GROUP BY {(dim_group_internal + ",") if dims else ""} fy_bucket, cal_year, cal_month
    """
    params = filter_params + [fy.last_fy_start, fy.current_fy_end] + selected_months + [fy.current_fy_start]
    df = execute_df(sql, params)
    df = df.rename(columns={f"dim__{d}": d for d in dims})

    months_seq = _fy_month_sequence(fy)
    if selected_months:
        selected_month_set = set(selected_months)
        months_seq = [month for month in months_seq if month["cal_month"] in selected_month_set]
    measure_keys = [m["key"] for m in measures]
    value_key = growth_keys[0] if growth_keys else measure_keys[-1]

    rows: list[dict] = []
    group_cols = dims
    grouping_keys = (
        [tuple(r) for r in df[group_cols].drop_duplicates().values.tolist()]
        if group_cols
        else [()]
    )

    for key in grouping_keys:
        sub = df
        for col, val in zip(group_cols, key):
            sub = sub[sub[col] == val]
        base = {col: val for col, val in zip(group_cols, key)}

        # Per-month CFY measures for every group so cumulative is computed
        # against the filtered dataset's OWN total (not a global/unfiltered one).
        total_value = 0.0
        month_cfy: list[dict] = []
        month_lfy: list[dict] = []
        for m in months_seq:
            lfy_mask = (sub["fy_bucket"] == "LFY") & (sub["cal_month"] == m["cal_month"]) & (
                sub["cal_year"] == m["lfy_cal_year"]
            )
            cfy_mask = (sub["fy_bucket"] == "CFY") & (sub["cal_month"] == m["cal_month"]) & (
                sub["cal_year"] == m["cfy_cal_year"]
            )
            is_future = m["month_start"] > fy.max_date
            cfy_vals: dict[str, float | None] = {}
            lfy_vals: dict[str, float] = {}
            for mk in measure_keys:
                lfy_vals[mk] = float(sub.loc[lfy_mask, mk].sum()) if lfy_mask.any() else 0.0
                cfy_vals[mk] = None if is_future else (
                    float(sub.loc[cfy_mask, mk].sum()) if cfy_mask.any() else 0.0
                )
            month_lfy.append({"m": m, "vals": lfy_vals})
            month_cfy.append({"m": m, "vals": cfy_vals})
            v = cfy_vals.get(value_key)
            if v is not None:
                total_value += v

        running_val = 0.0
        running_pct = 0.0
        for lfy_item, cfy_item in zip(month_lfy, month_cfy):
            m = cfy_item["m"]
            cfy_vals, lfy_vals = cfy_item["vals"], lfy_item["vals"]
            row = dict(base)
            row["month_order"] = _fiscal_month_index(m["cal_month"])
            row["month"] = _month_full_name(m["cal_month"])
            for mk in measure_keys:
                row[mk] = cfy_vals[mk]
                row[f"{mk}_ly"] = lfy_vals[mk]
                row[f"{mk}_growth_pct"] = (
                    None if cfy_vals[mk] is None else safe_growth(cfy_vals[mk], lfy_vals[mk])
                )
            for rm in ratio_measures:
                row[rm["key"]] = (
                    None if cfy_vals[rm["numerator"]] is None
                    else safe_pct(cfy_vals[rm["numerator"]], cfy_vals[rm["denominator"]])
                )
            val = cfy_vals.get(value_key)
            if val is not None and total_value:
                # Cumulative Value [contribution %] - running value and its
                # running contribution % against the filtered dataset's total,
                # accumulated in fiscal-month order (final data month ~100%).
                running_val += val
                running_pct += (val / total_value) * 100.0
                row["ms_cum_val"] = running_val
                row["ms_cum_pct"] = running_pct
                row["ms_contrib_pct"] = (val / total_value) * 100.0
            else:
                row["ms_cum_val"] = None
                row["ms_contrib_pct"] = None
                row["ms_cum_pct"] = None
            rows.append(row)

    return {
        "rows": rows,
        "months": months_seq_public(months_seq),
        "dimensions": dims,
        "measure_keys": measure_keys,
        "ratio_keys": [rm["key"] for rm in ratio_measures],
        "growth_keys": growth_keys,
        "fy_context": fy.to_dict(),
    }


def _month_full_name(m: int) -> str:
    import calendar

    return calendar.month_name[m]


def months_seq_public(months_seq: list[dict]) -> list[dict]:
    return [{"key": m["key"], "label": m["label"]} for m in months_seq]


def _fy_month_sequence(fy) -> list[dict]:
    """12 months April..March with the calendar year each falls in for both
    the last-FY and current-FY windows, so we can look up the right bucket."""
    from app.services.fy import month_label

    out = []
    for i in range(12):
        m = ((fy.current_fy_start.month - 1 + i) % 12) + 1
        cfy_year = fy.current_fy_start.year if m >= fy.current_fy_start.month else fy.current_fy_start.year + 1
        lfy_year = fy.last_fy_start.year if m >= fy.last_fy_start.month else fy.last_fy_start.year + 1
        out.append(
            {
                "key": f"m{i+1:02d}",
                "cal_month": m,
                "cfy_cal_year": cfy_year,
                "lfy_cal_year": lfy_year,
                "label": month_label(m),
                "month_start": date(cfy_year, m, 1),
            }
        )
    return out
