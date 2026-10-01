"""
CSS Stock Tracking (Module V) - Order vs Dispatch / Transformed-to-Store.

BASELINE (corrected spec)
-------------------------
The ORDER FORM is the COMPLETE original order placed before the season starts:

  Ordered Qty = SUM(order_form.CURRENTQUANTITY)   (VENUEQUANTITY is NEVER used)

Every Order Form Product/Style + Season combination appears in the Summary,
including styles that were never dispatched at all - the Summary is NOT
dependent on records existing in Secondary Data.

MATCHING
--------
  Order Form.STYLE_CODE  <->  Secondary Data.PRODUCT_CODE_CODE
  Order Form.SEASON      <->  Secondary Data.SEASON

Both sides are normalised identically before comparison (TRIM + removal of ALL
internal whitespace + UPPERCASE) so equivalent codes/seasons meet - stored
data is never modified. A Secondary record counts as current-season dispatch
ONLY when its cleaned Season equals the Order Form season; dispatches from
other seasons are never mixed in.

Matching key = (cleaned Product/Style, cleaned Season). Multiple Secondary
dispatch records for the same key are aggregated BEFORE comparison against
the Order Form quantity.

STATUS LOGIC (per Product/Style + Season)
-----------------------------------------
  Ordered Qty    = SUM(Order Form CURRENTQUANTITY) for that key
  Dispatched Qty = SUM(Secondary qty, net Sales-Returns) for that key
  Pending Qty    = MAX(Ordered Qty - Dispatched Qty, 0)
  Dispatch %     = Dispatched Qty / Ordered Qty x 100   (NULL when Ordered = 0)

  fully_dispatched        Ordered > 0 and Dispatched >= Ordered
  partially_dispatched    Ordered > 0 and 0 < Dispatched < Ordered
  pending                 Ordered > 0 and Dispatched <= 0
  dbno                    Dispatched > 0 with NO matching Order Form key
                          ("Dispatched But Not Ordered" - never forced into
                          the order baseline, never given an artificial order
                          quantity)

MRP VALUE
---------
  MRP Value has NO source column - it is derived internally:
      Ordered MRP Val    = MRP x Ordered Qty
      Dispatched MRP Val = MRP x Dispatched Qty   (Order Form MRP, Secondary
      Pending MRP Val    = MRP x Pending Qty       MDP as fallback)
  It is computed per Product/Style at the atomic grain so it re-aggregates
  exactly up any hierarchy and reconciles with the KPI cards. MRP itself is
  a per-style attribute (shown, never summed); only the derived value rolls
  up alongside the matching quantity.

SUB CATEGORY
------------
  Mapped records          -> Order Form.SUBCATEGORY
  Unmapped (dbno) records -> cleaned Secondary.PRODUCT_DESC (trimmed,
                             internal whitespace collapsed). Secondary's own
                             sub-category column is never used.

FILTERING / DIMENSIONS
----------------------
Any store_master VARCHAR attribute (retailer_name, brand, state, store_type,
department, group, store_status, ...) can be used as a filter and/or row
dimension. Filters apply to the UNDERLYING order/dispatch rows (via the
store_master join) BEFORE aggregation, so KPI cards, the brand chart, the
summary table and the Excel export always reconcile exactly. Dimensions
partition the rows, so summed summary rows equal the KPI totals.
"""
from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
from typing import Any

import pandas as pd

from app.core.database import cache_token, execute_df, filter_key, quote_ident
from app.services.store_master import get_all_columns

ORDER_SCHEMA, ORDER_TABLE = "order_form", "order_form"
SECONDARY_SCHEMA, SECONDARY_TABLE = "secondary_data", "data"
STORE_SCHEMA, STORE_TABLE = "store_master", "store_details"

# store_master columns that can never be slicers/dimensions: keys and dates.
_NON_DIMENSION_COLUMNS = {"adonis_store_code", "brand_code", "ter_min_date", "ter_max_date"}

STATUS_FULLY = "fully_dispatched"
STATUS_PARTIAL = "partially_dispatched"
STATUS_PENDING = "pending"
STATUS_DBNO = "dbno"

ALL_STATUSES = [STATUS_FULLY, STATUS_PARTIAL, STATUS_PENDING, STATUS_DBNO]

# Special (non store-master) row-hierarchy keys. Removing "product_style"
# from the hierarchy rolls the Summary up to group level (e.g. one M-Denim
# total per Brand/Season/Sub Category) instead of one row per style.
_SPECIAL_DIMS = {"subcategory", "product_style"}

STATUS_LABELS = {
    STATUS_FULLY: "Fully Dispatched",
    STATUS_PARTIAL: "Partially Dispatched",
    STATUS_PENDING: "Pending",
    STATUS_DBNO: "Dispatched But Not Ordered",
}


# ---------------------------------------------------------------------------
# Normalisation helpers (comparison-only; stored data is never modified)
# ---------------------------------------------------------------------------
def _norm_season(col: str) -> str:
    """TRIM + remove ALL internal whitespace + UPPERCASE, e.g. '2026 - H2'
    and '2026-H2' both normalise to '2026-H2'. Applied identically to BOTH
    tables so equivalent season labels meet without altering stored data."""
    return f"UPPER(REGEXP_REPLACE(TRIM({col}), '\\s+', '', 'g'))"


def _norm_code(col: str) -> str:
    """TRIM + remove ALL internal whitespace + UPPERCASE for product/style
    codes (e.g. '0003K 0012' == '0003k-0012' spacing/casing differences)."""
    return f"UPPER(REGEXP_REPLACE(TRIM({col}), '\\s+', '', 'g'))"


def _clean_text(col: str) -> str:
    """Display cleanup for free text (PRODUCT_DESC fallback Sub Category):
    trim + collapse repeated internal whitespace."""
    return f"NULLIF(REGEXP_REPLACE(TRIM({col}), '\\s+', ' ', 'g'), '')"


# ---------------------------------------------------------------------------
# Dimension / filter discovery
# ---------------------------------------------------------------------------
def get_available_dimensions() -> list[dict]:
    """Every store_master VARCHAR column except keys/dates can be used as a
    row dimension and/or slicer (resolved dynamically so renames never break).

    Served from the memoised catalog: this is called by every filter/dimension
    validation, so it used to re-hit `information_schema` several times per
    request.  Fresh dicts are returned each call.
    """
    return [{"column": col, "label": label} for col, label in _available_dimensions_cached()]


@lru_cache(maxsize=1)
def _available_dimensions_cached() -> tuple[tuple[str, str], ...]:
    return tuple(
        (c["name"], c["name"].replace("_", " ").upper())
        for c in get_all_columns()
        if c["name"] not in _NON_DIMENSION_COLUMNS and c["type"] == "VARCHAR"
    )


@lru_cache(maxsize=8)
def _seasons_cached(_token: tuple) -> tuple[str, ...]:
    rows = execute_df(
        f"SELECT DISTINCT TRIM(season) AS season FROM {ORDER_SCHEMA}.{ORDER_TABLE} "
        "WHERE season IS NOT NULL ORDER BY 1"
    )
    return tuple(rows["season"].tolist()) if not rows.empty else ()


def get_seasons() -> list[str]:
    """Order-form seasons, memoised on the data token (`_token` = cache key)."""
    return list(_seasons_cached(cache_token()))


def _validate_dims(dims: list[str]) -> list[str]:
    valid = {d["column"] for d in get_available_dimensions()} | _SPECIAL_DIMS
    bad = [d for d in dims if d not in valid]
    if bad:
        raise ValueError(f"Unknown/ineligible dimension(s): {bad}")
    out: list[str] = []
    for d in dims:
        if d not in out:
            out.append(d)
    return out


def _validate_filters(filters: dict[str, list[str]]) -> dict[str, list[str]]:
    # Store-master dimension columns PLUS the special analysis keys
    # (subcategory / product_style) are all valid filter columns. Special-dim
    # filters are evaluated AFTER the order/dispatch join (see
    # _special_filter_sql), store-master filters inside the ord/dis CTEs.
    valid = {d["column"] for d in get_available_dimensions()} | _SPECIAL_DIMS
    for col, values in (filters or {}).items():
        if col not in valid:
            raise ValueError(f"Unknown filter column: {col}")
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            raise ValueError(f"Filter values for {col} must be a list of strings")
    return {c: v for c, v in (filters or {}).items() if v}


def _validate_statuses(statuses: list[str] | None) -> list[str] | None:
    if statuses is None:
        return None
    bad = [s for s in statuses if s not in ALL_STATUSES]
    if bad:
        raise ValueError(f"Unknown status(es): {bad}. Valid: {ALL_STATUSES}")
    return [s for s in ALL_STATUSES if s in statuses] or None


def _filter_sql(filters: dict[str, list[str]]) -> tuple[str, list[Any]]:
    """AND-ed IN clauses over store_master columns (validated upstream)."""
    clauses: list[str] = []
    params: list[Any] = []
    for col, values in filters.items():
        placeholders = ",".join(["?"] * len(values))
        clauses.append(f"sm.{quote_ident(col)} IN ({placeholders})")
        params.extend(values)
    return ((" AND " + " AND ".join(clauses)) if clauses else ""), params


def _split_filters(
    filters: dict[str, list[str]],
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Split validated filters into store-master columns (applied inside the
    ord/dis CTEs on sm.*) and the special analysis keys (applied after the
    join, on j.subcategory / j.product_style)."""
    sm = {c: v for c, v in filters.items() if c not in _SPECIAL_DIMS}
    special = {c: v for c, v in filters.items() if c in _SPECIAL_DIMS}
    return sm, special


def _special_filter_sql(
    special_filters: dict[str, list[str]], alias: str = "j"
) -> tuple[str, list[Any]]:
    """AND-ed IN clauses over the special analysis keys. These columns only
    exist after the order/dispatch FULL OUTER JOIN resolves their display
    COALESCE, so they are attached to the post-join CTE (t0 / slicer SELECT),
    never to the ord/dis CTEs."""
    clauses: list[str] = []
    params: list[Any] = []
    for col, values in special_filters.items():
        placeholders = ",".join(["?"] * len(values))
        clauses.append(f"{alias}.{quote_ident(col)} IN ({placeholders})")
        params.extend(values)
    return ((" AND " + " AND ".join(clauses)) if clauses else ""), params


# ---------------------------------------------------------------------------
# Core row computation (single source of truth for KPIs / chart / table / export)
# ---------------------------------------------------------------------------
def _join_ctes(
    season: str | None,
    sm_dims: list[str],
    sm_filters: dict[str, list[str]],
) -> tuple[str, list[Any]]:
    """Shared ord/dis/j CTE chain used by BOTH _fetch_rows and
    get_slicer_options, so slicer values always describe exactly the rows the
    dashboard shows. Applies the season filter and the store-master filters
    (sm.*) inside both sides, aggregates each side to (sm-dims x cleaned
    Season x cleaned Style) and FULL-OUTER-JOINs them on the normalised key,
    resolving the special display keys via COALESCE. Returns the CTE text
    (without the leading WITH) and its ordered parameters."""
    # Dimension plumbing (both CTEs expose the store-master attribute under
    # its plain name so the FULL OUTER JOIN can pair the two sides).
    dim_sel_ord = "".join(f", sm.{quote_ident(d)} AS {quote_ident(d)}" for d in sm_dims)
    dim_sel_dis = dim_sel_ord
    dim_out = "".join(
        f", COALESCE(o.{quote_ident(d)}, d.{quote_ident(d)}) AS {quote_ident(d)}" for d in sm_dims
    )
    dim_join = "".join(
        f" AND o.{quote_ident(d)} IS NOT DISTINCT FROM d.{quote_ident(d)}" for d in sm_dims
    )

    filter_sql, filter_params = _filter_sql(sm_filters)

    season_clause_ord = ""
    season_clause_dis = ""
    season_params: list[Any] = []
    if season:
        season_clause_ord = f" AND {_norm_season('o.season')} = {_norm_season('?')}"
        season_clause_dis = f" AND {_norm_season('b.season')} = {_norm_season('?')}"
        season_params = [season]
    else:
        # No explicit season: only dispatches belonging to ORDER-FORM seasons
        # are relevant (other seasons can never match an order key anyway).
        season_clause_dis = (
            f" AND {_norm_season('b.season')} IN ("
            f"SELECT {_norm_season('season')} FROM {ORDER_SCHEMA}.{ORDER_TABLE} "
            "WHERE season IS NOT NULL)"
        )

    # Parameter order follows textual appearance: ord CTE (season, filters)
    # then dis CTE (season, filters).
    params = season_params + filter_params + season_params + filter_params

    sql = f"""
    ord AS (
        -- ORDER side baseline: the complete original order, aggregated to
        -- (dimensions x cleaned Season x cleaned Style). CURRENTQUANTITY is
        -- the ordered quantity; VENUEQUANTITY is intentionally NOT used.
        SELECT
            1 AS _g{dim_sel_ord}
            ,{_norm_season('o.season')} AS sn
            ,{_norm_code('o.style_code')} AS st
            ,MAX(TRIM(o.style_code)) AS ps_display
            ,MAX({_norm_season('o.season')}) AS season_display
            ,MAX(TRIM(o.subcategory)) AS subcategory
            ,MIN(COALESCE(sm.brand, o.brand_code)) AS brand_ref
            ,MAX(o.mrp) AS mrp_of
            ,MAX(o.mrp) * SUM(o.currentquantity) AS ordered_mrp_val
            ,SUM(o.currentquantity) AS ordered_qty
        FROM {ORDER_SCHEMA}.{ORDER_TABLE} o
        LEFT JOIN {STORE_SCHEMA}.{STORE_TABLE} sm
            ON o.adonis_store_code = sm.adonis_store_code
           AND o.brand_code = sm.brand_code
        WHERE o.style_code IS NOT NULL
          AND TRIM(o.style_code) <> ''
          {season_clause_ord}
          {filter_sql}
        GROUP BY ALL
    ),
    dis AS (
        -- DISPATCH side: Secondary rows aggregated to the same key shape.
        -- qty is NET dispatch (Sales positive, Returns negative). Only rows
        -- whose CLEANED season matches the order-form season(s) are used.
        SELECT
            1 AS _g{dim_sel_dis}
            ,{_norm_season('b.season')} AS sn
            ,{_norm_code('b.product_code_code')} AS st
            ,MAX(TRIM(b.product_code_code)) AS code_display
            ,MAX({_norm_season('b.season')}) AS season_display
            ,MAX({_clean_text('b.product_desc')}) AS pdesc_clean
            ,MIN(COALESCE(sm.brand, b.brand_code)) AS brand_ref
            ,MAX(b.mdp) AS mrp_of
            ,MAX(b.mdp) * SUM(b.qty) AS dispatched_mrp_val
            ,SUM(b.qty) AS dispatched_qty
        FROM {SECONDARY_SCHEMA}.{SECONDARY_TABLE} b
        LEFT JOIN {STORE_SCHEMA}.{STORE_TABLE} sm
            ON b.adonis_store_code = sm.adonis_store_code
           AND b.brand_code = sm.brand_code
        WHERE b.product_code_code IS NOT NULL
          AND TRIM(b.product_code_code) <> ''
          {season_clause_dis}
          {filter_sql}
        GROUP BY ALL
    ),
    j AS (
        SELECT
            TRUE AS _root{dim_out}
            ,COALESCE(o.brand_ref, d.brand_ref) AS brand
            ,COALESCE(o.season_display, d.season_display) AS season
            -- Sub Category: Order Form SUBCATEGORY when mapped; cleaned
            -- PRODUCT_DESC for unmapped (dispatched-but-not-ordered) rows.
            ,COALESCE(o.subcategory, d.pdesc_clean) AS subcategory
            ,COALESCE(o.ps_display, d.code_display) AS product_style
            -- MRP: Order Form MRP when mapped, Secondary MDP fallback.
            ,COALESCE(o.mrp_of, d.mrp_of) AS mrp
            -- MRP Value = MRP x Qty, derived on each side at the atomic
            -- (style x season) grain so it re-aggregates exactly up any
            -- requested hierarchy and keeps cards/table/export reconciled.
            ,CAST(COALESCE(o.ordered_mrp_val, 0) AS DOUBLE) AS ordered_mrp_val
            ,CAST(COALESCE(d.dispatched_mrp_val, 0) AS DOUBLE) AS dispatched_mrp_val
            ,CAST(GREATEST(
                COALESCE(o.ordered_mrp_val, 0) - COALESCE(d.dispatched_mrp_val, 0),
                0) AS DOUBLE) AS pending_mrp_val
            ,CAST(COALESCE(o.ordered_qty, 0) AS DOUBLE) AS ordered_qty
            ,CAST(COALESCE(d.dispatched_qty, 0) AS DOUBLE) AS dispatched_qty
        FROM ord o
        FULL OUTER JOIN dis d
            ON o.sn = d.sn AND o.st = d.st{dim_join}
    )"""
    return sql, params


def _fetch_rows(
    season: str | None,
    dims: list[str],
    filters: dict[str, list[str]],
    statuses: list[str] | None = None,
) -> pd.DataFrame:
    """One row per (selected dimensions) x (cleaned Product/Style + Season).

    Both sides are aggregated independently (after store-master filters and
    the season filter) and FULL-OUTER-JOINED on the normalised key, so:
      * every Order Form style appears even with zero dispatch;
      * Secondary styles with no Order Form match survive as separate rows;
      * seasons are matched only after identical cleaning - never mixed.

    Memoised on (season, dimensions, filters, statuses, data token): the KPI
    cards, the summary table and the Excel export all read this SAME canonical
    row set, so one page view used to aggregate order_form x secondary_data
    three or four times over.  Every consumer only reads the frame (never
    mutates it), so one shared frame is safe.
    """
    return _rows_cached(
        season or None,
        tuple(dict.fromkeys(dims or [])),
        filter_key(filters),
        tuple(statuses) if statuses else None,
        cache_token(),
    )


@lru_cache(maxsize=32)
def _rows_cached(
    season: str | None,
    dims_key: tuple,
    filters_key: tuple,
    statuses_key: tuple | None,
    _token: tuple,
) -> pd.DataFrame:
    """Body of `_fetch_rows` (the `_token` argument is the cache key only)."""
    dims = list(dims_key)
    filters = {col: list(values) for col, values in filters_key}
    statuses = list(statuses_key) if statuses_key else None
    dims = _validate_dims(dims)
    filters = _validate_filters(filters)
    statuses = _validate_statuses(statuses)

    # Split requested hierarchy into store-master attributes and the special
    # analysis keys. The atomic grain is always (sm-dims x Season x Style);
    # a final GROUP BY then rolls up to exactly the requested hierarchy, so
    # hiding Product/Style yields true group totals (e.g. one M-Denim row).
    sm_dims = [d for d in dims if d not in _SPECIAL_DIMS]
    want_subcat = "subcategory" in dims
    want_style = "product_style" in dims
    sm_filters, special_filters = _split_filters(filters)

    # Final output key list (GROUP BY ALL keys).
    agg_keys = "".join(f", {quote_ident(d)}" for d in sm_dims) + ", brand, season"
    if want_subcat:
        agg_keys += ", subcategory"
    if want_style:
        agg_keys += ", product_style"
    # MRP is a per-style attribute (never summed): shown only at style grain.
    mrp_select = ", MAX(mrp) AS mrp" if want_style else ""

    chain_sql, chain_params = _join_ctes(season, sm_dims, sm_filters)
    # Special-dim filters can only be evaluated AFTER the join, where the
    # order/dispatch COALESCE has resolved the display values (j.*).
    special_sql, special_params = _special_filter_sql(special_filters)

    sql = f"""
    WITH {chain_sql},
    -- Atomic style-grain rows: status classified HERE, before any roll-up,
    -- so a status drill-down followed by grouping still sums only the
    -- matching styles and reconciles with the KPI cards.
    t0 AS (
        SELECT
            j.* EXCLUDE (_root),
            CASE
                WHEN j.ordered_qty > 0 AND j.dispatched_qty >= j.ordered_qty THEN '{STATUS_FULLY}'
                WHEN j.ordered_qty > 0 AND j.dispatched_qty > 0 THEN '{STATUS_PARTIAL}'
                WHEN j.ordered_qty > 0 THEN '{STATUS_PENDING}'
                ELSE '{STATUS_DBNO}'
            END AS status_key
        FROM j
        -- Drop keys that carry no quantity on either side (e.g. 0-qty order
        -- lines never dispatched): they are numerically meaningless.
        WHERE NOT (j.ordered_qty <= 0 AND j.dispatched_qty <= 0){special_sql}
    ),
    t AS (
        SELECT * FROM t0
        {'WHERE status_key IN (' + ','.join('?' * len(statuses)) + ')' if statuses else ''}
    ),
    rolled AS (
        -- Roll up to the REQUESTED hierarchy. Measures re-aggregate from the
        -- sums (Pending = MAX(SUM(o)-SUM(d),0), % from sums, status recomputed
        -- on the totals); MRP is never summed - it is a per-style attribute.
        SELECT
            1 AS _root{agg_keys}
            {mrp_select}
            ,SUM(t.ordered_mrp_val) AS ordered_mrp_val
            ,SUM(t.dispatched_mrp_val) AS dispatched_mrp_val
            ,SUM(t.pending_mrp_val) AS pending_mrp_val
            ,SUM(t.ordered_qty) AS ordered_qty
            ,SUM(t.dispatched_qty) AS dispatched_qty
            ,GREATEST(SUM(t.ordered_qty) - SUM(t.dispatched_qty), 0) AS pending_qty
            ,CASE WHEN SUM(t.ordered_qty) > 0
                  THEN SUM(t.dispatched_qty) / SUM(t.ordered_qty) * 100.0 END AS dispatch_pct
            ,CASE
                WHEN SUM(t.ordered_qty) > 0 AND SUM(t.dispatched_qty) >= SUM(t.ordered_qty) THEN '{STATUS_FULLY}'
                WHEN SUM(t.ordered_qty) > 0 AND SUM(t.dispatched_qty) > 0 THEN '{STATUS_PARTIAL}'
                WHEN SUM(t.ordered_qty) > 0 THEN '{STATUS_PENDING}'
                ELSE '{STATUS_DBNO}'
            END AS status_key
        FROM t
        GROUP BY ALL
    )
    SELECT * EXCLUDE (_root)
    FROM rolled
    ORDER BY ordered_qty DESC, dispatched_qty DESC
    """
    df = execute_df(sql, chain_params + special_params + (statuses or []))

    if df.empty:
        cols = [
            *sm_dims,
            "brand",
            "season",
        ]
        if want_subcat:
            cols.append("subcategory")
        if want_style:
            cols.append("product_style")
        if want_style:
            cols.append("mrp")
        cols += [
            "ordered_mrp_val",
            "dispatched_mrp_val",
            "pending_mrp_val",
            "ordered_qty",
            "dispatched_qty",
            "pending_qty",
            "dispatch_pct",
            "status_key",
        ]
        return pd.DataFrame(columns=cols)

    df["status"] = df["status_key"].map(STATUS_LABELS)
    for c in ("ordered_qty", "dispatched_qty", "pending_qty"):
        df[c] = df[c].astype(float).round(0)
    for c in ("ordered_mrp_val", "dispatched_mrp_val", "pending_mrp_val"):
        df[c] = df[c].astype(float).round(2)
    df["dispatch_pct"] = df["dispatch_pct"].astype(float).round(2)
    if "mrp" in df.columns:
        df["mrp"] = df["mrp"].astype(object).where(df["mrp"].notnull(), None)
        df["mrp"] = df["mrp"].map(lambda v: float(v) if v is not None else None)

    # NaN -> None on OBJECT dtype (NaN is not valid JSON and would 500 FastAPI).
    df = df.astype(object).where(pd.notnull(df), None)
    return df


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
@lru_cache(maxsize=32)
def _kpis_cached(season: str | None, filters_key: tuple, _token: tuple) -> dict:
    """Body of `get_kpis` (the `_token` argument is the cache key only).

    Memoising the finished KPI dict (brand-wise chart series + cards) is what
    makes the warm read of this path interactive: the canonical rows frame is
    already served by `_fetch_rows`/`_rows_cached`, and the per-brand
    `iterrows` aggregation below is now computed once per (season, filters,
    data token) instead of on every call."""
    filters = {col: list(values) for col, values in filters_key}
    df = _fetch_rows(season, ["product_style"], filters)

    if df.empty:
        return {
            "total_ordered": 0.0,
            "total_dispatched": 0.0,
            "total_pending": 0.0,
            "dispatch_pct": None,
            "ordered_mrp_val": 0.0,
            "dispatched_mrp_val": 0.0,
            "pending_mrp_val": 0.0,
            "dbno_qty": 0,
            "dbno_mrp_val": 0.0,
            "fully_dispatched": 0,
            "partially_dispatched": 0,
            "pending": 0,
            "dispatched_but_not_ordered": 0,
            "by_brand": [],
        }

    total_ordered = float(df["ordered_qty"].astype(float).sum())
    total_dispatched = float(df["dispatched_qty"].astype(float).sum())
    total_pending = float(df["pending_qty"].astype(float).sum())
    total_ordered_mrp = float(df["ordered_mrp_val"].astype(float).sum())
    total_dispatched_mrp = float(df["dispatched_mrp_val"].astype(float).sum())
    total_pending_mrp = float(df["pending_mrp_val"].astype(float).sum())
    dispatch_pct = (total_dispatched / total_ordered * 100.0) if total_ordered else None

    # Dispatched-But-Not-Ordered quantity (and its MRP value) for the KPI
    # card: rows without an order-form key carry only dispatch qty/value.
    dbno_mask = df["status_key"].eq(STATUS_DBNO)
    dbno_qty = (
        float(df.loc[dbno_mask, "dispatched_qty"].astype(float).sum())
        if dbno_mask.any()
        else 0.0
    )
    dbno_mrp_val = (
        float(df.loc[dbno_mask, "dispatched_mrp_val"].astype(float).sum())
        if dbno_mask.any()
        else 0.0
    )

    counts = df["status_key"].value_counts().to_dict()

    # Brand-wise Ordered vs Dispatched vs Pending (brands with orders but no
    # dispatch still appear because every order row carries its brand ref).
    # Pending accumulates the PER-ROW pending (MAX(Ordered-Dispatched, 0)) so
    # the chart always reconciles exactly with the summary/KPI totals.
    by_brand: dict[str, dict] = defaultdict(
        lambda: {"ordered_qty": 0.0, "dispatched_qty": 0.0, "pending_qty": 0.0}
    )
    for _, r in df.iterrows():
        b = by_brand[r.get("brand")]
        b["ordered_qty"] += float(r["ordered_qty"] or 0)
        b["dispatched_qty"] += float(r["dispatched_qty"] or 0)
        b["pending_qty"] += float(r["pending_qty"] or 0)
    brand_rows = []
    for brand, v in by_brand.items():
        oq, dq = v["ordered_qty"], v["dispatched_qty"]
        brand_rows.append(
            {
                "brand": brand,
                "ordered_qty": round(v["ordered_qty"]),
                "dispatched_qty": round(v["dispatched_qty"]),
                "pending_qty": round(v["pending_qty"]),
                "dispatch_pct": round(dq / oq * 100.0, 2) if oq else None,
            }
        )
    brand_rows.sort(key=lambda x: (-x["ordered_qty"], -x["dispatched_qty"], x["brand"]))

    return {
        "total_ordered": total_ordered,
        "total_dispatched": total_dispatched,
        "total_pending": total_pending,
        "dispatch_pct": round(dispatch_pct, 2) if dispatch_pct is not None else None,
        "ordered_mrp_val": round(total_ordered_mrp, 2),
        "dispatched_mrp_val": round(total_dispatched_mrp, 2),
        "pending_mrp_val": round(total_pending_mrp, 2),
        "dbno_qty": round(dbno_qty),
        "dbno_mrp_val": round(dbno_mrp_val, 2),
        "fully_dispatched": int(counts.get(STATUS_FULLY, 0)),
        "partially_dispatched": int(counts.get(STATUS_PARTIAL, 0)),
        "pending": int(counts.get(STATUS_PENDING, 0)),
        "dispatched_but_not_ordered": int(counts.get(STATUS_DBNO, 0)),
                "by_brand": brand_rows,
    }


def get_kpis(season: str | None = None, filters: dict[str, list[str]] | None = None) -> dict:
    """Filter-aware KPI cards + brand-wise chart series, derived from the SAME
    canonical engine as the summary table. Status counts are taken at
    Product/Style grain (one style = one status), while quantities reconcile
    with any rollup of the summary."""
    return dict(_kpis_cached(season, filter_key(filters or {}), cache_token()))


def get_summary(
    season: str | None = None,
    dims: list[str] | None = None,
    filters: dict[str, list[str]] | None = None,
    statuses: list[str] | None = None,
) -> dict:
    """Summary rows: Brand | Season | Sub Category | Product/Style (+ chosen
    store-master dimensions) with Ordered / Dispatched / Pending / Dispatch %
    / Status. Includes ALL ordered products, even with zero dispatch."""
    df = _fetch_rows(season, dims or [], filters or {}, statuses)
    return {
        "rows": df.to_dict(orient="records"),
        "dimensions": _validate_dims(dims or []),
        "statuses": _validate_statuses(statuses),
        "season": season,
    }


def get_slicer_options(filters: dict[str, list[str]] | None = None) -> dict[str, list[str]]:
    """Cross-filter aware slicer options: for EACH column the distinct values
    are computed with every OTHER applied filter taken into account (the
    column's own selections are ignored so multi-selects stay stable).

    Store-master columns are resolved over the SAME joined order/dispatch
    rows the dashboard shows; the special analysis keys (subcategory /
    product_style) are resolved AFTER the join, where their display COALESCE
    has been applied.

    Memoised on (filters, data token).  This is the single most expensive read
    path in the app (one CTE chain + DISTINCT per dimension column), and the
    UI asks for it after every filter change - identical filter states now
    cost a dict lookup instead of the whole chain.
    """
    filters = _validate_filters(filters or {})
    return {
        col: list(values)
        for col, values in _slicer_options_cached(filter_key(filters), cache_token())
    }


@lru_cache(maxsize=32)
def _slicer_options_cached(filters_key: tuple, _token: tuple) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Body of `get_slicer_options` (the `_token` argument is the cache key)."""
    filters = {col: list(values) for col, values in filters_key}
    sm_filters, special_filters = _split_filters(filters)

    out: list[tuple[str, tuple[str, ...]]] = []
    for col in [d["column"] for d in get_available_dimensions()] + sorted(_SPECIAL_DIMS):
        # The special keys always exist on j; a store-master column is exposed
        # there by requesting it as the chain's only dimension.
        col_sm_dims = [] if col in _SPECIAL_DIMS else [col]
        others_sm = {c: v for c, v in sm_filters.items() if c != col}
        others_special = {c: v for c, v in special_filters.items() if c != col}

        chain_sql, chain_params = _join_ctes(None, col_sm_dims, others_sm)
        special_sql, special_params = _special_filter_sql(others_special)
        val = f"j.{quote_ident(col)}"
        sql = f"""
        WITH {chain_sql}
        SELECT DISTINCT {val} AS val
        FROM j
        WHERE {val} IS NOT NULL
          AND NOT (j.ordered_qty <= 0 AND j.dispatched_qty <= 0){special_sql}
        ORDER BY 1
        """
        rows = execute_df(sql, chain_params + special_params)
        values = tuple(r[0] for r in rows.itertuples(index=False)) if not rows.empty else ()
        out.append((col, values))
    return tuple(out)