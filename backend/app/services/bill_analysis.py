"""
Bill No. Based Analysis (Tertiary Sales).

Everything on this page operates on ONE bill-level dataset:

    RAW TRANSACTION ROWS
        -> INTERNAL BILL ID  (FY + MONTH + BILL_NO, per store)
        -> AGGREGATED TO ONE ROW PER BILL
        -> ALL bill-based analysis (KPIs, hierarchy, distributions)

Grain rules (per requirement + user clarification):
- A bill is identified by (FY, Month, BILL_NO, Store).  The same bill_no at a
  DIFFERENT store is a different bill (bills are never collapsed across
  stores); the same bill_no in a different FY/Month is a different bill.
- A bill that contains MULTIPLE BRANDS stays ONE bill - its Qty / Bill Value /
  MRP Value / Discount are summed across all of its item rows regardless of
  brand.  Brand / Retailor / other store-master attributes are taken from the
  bill's DOMINANT line (max Qty, tie -> max Bill Value) so every level of the
  hierarchy reconciles exactly (brand totals sum to their store total).
- INTERNAL_BILL_ID (the canonical unique bill identifier used for EVERY bill
  count / grouping / Top-N list):

      `ADONIS_CODE-FY{yy}-{MM}-BILL_NO`   e.g.  `AD01-FY25-04-10023`

  FY{yy} = last two digits of the fiscal-year START year (Apr 2025 -> FY25),
  MM = zero-padded calendar month.  Because the id embeds the store code it is
  unique by construction; the same bill_no at a DIFFERENT store is a different
  bill (bills are never collapsed across stores).
- Bills with an invalid BILL_NO (NULL / blank / 'NA' / 'N/A',
  case-insensitive) are EXCLUDED from the bill-level dataset entirely, so no
  bill count, KPI, bucket or Top-N list ever sees them.

LFY figures use the SAME-PERIOD last-year window (`last_fy_start ..
lfy_ytd_end` from the shared FY service) - identical to the LFYTD basis the
rest of the application uses for growth comparisons.

Performance: the bill-level dataset is loaded ONCE (lru_cache) and every
request merely slices it in pandas - no per-KPI/per-table re-aggregation of
raw transaction rows.
"""
from __future__ import annotations

from datetime import date
from functools import lru_cache

import pandas as pd

from app.core.database import (
    cache_token,
    column_exists,
    execute_df,
    filter_key,
    quote_ident,
)
from app.services.analysis import FactSpec, get_dimension_catalog
from app.services.fy import GROWTH_BASE_EPSILON, build_fy_context, month_label

# ---------------------------------------------------------------------------
# KPI definitions (label + display format used by the frontend)
# ---------------------------------------------------------------------------
KPI_DEFS = [
    {"key": "total_bills", "label": "Total Bills", "fmt": "qty"},
    {"key": "upt", "label": "UPT (Units / Bill)", "fmt": "num2"},
    {"key": "abv", "label": "ABV (Avg Bill Value)", "fmt": "val"},
    {"key": "asp", "label": "ASP (Avg Selling Value)", "fmt": "val"},
]

QUANTITY_BUCKETS = [
    "1 Qty Bill", "2 Qty Bill", "3 Qty Bill", "4 Qty Bill", ">4 Qty Bill",
]
# Half-open [low, high) edges: exactly 3,000 lands in "3K - 5K", exactly
# 15,000 lands in "> 15K".  Same convention the module has always used for
# the old "< 3K" bucket (v < 3000).
VALUE_BUCKETS = [
    "0 - 3K", "3K - 5K", "5K - 8K", "8K - 10K", "10K - 12K", "12K - 15K", "> 15K",
]



_FY_LABEL_SQL = (
    "CASE WHEN EXTRACT(MONTH FROM tx_date) >= 4 "
    "THEN 'FY' || EXTRACT(YEAR FROM tx_date)::VARCHAR || '-' || "
    "RIGHT((EXTRACT(YEAR FROM tx_date) + 1)::VARCHAR, 2) "
    "ELSE 'FY' || (EXTRACT(YEAR FROM tx_date) - 1)::VARCHAR || '-' || "
    "RIGHT(EXTRACT(YEAR FROM tx_date)::VARCHAR, 2) END"
)


def _qty_bucket(q) -> str:
    """Classify the AGGREGATED bill qty (never raw transaction rows).

    Buckets are exact counts 1..4, everything above is ">4".  Non-integer
    quantities (e.g. 1.5 from weight-based items) are floored, so 1.5 counts
    as a 1-qty bill rather than falling through to the open-ended bucket."""
    if q is None or pd.isna(q):
        return ">4 Qty Bill"
    q = float(q)
    if q < 2:
        return "1 Qty Bill"
    if q < 3:
        return "2 Qty Bill"
    if q < 4:
        return "3 Qty Bill"
    if q < 5:
        return "4 Qty Bill"
    return ">4 Qty Bill"


def _value_bucket(v) -> str:
    """Classify the AGGREGATED bill value (never raw transaction rows).

    Edges are half-open [low, high): exactly 3000 -> "3K - 5K",
    exactly 15000 -> "> 15K".
    """
    if v is None or pd.isna(v):
        return "0 - 3K"
    v = float(v)
    if v < 3000:
        return "0 - 3K"
    if v < 5000:
        return "3K - 5K"
    if v < 8000:
        return "5K - 8K"
    if v < 10000:
        return "8K - 10K"
    if v < 12000:
        return "10K - 12K"
    if v < 15000:
        return "12K - 15K"
    return "> 15K"


def _dim_columns() -> list[str]:
    """Store-master columns usable as analysis dimensions (dynamic)."""
    return [d["column"] for d in get_dimension_catalog()]


@lru_cache(maxsize=2)
def _load_bill_dataset(fact: FactSpec) -> pd.DataFrame:
    """Build the bill-level dataset for the WHOLE fact (no filters).

    One row = one bill (FY + Month + BILL_NO within a store), with Qty /
    Bill Value / MRP Value / Discount summed across every transaction row -
    including rows of different brands inside the same bill.
    """
    store_q = quote_ident(fact.store_column)
    brand_q = quote_ident(fact.brand_column)
    date_q = quote_ident(fact.date_column)

    fine_sql = f"""
    WITH j AS (
        SELECT
            f.{quote_ident("bill_no")} AS bill_no,
            f.{date_q} AS tx_date,
            {fact.qty_expr} AS qty,
            {fact.val_expr} AS bill_val,
            f.{quote_ident("mrp_value")} AS mrp_value,
            f.{quote_ident("discount")} AS discount,
            f.{store_q} AS store_code,
            f.{brand_q} AS brand_code,
            f.{quote_ident("customer_name")} AS customer_name
        FROM {fact.schema}.{fact.table} f
        -- Invalid bill numbers (NULL / blank / 'NA' / 'N/A') are excluded
        -- from the ENTIRE bill-level dataset: no bill count ever sees them.
        WHERE bill_no IS NOT NULL
          AND TRIM(CAST(bill_no AS VARCHAR)) <> ''
          AND UPPER(TRIM(CAST(bill_no AS VARCHAR))) NOT IN ('NA', 'N/A')
    )
    SELECT
        {_FY_LABEL_SQL} AS fy_label,
        'FY' || RIGHT(CASE WHEN EXTRACT(MONTH FROM tx_date) >= 4
                      THEN EXTRACT(YEAR FROM tx_date)
                      ELSE EXTRACT(YEAR FROM tx_date) - 1 END::VARCHAR, 2)
            AS fy_short,
        EXTRACT(MONTH FROM tx_date)::INTEGER AS month_num,
        TRIM(CAST(bill_no AS VARCHAR)) AS bill_no,
        store_code,
        brand_code,
        customer_name,
        MIN(CAST(tx_date AS DATE)) AS bill_date,
        SUM(qty) AS qty,
        SUM(bill_val) AS bill_val,
        SUM(mrp_value) AS mrp_value,
        SUM(discount) AS discount,
        COUNT(*) AS row_count
    FROM j
    GROUP BY ALL
    """
    fine = execute_df(fine_sql)
    if fine.empty:
        return pd.DataFrame(
            columns=[
                "bill_key", "internal_bill_id", "fy_label", "fy_short",
                "month_num", "month",
                "bill_no", "adonis_store_code", "brand_code", "brand",
                "customer_name", "bill_date", "qty", "bill_val", "mrp_value",
                "discount", "row_count", "qty_bucket", "value_bucket",
            ]
            + _dim_columns()
        )

    fine["store_code"] = fine["store_code"].fillna("(no store)")
    fine["brand_code"] = fine["brand_code"].fillna("(no brand)")

    # Unique bill key = FY + Month + BILL_NO + store (never collapsed across
    # stores, never split by brand).
    fine["bill_key"] = (
        fine["fy_label"]
        + "|" + fine["month_num"].astype(str)
        + "|" + fine["bill_no"].astype(str)
        + "|" + fine["store_code"]
    )

    # ---- Bill-level aggregation: SUM across every line of the bill ----
    agg = (
        fine.groupby("bill_key", as_index=False, sort=False)
        .agg(
            {
                "fy_label": "first",
                "fy_short": "first",
                "month_num": "first",
                "bill_no": "first",
                "store_code": "first",
                "bill_date": "first",
                "qty": "sum",
                "bill_val": "sum",
                "mrp_value": "sum",
                "discount": "sum",
                "row_count": "sum",
            }
        )
    )

    # ---- Dominant line (brand / retailer / customer) per bill ----
    # Multi-brand bills stay ONE bill; attributes come from the line with the
    # max Qty (tie -> max Bill Value, then brand code) so hierarchy totals
    # reconcile exactly.
    ranked = fine.sort_values(
        ["bill_key", "qty", "bill_val", "brand_code"],
        ascending=[True, False, False, True],
        kind="stable",
    )
    primary = ranked.drop_duplicates(subset=["bill_key"], keep="first")[
        ["bill_key", "brand_code", "customer_name"]
    ].rename(columns={"brand_code": "_p_brand_code", "customer_name": "_p_customer"})
    agg = agg.merge(primary, on="bill_key", how="left")

    # ---- Store-master dimension attributes for the dominant line ----
    dim = execute_df("SELECT * FROM store_master.store_details")
    dim_cols = [c for c in _dim_columns() if c in dim.columns]
    dim = dim[["adonis_store_code", "brand_code"] + dim_cols].rename(
        columns={"adonis_store_code": "store_code", "brand_code": "_p_brand_code"}
    )
    agg = agg.merge(dim, on=["store_code", "_p_brand_code"], how="left")

    agg = agg.rename(columns={"store_code": "adonis_store_code", "_p_customer": "customer_name"})
    agg["brand_code"] = agg.pop("_p_brand_code")

    # Month label (Apr -> Mar fiscal display, same convention as Monthwise).
    agg["month"] = agg["month_num"].apply(lambda m: month_label(int(m)))

    # Normalise the date column once so per-request period windowing never
    # pays the datetime-conversion cost again on the full dataset.
    agg["bill_date"] = pd.to_datetime(agg["bill_date"], errors="coerce")

    # ---- INTERNAL_BILL_ID (canonical unique bill id, spec format) ----
    # ADONIS_CODE-FY{yy}-{MM}-BILL_NO, e.g. AD01-FY25-04-10023.  The store
    # code is part of the id, so it is unique by construction (bill_key =
    # FY|Month|bill_no|store already groups one row per bill).
    agg["internal_bill_id"] = (
        agg["adonis_store_code"].astype(str)
        + "-" + agg["fy_short"].astype(str)
        + "-" + agg["month_num"].astype(int).map(lambda m: f"{m:02d}")
        + "-" + agg["bill_no"].astype(str)
    )

    # Buckets are classified from the AGGREGATED bill figures only.
    agg["qty_bucket"] = agg["qty"].apply(_qty_bucket)
    agg["value_bucket"] = agg["bill_val"].apply(_value_bucket)

    return agg


# ---------------------------------------------------------------------------
# Filtering / KPI math
# ---------------------------------------------------------------------------
def _filtered_bills(fact: FactSpec, filters: dict[str, list[str]]) -> pd.DataFrame:
    """Validate the filters and slice the cached bill dataset in pandas.

    A single boolean mask is built across all filter columns (one pass, no
    intermediate DataFrame copies) so large filter sets stay fast.
    """
    ds = _load_bill_dataset(fact)
    mask = None
    for col, values in (filters or {}).items():
        if not values:
            continue
        if col not in ds.columns:
            if column_exists("store_master", "store_details", col):
                raise ValueError(
                    f"Filter column '{col}' is not part of the bill-level dataset"
                )
            raise ValueError(f"Unknown filter column: {col}")
        col_mask = ds[col].isin(values)
        mask = col_mask if mask is None else (mask & col_mask)
    if mask is None:
        return ds.reset_index(drop=True)
    return ds[mask].reset_index(drop=True)


def _growth(cfy, lfy):
    """Sign-correct ((CFY - LFY) / |LFY|) * 100 - safely: None (rendered as
    '-') when LFY is 0 / None / missing. Never NaN / Infinity.

    The base is taken as an absolute value so the sign of the result always
    means "better / worse", even when the prior period was negative (LFY
    -1,00,000 -> CFY +2,00,000 is +300% growth, not -300%).
    """
    try:
        if cfy is None or lfy is None or pd.isna(cfy) or pd.isna(lfy) or lfy == 0:
            return None
    except TypeError:
        return None
    return (cfy - lfy) / abs(lfy) * 100.0


def _period_metrics(df: pd.DataFrame) -> dict:
    """All bill KPIs for one period slice of the bill-level dataset."""
    if df.empty:
        return {
            "total_bills": 0, "qty": 0.0, "val": 0.0, "days": 0,
            "upt": None, "asp": None, "abv": None,
            "bills_per_day": None, "qty_per_day": None, "val_per_day": None,
        }
    bills = float(len(df))
    qty = float(df["qty"].sum())
    val = float(df["bill_val"].sum())
    days = int(df["bill_date"].nunique())

    def _div(n, d):
        if not d:
            return None
        return float(n) / float(d)

    return {
        "total_bills": bills,
        "qty": qty,
        "val": val,
        "days": days,
        "upt": _div(qty, bills),
        "asp": _div(val, qty),
        "abv": _div(val, bills),
        "bills_per_day": _div(bills, days),
        "qty_per_day": _div(qty, days),
        "val_per_day": _div(val, days),
    }


def _kpi_cells(cfy_m: dict, lfy_m: dict) -> list[dict]:
    """The canonical KPI cell used EVERYWHERE (KPI cards, every hierarchy row,
    every distribution bucket cell): all four bill KPIs each carrying the
    LFY / CFY / Growth % trio that the UI renders as one stacked value."""
    out = []
    for k in KPI_DEFS:
        key = k["key"]
        c = cfy_m.get(key)
        l = lfy_m.get(key)
        out.append(
            {
                "key": key,
                "label": k["label"],
                "fmt": k["fmt"],
                "cfy": c,
                "lfy": l,
                "growth_pct": _growth(c, l),
            }
        )
    return out


def _kpis(cfy_m: dict, lfy_m: dict) -> list[dict]:
    """Alias kept for the top-level KPI cards; delegates to the canonical
    cell builder so every level shares the exact same KPI shape."""
    return _kpi_cells(cfy_m, lfy_m)


@lru_cache(maxsize=1)
def _bill_dimensions_cached() -> tuple[tuple[str, str], ...]:
    core = (
        ("adonis_store_code", "Store"),
        ("brand", "Brand"),
        ("retailer_name", "Retailor"),
        ("month", "Month"),
    )
    core_cols = {col for col, _label in core}
    extra = tuple(
        (d["column"], d["label"])
        for d in get_dimension_catalog()
        if d["column"] not in core_cols
    )
    return core + extra


def _bill_dimensions() -> list[dict]:
    """Picker options: Store / Brand / Retailor / Month (+ discovered dims).

    Memoised: the picker payload is rebuilt from the (already cached) dimension
    catalog on every validation call, so this keeps dict churn off the hot path.
    """
    return [{"column": col, "label": label} for col, label in _bill_dimensions_cached()]


# ---------------------------------------------------------------------------
# Hierarchy (dynamic, 1-2 levels, grand total at the FIRST level)
# ---------------------------------------------------------------------------
def _fmt_dim(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "(blank)"
    return str(v)


def _ordered_values(df: pd.DataFrame, dim: str) -> list:
    """Dimension values in display order: fiscal order for Month, else by
    bill count descending."""
    if df.empty:
        return []
    if dim == "month":
        vals = df[["month", "month_num"]].drop_duplicates()
        return list(vals.sort_values("month_num")["month"])
    counts = df.groupby(dim, dropna=False, sort=False).size()
    return list(counts.sort_values(ascending=False).index)


def _union_values(cfy: pd.DataFrame, lfy: pd.DataFrame, dim: str) -> list:
    """CFY values first (by CFY volume), then any LFY-only values (stores /
    brands with no sales this year) so level-1 totals reconcile with the KPI."""
    vals = _ordered_values(cfy, dim)
    if lfy.empty:
        return vals
    seen = {str(v) for v in vals}
    return vals + [v for v in _ordered_values(lfy, dim) if str(v) not in seen]


def _hierarchy_rows(cfy: pd.DataFrame, lfy: pd.DataFrame, dims: list[str]) -> list[dict]:
    """Rows for the dynamic N-level row hierarchy (1..3 dimension columns).

    Level-1 rows ARE the grand total at the selected dimension's grain: every
    KPI cell in a row is computed by re-aggregating over ALL bills of that
    row's own subset (e.g. "Brand X" totals come from all Brand X bills
    directly, never as an average of its Store child rows).  Deeper levels
    drill under the parent subset, so Brand->Store shows every store total
    even when a store only transacted in LFY.  Each row carries `kpis` = the
    four bill KPIs, each with its LFY / CFY / Growth % trio for the stacked
    same-cell rendering.
    """
    dims = dims or ["adonis_store_code"]
    dims = dims[:3]
    rows: list[dict] = []

    def _sub(df, col, val):
        """Rows of `df` where `col` == val (NaN-safe)."""
        if df is None or df.empty:
            return df
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return df[df[col].isna()]
        return df[df[col] == val]

    def _walk(df_c, df_l, level, parent):
        if level >= len(dims) or df_c is None:
            return
        dim = dims[level]
        for v in _union_values(df_c, df_l, dim):
            sub_c = _sub(df_c, dim, v)
            sub_l = _sub(df_l, dim, v)
            pv = None if v is None or (isinstance(v, float) and pd.isna(v)) else v
            row: dict = {"_level": level + 1, "_label": _fmt_dim(v)}
            for i, d in enumerate(dims[: level + 1]):
                row[d] = parent[d] if i < level else pv
            # GENUINE re-aggregation at the row's own grain (never an average
            # of child rows) - all four KPIs with LFY / CFY / Growth.
            row["kpis"] = _kpi_cells(_period_metrics(sub_c), _period_metrics(sub_l))
            row["bills"] = float(len(sub_c))
            row["bill_val"] = float(sub_c["bill_val"].sum()) if len(sub_c) else 0.0
            rows.append(row)
            _walk(sub_c, sub_l, level + 1, row)

    _walk(cfy, lfy, 0, {})
    return rows


# ---------------------------------------------------------------------------
# Distributions (buckets classified on AGGREGATED bill figures)
# ---------------------------------------------------------------------------
def _distribution_rows(
    cfy: pd.DataFrame, lfy: pd.DataFrame, dim: str, bucket_col: str, bucket_order: list[str]
) -> list[dict]:
    """Bucket distribution pivoted so that BUCKETS ARE THE COLUMN HEADERS.

    Returns one row per dimension value (or a single `(All)` row when
    dim == "all").  Every bucket cell holds ALL FOUR bill KPIs (via
    `_kpi_cells`) for the bills in that (dim value, bucket) slice - the full
    LFY / CFY / Growth % trio per KPI, rendered in one stacked cell.  An
    "All Bills" cell wraps the whole row so "sum of buckets == all bills" is
    visually provable.  Every figure is a genuine re-aggregation of the
    BILL-level rows (never transaction rows, never an average of children).
    """
    is_all = dim in (None, "", "all")
    key = "_dim" if is_all else dim
    if is_all:
        if not cfy.empty:
            cfy = cfy.assign(_dim="(All)")
        if not lfy.empty:
            lfy = lfy.assign(_dim="(All)")

    def _group_sums(df, group_key=None):
        """{dim_value: {bucket: {bills, qty, val}}} - ONE groupby pass."""
        gk = group_key or key
        if df is None or df.empty or bucket_col not in df.columns:
            return {}
        out: dict = {}
        for (k, b), sub in df.groupby([gk, bucket_col], dropna=False, sort=False):
            out.setdefault(_fmt_dim(k), {})[_fmt_dim(b)] = {
                "bills": float(len(sub)),
                "qty": float(sub["qty"].sum()),
                "val": float(sub["bill_val"].sum()),
            }
        return out

    gc = _group_sums(cfy)
    gl = _group_sums(lfy)
    if not is_all:
        # "(All)" summary row = genuine re-aggregation over the WHOLE selected
        # context (all dimension values pooled), shown above the detail rows.
        gc["(All)"] = _group_sums(cfy.assign(_dim="(All)"), "_dim").get("(All)", {})
        gl["(All)"] = _group_sums(lfy.assign(_dim="(All)"), "_dim").get("(All)", {})

    def _totals(bmap):
        return {
            "bills": sum(a["bills"] for a in bmap.values()),
            "qty": sum(a["qty"] for a in bmap.values()),
            "val": sum(a["val"] for a in bmap.values()),
        }

    def _metrics(agg):
        bills = agg.get("bills", 0.0)
        qty = agg.get("qty", 0.0)
        val = agg.get("val", 0.0)

        def _div(n, d):
            return float(n) / float(d) if d else None

        return {
            "total_bills": bills,
            "qty": qty,
            "val": val,
            "upt": _div(qty, bills),
            "abv": _div(val, bills),
            "asp": _div(val, qty),
            "days": 0,
        }

    def _cell(c_agg, l_agg):
        return _kpi_cells(_metrics(c_agg), _metrics(l_agg))

    def _finalise_total_bills(cell, c_tot, l_tot):
        """Bill-count distribution cells: Cont% = share of the ROW's bill total
        and Growth = the CONT% change (LFY -> CFY, user-confirmed contract) -
        NOT growth on the raw bill counts."""
        for item in cell:
            if item["key"] == "total_bills":
                item["share_cfy_pct"] = (
                    item["cfy"] / c_tot["bills"] * 100.0 if c_tot["bills"] else 0.0
                )
                item["share_lfy_pct"] = (
                    item["lfy"] / l_tot["bills"] * 100.0 if l_tot["bills"] else 0.0
                )
                item["growth_pct"] = _growth(item["share_cfy_pct"], item["share_lfy_pct"])
        return cell

    dim_vals = ["(All)"] if is_all else ["(All)"] + _union_values(cfy, lfy, dim)
    rows: list[dict] = []
    for d1v in dim_vals:
        dv = None if pd.isna(d1v) else d1v
        cb = gc.get(_fmt_dim(d1v), {})
        lb = gl.get(_fmt_dim(d1v), {})
        c_total = _totals(cb)
        l_total = _totals(lb)
        cells: dict[str, list[dict]] = {}
        for bucket in bucket_order:
            cells[bucket] = _finalise_total_bills(
                _cell(cb.get(_fmt_dim(bucket), {}), lb.get(_fmt_dim(bucket), {})),
                c_total,
                l_total,
            )
        cells["All Bills"] = _finalise_total_bills(_cell(c_total, l_total), c_total, l_total)
        rows.append({"dim_value": dv, "cells": cells})
    return rows


def _iso_date(v) -> str | None:
    try:
        if v is None or pd.isna(v):
            return None
        return pd.Timestamp(v).date().isoformat()
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Top Bills (Top-N by bill value, LFY and CFY)
# ---------------------------------------------------------------------------
def _top_bill_rows(df: pd.DataFrame, n: int) -> list[dict]:
    if df is None or df.empty or n <= 0:
        return []
    # Top-N must ALWAYS come back as a strict, deterministic rank 1..n:
    # bill_val desc, ties -> earliest bill_date, then internal_bill_id.
    # nlargest() offers no tie-break contract (equal-value bills can flip
    # order between / within queries), so we sort explicitly and stably.
    top = df.dropna(subset=["bill_val"]).sort_values(
        ["bill_val", "bill_date", "internal_bill_id"],
        ascending=[False, True, True],
        kind="stable",
    ).head(n)
    out = []
    for rank, (_, r) in enumerate(top.iterrows(), start=1):
        out.append(
            {
                # Server-side rank: 1..n, always in exactly this order.
                "rank": rank,
                "internal_bill_id": str(r.get("internal_bill_id", "")),
                "bill_date": _iso_date(r.get("bill_date")),
                "month": None if pd.isna(r.get("month")) else r.get("month"),
                "adonis_store_code": (
                    None if pd.isna(r.get("adonis_store_code")) else r.get("adonis_store_code")
                ),
                "brand": None if pd.isna(r.get("brand")) else r.get("brand"),
                "retailer_name": (
                    None if pd.isna(r.get("retailer_name")) else r.get("retailer_name")
                ),
                "qty": float(r["qty"]),
                "bill_val": float(r["bill_val"]),
            }
        )
    return out


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def run_bill_analysis(
    fact: FactSpec,
    filters: dict[str, list[str]],
    hierarchy: list[str] | None = None,
    qty_dim: str | None = None,
    value_dim: str | None = None,
    top_n: int = 25,
) -> dict:
    """Bill No. Based Analysis payload (KPI cards, hierarchy, distributions,
    Top Bills) for the selected hierarchy + slicers.

    Memoised on (fact, filters, hierarchy, qty/value dimension, top-N, data
    token): the tab re-requests this on every hierarchy or slicer change and
    the Excel export re-uses it right after a render, so identical view states
    now cost a dict lookup.  Normalising the key (sorted filter keys/values)
    cannot change the result - the filters are AND-ed `IN (...)` clauses and
    the hierarchy order is preserved exactly as sent.
    """
    return _bill_analysis_cached(
        fact,
        filter_key(filters),
        tuple(hierarchy or []),
        (qty_dim or "all"),
        (value_dim or "all"),
        int(top_n) if str(top_n).lstrip("-").isdigit() else 25,
        cache_token(),
    )


@lru_cache(maxsize=32)
def _bill_analysis_cached(
    fact: FactSpec,
    filters_key: tuple,
    hierarchy_key: tuple,
    qty_dim_key: str,
    value_dim_key: str,
    top_n_key: int,
    _token: tuple,
) -> dict:
    """Body of `run_bill_analysis` (the `_token` argument is the cache key)."""
    from app.services.analysis import _get_global_max_date

    filters = {col: list(values) for col, values in filters_key}
    hierarchy = list(hierarchy_key)
    qty_dim = qty_dim_key
    value_dim = value_dim_key
    top_n = top_n_key

    available = {d["column"] for d in _bill_dimensions()}

    # Row hierarchy: 0..3 distinct dimension columns.  An empty list simply
    # means "overall grand total" (no per-dimension rows).
    hierarchy = [d for d in (hierarchy or []) if d]
    bad = [d for d in hierarchy if d not in available]
    if bad:
        raise ValueError(f"Unknown hierarchy dimension(s): {bad}")
    if len(set(hierarchy)) != len(hierarchy):
        raise ValueError("Hierarchy dimensions must be distinct")
    hierarchy = hierarchy[:3]

    # "all" is accepted for both distribution dimensions (overall buckets).
    qty_dim = (qty_dim or "all").strip().lower()
    value_dim = (value_dim or "all").strip().lower()
    for name, dim in (
        ("quantity-distribution", qty_dim),
        ("bill-value-distribution", value_dim),
    ):
        if dim != "all" and dim not in available:
            raise ValueError(f"Unknown {name} dimension: {dim}")

    try:
        top_n = int(top_n)
    except (TypeError, ValueError):
        top_n = 25
    top_n = max(1, min(top_n, 500))

    ds = _filtered_bills(fact, filters)
    max_date = _get_global_max_date(fact)
    if max_date is None:
        max_date = date.today()  # noqa: DTZ011
    if hasattr(max_date, "date") and not isinstance(max_date, date):
        max_date = max_date.date()
    fy = build_fy_context(max_date)

    meta = {
        "transaction_rows": 0,
        "bill_count": 0,
        "grain": (
            "ADONIS_CODE-FY{yy}-{MM}-BILL_NO per store (one bill, never split "
            "by brand; invalid 'NA'/blank bill numbers excluded)"
        ),
    }
    result = {
        "fy_context": fy.to_dict(),
        "lfy_basis": f"same period last year (through {fy.lfy_ytd_end.isoformat()})",
        "meta": meta,
        "dimensions": _bill_dimensions(),
        "kpis": [],
        "hierarchy": {"dims": hierarchy, "rows": []},
        "qty_distribution": {
            "dim": qty_dim,
            "buckets": QUANTITY_BUCKETS,
            "rows": [],
        },
        "value_distribution": {
            "dim": value_dim,
            "buckets": VALUE_BUCKETS,
            "rows": [],
        },
        "top_bills": {"n": top_n, "cfy": [], "lfy": []},
    }

    if ds.empty:
        result["kpis"] = _kpis(_period_metrics(ds), _period_metrics(ds))
        return result

    meta["transaction_rows"] = int(_load_bill_dataset(fact)["row_count"].sum())

    cfy = ds[ds["fy_label"] == fy.current_fy_label]
    lfy_end = pd.Timestamp(fy.lfy_ytd_end)
    lfy = ds[(ds["fy_label"] == fy.last_fy_label) & (ds["bill_date"] <= lfy_end)]

    cfy_m = _period_metrics(cfy)
    meta["bill_count"] = cfy_m["total_bills"]

    result["kpis"] = _kpis(cfy_m, _period_metrics(lfy))
    if hierarchy:
        result["hierarchy"]["rows"] = _hierarchy_rows(cfy, lfy, hierarchy)
    result["qty_distribution"]["rows"] = _distribution_rows(
        cfy, lfy, qty_dim, "qty_bucket", QUANTITY_BUCKETS
    )
    result["value_distribution"]["rows"] = _distribution_rows(
        cfy, lfy, value_dim, "value_bucket", VALUE_BUCKETS
    )
    result["top_bills"]["cfy"] = _top_bill_rows(cfy, top_n)
    result["top_bills"]["lfy"] = _top_bill_rows(lfy, top_n)
    return result

