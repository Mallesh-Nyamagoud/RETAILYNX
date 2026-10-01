"""
Bill_No Based KPI Analysis ("Module V" - new subpage).

This module REUSES the cached, bill-level dataset that
`app/services/bill_analysis.py` already builds (one row per bill, with the
canonical INTERNAL_BILL_ID = `ADONIS_CODE-FY{yy}-{MM}-BILL_NO`, invalid
'NA'/blank bill numbers excluded, bill_date = first sale date of the bill,
month/month_num derived from that date).  Reusing the existing loader keeps a
SINGLE source of truth for the bill grain instead of a parallel filter system.

NEW capabilities layered on top (none exist in the original module yet):

  * Date-range mode (start/end) that overrides the FY window and shifts LFY
    back exactly one year (req §5).
  * Internal Month field usable as a filter dimension.
  * SPD[QTY] / SPD[VAL] KPIs with the BRAND-ANCHORED Active_Days rule (§3):
        Active_Days = MAX(bill_date in dataset)
                      - MIN(bill_date where brand = X, across ALL retailers)
                      + 1
    The window is anchored to the brand's GLOBAL first sale date - NOT the
    specific store/retailer's own first sale date - running through to the
    dataset's max date.  This applies EVEN when slicing by a specific
    retailer: a retailer's SPD for Brand X still uses Brand X's overall first
    sale date.  NOTE: this means a retailer's SPD can look artificially
    diluted if they stocked a brand later than other retailers - intentional
    per business rule, NOT a bug. (Flagged in code + README §12.)
  * Top-N is a free user input (any positive count, no preset snapping).
  * Top Bills brand-contribution breakdown for the Retailer-only view (§9).
  * Pivot-style dimensional summary whose order follows the user's dimension
    selection order (§6).

All aggregation is server-side (pandas slicing of the cached bill dataset).
No client-side aggregation of raw transactions.
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
from app.services import bill_analysis as _ba
from app.services.analysis import FactSpec, get_dimension_catalog
from app.services.fy import GROWTH_BASE_EPSILON, build_fy_context, safe_div

# ---------------------------------------------------------------------------
# KPI definitions (label + display format used by the frontend).
# SPD[QTY]/SPD[VAL] are NEW vs. the original module.
# ---------------------------------------------------------------------------
KPI_DEFS = [
    {"key": "total_bills", "label": "Total Bills", "fmt": "qty"},
    {"key": "upt", "label": "UPT (Units / Bill)", "fmt": "num2"},
    {"key": "abv", "label": "ABV (Avg Bill Value)", "fmt": "val"},
    {"key": "asp", "label": "ASP (Avg Selling Value)", "fmt": "val"},
    {"key": "spd_qty", "label": "SPD[QTY] (Units / Day)", "fmt": "num2"},
    {"key": "spd_val", "label": "SPD[VAL] (Rs / Day)", "fmt": "val"},
    {"key": "active_days", "label": "Active Days", "fmt": "qty"},
]

# Reuse the existing bucket labels + edge convention (half-open [low, high):
# exactly 3000 -> "3K - 5K", exactly 15000 -> "> 15K").
QUANTITY_BUCKETS = _ba.QUANTITY_BUCKETS
VALUE_BUCKETS = _ba.VALUE_BUCKETS


# ---------------------------------------------------------------------------
# Dataset + Active_Days (brand-anchored, req §3)
# ---------------------------------------------------------------------------
def _load_dataset(fact: FactSpec) -> pd.DataFrame:
    """The cached bill-level dataset (reused from bill_analysis)."""
    return _ba._load_bill_dataset(fact)


def _brand_global_first_sale(fact: FactSpec) -> pd.DataFrame:
    """Per-brand GLOBAL first sale date across ALL retailers (req §3).

    Active_Days = MAX(bill_date in dataset) - MIN(bill_date where brand=X,
    across all retailers) + 1.  Computed over the RAW transaction table so a
    brand's first-ever sale (even at a single store) is the anchor.  (Currently
    unused - `_active_days` derives the same figure from the cached bill
    dataset's bill_date per brand - but kept for explicit raw-table fallback.)
    """
    sq = quote_ident
    sql = (
        f"SELECT {sq(fact.brand_column)} AS brand_code, "
        f"MIN(CAST({sq(fact.date_column)} AS DATE)) AS first_sale_date "
        f"FROM {fact.schema}.{fact.table} "
        f"WHERE {sq(fact.date_column)} IS NOT NULL "
        f"  AND bill_no IS NOT NULL "
        f"  AND TRIM(CAST(bill_no AS VARCHAR)) <> '' "
        f"  AND UPPER(TRIM(CAST(bill_no AS VARCHAR))) NOT IN ('NA','N/A') "
        f"GROUP BY {sq(fact.brand_column)}"
    )
    df = execute_df(sql)
    if df.empty:
        return df
    df["first_sale_date"] = pd.to_datetime(df["first_sale_date"])
    return df


def _active_days(full_df: pd.DataFrame, brand, max_date) -> int:
    """Active_Days window for the SELECTED context (req §3).

    Rule: dataset MAX(bill_date) - brand's GLOBAL MIN(bill_date) + 1.  The
    first-sale date is taken from `full_df` (the WHOLE filtered dataset, all
    retailers) so a retailer's SPD for Brand X still uses Brand X's overall
    first sale date, NOT the retailer's own first sale date.  May make a
    retailer's SPD look diluted - intentional per business rule, NOT a bug.
    """
    max_ts = pd.to_datetime(max_date)
    if max_ts.tz is not None:
        max_ts = max_ts.tz_localize(None)
    if "brand" not in full_df.columns or full_df.empty:
        first = pd.to_datetime(full_df["bill_date"].min()) if "bill_date" in full_df.columns else max_ts
    else:
        slice_ = full_df[full_df["brand"] == brand] if brand is not None else full_df
        if slice_.empty or "bill_date" not in slice_.columns:
            first = max_ts
        else:
            first = pd.to_datetime(slice_["bill_date"].min())
    if pd.isna(first):
        return 0
    return max(int((max_ts - first).days) + 1, 0)


def _metrics(df: pd.DataFrame, active_days: int) -> dict:
    """All KPIs for one period slice, including SPD (using Active_Days)."""
    if df.empty:
        return {
            "total_bills": 0, "qty": 0.0, "val": 0.0, "active_days": int(active_days),
            "upt": None, "abv": None, "asp": None,
            "spd_qty": None, "spd_val": None,
        }
    bills = float(len(df))
    qty = float(df["qty"].sum())
    val = float(df["bill_val"].sum())
    d = active_days
    return {
        "total_bills": bills,
        "qty": qty,
        "val": val,
        "active_days": int(d),
        "upt": safe_div(qty, bills),
        "abv": safe_div(val, bills),
        "asp": safe_div(val, qty),
        "spd_qty": safe_div(qty, d),
        "spd_val": safe_div(val, d),
    }


def _growth(cfy, lfy):
    """Sign-correct ((CFY - LFY) / |LFY|) * 100 -> None (rendered as 'N/A')
    when LFY is 0/None or otherwise non-numeric.  Never divides by zero, never
    NaN/Infinity.  The absolute base keeps the sign meaningful ("better /
    worse") when the prior period is negative."""
    try:
        if cfy is None or lfy is None or pd.isna(cfy) or pd.isna(lfy) or lfy == 0:
            return None
        return float(cfy - lfy) / abs(float(lfy)) * 100.0
    except TypeError:
        return None


def _kpi_cell(
    cfy_m: dict,
    lfy_m: dict,
    cfy_total: dict | None = None,
    lfy_total: dict | None = None,
) -> list[dict]:
    """Return LFY, CFY, contribution and growth for every non-Top-Bills KPI."""
    cfy_total = cfy_total or cfy_m
    lfy_total = lfy_total or lfy_m
    out = []
    for k in KPI_DEFS:
        key = k["key"]
        c = cfy_m.get(key)
        l = lfy_m.get(key)
        c_total = cfy_total.get(key)
        l_total = lfy_total.get(key)
        out.append({
            "key": key,
            "label": k["label"],
            "fmt": k["fmt"],
            "cfy": c,
            "lfy": l,
            "contribution_cfy_pct": safe_div(c, c_total) * 100.0 if c_total else None,
            "contribution_lfy_pct": safe_div(l, l_total) * 100.0 if l_total else None,
            "growth_pct": None if key == "active_days" else _growth(c, l),
        })
    return out
def _na_or(v):
    """None if null/NaN else the value (used for nullable dimension attrs)."""
    return None if (v is None or (isinstance(v, float) and pd.isna(v))) else v


def snap_top_n(n) -> int:
    """Accept the user-selected Top-N size without preset-step restrictions."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = 25
    return max(1, n)
# ---------------------------------------------------------------------------
# Period windowing (FY-based OR custom date range) - req §5
# ---------------------------------------------------------------------------
def _slice_by_date_range(ds: pd.DataFrame, start, end) -> pd.DataFrame:
    """Inclusive [start, end] date filter on bill_date."""
    if start is None and end is None:
        return ds
    mask = pd.Series(True, index=ds.index)
    bd = pd.to_datetime(ds["bill_date"])
    if start is not None:
        mask &= bd >= pd.to_datetime(start)
    if end is not None:
        mask &= bd <= pd.to_datetime(end)
    return ds[mask].reset_index(drop=True)


def _to_date(v) -> date:
    return pd.to_datetime(v).date()


def _shift_back_year(d: date) -> date:
    """Same calendar date one year earlier, clamping Feb-29 to Feb-28."""
    try:
        return d.replace(year=d.year - 1)
    except ValueError:
        return d.replace(year=d.year - 1, day=28)


def _period_windows(ds: pd.DataFrame, date_range: dict | None):
    """Return (cfy_df, lfy_df, window_meta) honoring req §5.

    If a custom date_range {start, end} is supplied:
      CFY = dates within [start, end]
      LFY = the SAME window shifted back exactly one year
    Else (FY mode):
      CFY = current FY up to the dataset max date (FY-TD basis the rest of the
      app uses for growth comparisons)
      LFY = last FY, same-day-prior-year window.
    """
    if ds.empty or "bill_date" not in ds.columns:
        return pd.DataFrame(), pd.DataFrame(), {"mode": "date-range"}

    max_date = pd.to_datetime(ds["bill_date"].max())
    if max_date.tz is not None:
        max_date = max_date.tz_localize(None)
    max_date = max_date.date()

    if date_range and date_range.get("start") and date_range.get("end"):
        try:
            start = _to_date(date_range["start"])
            end = _to_date(date_range["end"])
            l_start = _shift_back_year(start)
            l_end = _shift_back_year(end)
        except (ValueError, TypeError):
            start = end = l_start = l_end = None
        cfy = _slice_by_date_range(ds, start, end)
        lfy = _slice_by_date_range(ds, l_start, l_end)
        return cfy, lfy, {
            "mode": "date-range",
            "cfy_start": start.isoformat() if start else None,
            "cfy_end": end.isoformat() if end else None,
            "lfy_start": l_start.isoformat() if l_start else None,
            "lfy_end": l_end.isoformat() if l_end else None,
        }

    # FY-based default (identical LFYTD basis the rest of the app uses).
    fy = build_fy_context(max_date)
    cfy = ds[ds["fy_label"] == fy.current_fy_label].reset_index(drop=True)
    lfy = ds[
        (ds["fy_label"] == fy.last_fy_label)
        & (pd.to_datetime(ds["bill_date"]) <= pd.to_datetime(fy.lfy_ytd_end))
    ].reset_index(drop=True)
    return cfy, lfy, {
        "mode": "fy",
        "fy_context": fy.to_dict(),
        "lfy_basis": f"same period last year (through {fy.lfy_ytd_end.isoformat()})",
    }


def _period_bounds(df: pd.DataFrame):
    if df is None or df.empty or "bill_date" not in df.columns:
        return [None, None]
    return [_ba._iso_date(df["bill_date"].min()), _ba._iso_date(df["bill_date"].max())]


# ---------------------------------------------------------------------------
# Dimensions / slicers (reuse existing catalog + cross-filter pattern)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _bill_dimensions_cached() -> tuple[tuple[str, str], ...]:
    core = (
        ("adonis_store_code", "Store"),
        ("brand", "Brand"),
        ("retailer_name", "Retailer"),
        ("month", "Internal Month"),
    )
    core_cols = {col for col, _label in core}
    extra = tuple(
        (d["column"], d["label"])
        for d in get_dimension_catalog()
        if d["column"] not in core_cols
    )
    return core + extra


def bill_dimensions() -> list[dict]:
    """Picker options: Store / Brand / Retailer / Internal Month + discovered.

    `month` (and `month_num`) is the Internal Month field (req §1) - usable
    both as a filter and as a selectable dimension for month-wise analysis.
    `adonis_store_code` (Store) is the canonical store code column on the bill
    dataset and is always offered too.

    Memoised (the underlying dimension catalog is itself cached): this is
    called on every validation and appears twice in the analysis response.
    """
    return [{"column": col, "label": label} for col, label in _bill_dimensions_cached()]


def _distinct_col_values(df: pd.DataFrame, col: str) -> list[str]:
    if col not in df.columns:
        return []
    vals = df[col].dropna().map(lambda v: "" if pd.isna(v) else str(v))
    out = [v for v in vals.unique() if v]
    out.sort()
    return out


def get_slicers(fact: FactSpec, filters: dict[str, list[str]] | None = None) -> dict:
    """Cross-filter aware slicer options (same semantics as the existing app).

    Each column's options respect every OTHER applied filter (its own
    selections are ignored so a multi-select stays stable while narrowing the
    rest).  Implemented by applying all OTHER filters to the cached dataset
    and reading distinct values for the target column.

    Memoised on (fact, filters, data token): the bill dataset itself is already
    cached, but the per-dimension subsetting used to be redone for every
    dimension on every slicer request.
    """
    return {
        col: list(values)
        for col, values in _slicers_cached(fact, filter_key(filters), cache_token())
    }


@lru_cache(maxsize=32)
def _slicers_cached(fact: FactSpec, filters_key: tuple, _token: tuple) -> tuple[tuple[str, tuple], ...]:
    """Body of `get_slicers` (the `_token` argument is the cache key only)."""
    ds = _load_dataset(fact)
    f = {col: list(values) for col, values in filters_key}
    fcols = [k for k, vals in f.items() if vals and k in ds.columns]
    out: list[tuple[str, tuple]] = []
    # Cross-filtered subset narrowed by ALL OTHER applied filters.  Every
    # column that is NOT itself filtered reuses this single precomputed subset
    # (the old code re-applied every other filter once per dimension column).
    all_others = None
    for dim in bill_dimensions():
        col = dim["column"]
        if col not in ds.columns:
            continue
        others = [k for k in fcols if k != col]
        if not others:
            sub = ds
        elif others == fcols:
            if all_others is None:
                all_others = ds
                for k in fcols:
                    all_others = all_others[all_others[k].isin(f[k])]
            sub = all_others
        else:  # rare: the column's own selection must be ignored
            sub = ds
            for k in others:
                sub = sub[sub[k].isin(f[k])]
        out.append((col, tuple(_distinct_col_values(sub, col))))
    month_nums = (
        sorted([int(m) for m in ds["month_num"].dropna().unique().tolist()])
        if not ds.empty and "month_num" in ds.columns
        else []
    )
    out.append(("month_num", tuple(month_nums)))
    return tuple(out)


def _validate_filters(fact: FactSpec, filters: dict) -> dict:
    """Validate that every filter column is a real column on the bill dataset."""
    ds = _load_dataset(fact)
    for col in filters or {}:
        if col in ("month_num",):
            continue
        if col not in ds.columns:
            raise ValueError(f"Unknown filter column: {col}")
    return filters


def _fmt_dim(v):
    """Stringify a dimension value for use as a dict key (NaN-safe)."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "(blank)"
    s = str(v)
    return s if s != "nan" else "(blank)"


def _dim_value(v):
    """None-safe value for display / keying."""
    return None if (v is None or (isinstance(v, float) and pd.isna(v))) else v


# ---------------------------------------------------------------------------
# Dimensional summary (pivot-style, §6)
# ---------------------------------------------------------------------------
def _ordered_dim_values(df: pd.DataFrame, dim: str) -> list:
    """Display order: fiscal month order for month/month_num, else by CFY
    total bill value descending (stable across CFY/LFY)."""
    if df.empty or dim not in df.columns:
        return []
    if dim in ("month", "month_num"):
        vals = df[["month", "month_num"]].drop_duplicates()
        return list(vals.sort_values("month_num")["month"])
    counts = df.groupby(dim, dropna=False, sort=False).agg(val=("bill_val", "sum"))
    return list(counts.sort_values("val", ascending=False).index)


def _union_dim_values(cfy: pd.DataFrame, lfy: pd.DataFrame, dim: str) -> list:
    """CFY values first (by CFY volume), then any LFY-only values, so level-1
    totals reconcile with the KPI card."""
    vals = _ordered_dim_values(cfy, dim)
    if lfy.empty:
        return vals
    seen = {str(v) for v in vals}
    return vals + [v for v in _ordered_dim_values(lfy, dim) if str(v) not in seen]


def _sub(df: pd.DataFrame, col: str, val) -> pd.DataFrame:
    """Rows of `df` where `col` == val (NaN-safe)."""
    if df is None or df.empty:
        return df
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return df[df[col].isna()]
    return df[df[col] == val]


def _dimension_summary_rows(
    cfy: pd.DataFrame,
    lfy: pd.DataFrame,
    dims: list[str],
    active_days: int,
) -> list[dict]:
    """Pivot-style summary table (req §6).

    Rules:
      * No dims  -> single grand-total row.
      * 1 dim    -> rows = each dimension value + an '(All)' grand-total row
        that is a GENUINE re-aggregation at the selected grain (never an
        average of children).  Single-dim "Retailer only" -> retailer-level
        KPIs (NOT brand-level).  NOTE: source spec literally says "brand level"
        here for the retailer-only case, contradicting every other rule -
        treated as retailer-level for consistency; flagged in README §12.
      * Multi dim -> Excel-pivot behaviour: the FIRST-selected dimension is the
        outer/parent grouping (its subtotal rows are bold + tinted); each
        subsequent dimension nests underneath in selection order.  Column
        order in the table follows selection order (never fixed).  Grand-total
        rows are re-aggregated at that grouping's grain - never an average of
        nested child rows.
    """
    rows: list[dict] = []
    if not dims:
        cm = _metrics(cfy, active_days)
        lm = _metrics(lfy, active_days)
        rows.append({"dim_value": "(All)", "is_total": True, "_level": 0, "kpis": _kpi_cell(cm, lm, cm, lm)})
        return rows

    total_c = _metrics(cfy, active_days)
    total_l = _metrics(lfy, active_days)

    # Position-based subsetting: ONE groupby per (parent, dim) provides the row
    # positions, the aggregate metrics AND the display ordering together -
    # instead of a full boolean scan per value plus separate metric sweeps.
    # `indices` maps each formatted value to the positions of that value inside
    # the parent subset, so deeper-level drills still see exactly the rows the
    # old `_sub` boolean masks did.
    def _group_info(df, dim):
        """(positions, metrics, raw) per formatted dim value - ONE groupby."""
        if df is None or df.empty or dim not in df.columns:
            return {}, {}, {}
        g = df.groupby(dim, dropna=False, sort=False)
        agg = g.agg(bills=(dim, "size"), qty=("qty", "sum"), val=("bill_val", "sum"))
        metrics: dict = {}
        raw: dict = {}
        for k, bills, qty, val in agg.itertuples(name=None):
            fk = _fmt_dim(k)
            metrics[fk] = (float(bills), float(qty), float(val))
            raw[fk] = k
        positions = {_fmt_dim(k): v for k, v in g.indices.items()}
        return positions, metrics, raw

    def _metrics_of(bills, qty, val):
        return {
            "total_bills": bills,
            "qty": qty,
            "val": val,
            "active_days": int(active_days),
            "upt": safe_div(qty, bills),
            "abv": safe_div(val, bills),
            "asp": safe_div(val, qty),
            "spd_qty": safe_div(qty, active_days),
            "spd_val": safe_div(val, active_days),
        }

    def _walk(c_df, l_df, level, path):
        dim = dims[level]
        c_pos, c_met, c_raw = _group_info(c_df, dim)
        l_pos, l_met, l_raw = _group_info(l_df, dim) if not l_df.empty else ({}, {}, {})
        c_empty = c_df.iloc[0:0]
        l_empty = l_df.iloc[0:0]
        # Display order: CFY values by CFY bill value desc, then LFY-only
        # values by LFY bill value desc.  Month dims keep their fiscal-month
        # ordering via the shared helper (month_num is not carried here).
        if dim in ("month", "month_num") or not c_met:
            order = [(_fmt_dim(v), v) for v in _union_dim_values(c_df, l_df, dim)]
        else:
            c_keys = sorted(c_met.keys(), key=lambda k: c_met[k][2], reverse=True)
            seen = set(c_keys)
            l_keys = sorted(
                (k for k in l_met if k not in seen),
                key=lambda k: l_met[k][2],
                reverse=True,
            )
            order = [(k, c_raw.get(k, l_raw.get(k, k))) for k in c_keys + l_keys]
        for vk, v in order:
            pv = _dim_value(v)
            sub_c = c_df.iloc[c_pos[vk]] if vk in c_pos else c_empty
            sub_l = l_df.iloc[l_pos[vk]] if vk in l_pos else l_empty
            row: dict = {"_level": level + 1, "dim_value": _fmt_dim(v)}
            for i, d in enumerate(dims[: level + 1]):
                row[d] = path.get(d) if i < level else pv
            bills_c, qty_c, val_c = c_met.get(vk, (0.0, 0.0, 0.0))
            bills_l, qty_l, val_l = l_met.get(vk, (0.0, 0.0, 0.0))
            cm = _metrics_of(bills_c, qty_c, val_c)
            lm = _metrics_of(bills_l, qty_l, val_l)
            row["kpis"] = _kpi_cell(cm, lm, total_c, total_l)
            row["is_total"] = (level == 0)  # level-1 (outermost) rows = subtotals
            rows.append(row)
            if level + 1 < len(dims):
                _walk(sub_c, sub_l, level + 1, {**path, dim: pv})

    _walk(cfy, lfy, 0, {})

    # Grand-total row: genuine re-aggregation over the WHOLE selected context,
    # NOT an average of child rows.
    grand: dict = {"dim_value": "(All)", "is_total": True, "_level": 0, "kpis": _kpi_cell(total_c, total_l, total_c, total_l)}
    for d in dims:
        grand[d] = "(All)"
    rows.insert(0, grand)
    return rows


# ---------------------------------------------------------------------------
# Distributions (§7 Qty / §8 Bill Value) - buckets as column headers
# ---------------------------------------------------------------------------
def _distribution_rows(
    cfy: pd.DataFrame,
    lfy: pd.DataFrame,
    dim: str,
    bucket_col: str,
    bucket_order: list[str],
    active_days: int,
) -> list[dict]:
    """Bucket distribution pivoted so BUCKETS ARE COLUMN HEADERS (§7/8).

    The selected dimension drives the ROWS (Brand -> one row per brand, plus
    an '(All)' total row), exactly like the dimensional summary (§6).  When no
    dimension is selected a single '(All)' row is returned.

    Each bucket cell answers "HOW MANY bills landed in this bucket" — the
    simple user-confirmed contract (NO UPT / ABV / ASP / SPD, and NOT qty/val
    sums as the headline):

        CFY:    <bill count>
        CONT%:  <share of the row's CFY bill total>
        LFY:    <bill count>
        CONT%:  <share of the row's LFY bill total>
        PP Δ:   <pill = CFY Cont% − LFY Cont% in percentage points>

    The headline figure is always the NUMBER OF BILLS (NOT qty/val sums) for
    BOTH the qty-bucket and the value-bucket distributions - the bucket column
    only decides the CLASSIFICATION of the bill.  Cont% is the bucket's share
    of the ROW's own bill total (sum across all buckets) - a genuine
    re-aggregation at the row's grain, never an average of child rows.
    The delta is computed on those CONT% values as a plain percentage-point
    change (pp Δ = cont%_cfy − cont%_lfy, stored in `growth_pct` per user
    confirmation), NOT as a % change on the raw bill counts - so a bucket that
    lost share reads directly as e.g. "-4.5 pp", never as "-13.5%".  Aggregated
    bill qty / bill value are still carried on every cell for exports/drills.
    """
    is_all = dim in (None, "", "all")
    key = "_dim" if is_all else dim

    if not is_all and dim not in cfy.columns and dim not in lfy.columns:
        is_all = True

    # Coerce qty / bill_val to numeric once so the vectorised groupby sums stay
    # safe even if the source DB returns them as strings.
    if not cfy.empty:
        qty_obj = any(pd.api.types.is_object_dtype(cfy[c]) for c in ("qty", "bill_val") if c in cfy.columns)
        if qty_obj:
            cfy = cfy.copy()
            for c in ("qty", "bill_val"):
                if c in cfy.columns:
                    cfy[c] = pd.to_numeric(cfy[c], errors="coerce")
    if not lfy.empty:
        qty_obj = any(pd.api.types.is_object_dtype(lfy[c]) for c in ("qty", "bill_val") if c in lfy.columns)
        if qty_obj:
            lfy = lfy.copy()
            for c in ("qty", "bill_val"):
                if c in lfy.columns:
                    lfy[c] = pd.to_numeric(lfy[c], errors="coerce")

    def _group(df, gk):
        """{dim_value: {bucket: {bills, qty, val}}} - one vectorised pass/period."""
        if df is None or df.empty or bucket_col not in df.columns:
            return {}
        g = (
            df.groupby([gk, bucket_col], dropna=False, sort=False)
            .agg(bills=(bucket_col, "size"), qty=("qty", "sum"), val=("bill_val", "sum"))
            .reset_index()
        )
        out: dict = {}
        for k, b, bills, qty, val in g.itertuples(name=None, index=False):
            out.setdefault(_fmt_dim(k), {})[str(b)] = {
                "bills": float(bills),
                "qty": float(qty),
                "val": float(val),
            }
        return out

    def _grand(df):
        """{bucket: {bills, qty, val}} across the WHOLE df (for the (All) row)."""
        if df is None or df.empty or bucket_col not in df.columns:
            return {}
        g = (
            df.groupby(bucket_col, dropna=False, sort=False)
            .agg(bills=(bucket_col, "size"), qty=("qty", "sum"), val=("bill_val", "sum"))
            .reset_index()
        )
        return {
            str(b): {"bills": float(bills), "qty": float(qty), "val": float(val)}
            for b, bills, qty, val in g.itertuples(name=None, index=False)
        }

    gc = _group(cfy, key) if not is_all else {}
    gl = _group(lfy, key) if not is_all else {}
    zero = {"bills": 0.0, "qty": 0.0, "val": 0.0}

    def _totals(bmap):
        return {m: sum(v.get(m, 0.0) for v in bmap.values()) for m in ("bills", "qty", "val")}

    def _cell(c: dict, l: dict, c_tot: dict, l_tot: dict) -> dict:
        """One distribution bucket: Cont% shares + pp Δ = CFY Cont% − LFY Cont%.

        `growth_pct` carries the PERCENTAGE-POINT delta (share_cfy − share_lfy),
        not a % change of that Cont% - always numeric, zero-safe (buckets empty
        in both periods read ±0.0 pp, never a divide-by-zero None).
        """
        cfy_bills = float(c.get("bills", 0.0))
        lfy_bills = float(l.get("bills", 0.0))
        share_cfy = (cfy_bills / c_tot["bills"] * 100.0) if c_tot["bills"] else 0.0
        share_lfy = (lfy_bills / l_tot["bills"] * 100.0) if l_tot["bills"] else 0.0
        return {
            "metric": "bills",
            "cfy_bills": cfy_bills,
            "lfy_bills": lfy_bills,
            "cfy_qty": float(c.get("qty", 0.0)),
            "lfy_qty": float(l.get("qty", 0.0)),
            "cfy_val": float(c.get("val", 0.0)),
            "lfy_val": float(l.get("val", 0.0)),
            "share_cfy_pct": share_cfy,
            "share_lfy_pct": share_lfy,
            # pp delta (CFY Cont% - LFY Cont%), NOT a % change of the Cont%.
            "growth_pct": share_cfy - share_lfy,
        }
    dim_vals = ["(All)"] if is_all else ["(All)"] + _union_dim_values(cfy, lfy, key)
    rows: list[dict] = []
    for dv in dim_vals:
        if dv == "(All)" or is_all:
            c_map = _grand(cfy)
            l_map = _grand(lfy)
        else:
            c_map = gc.get(dv, {})
            l_map = gl.get(dv, {})
        c_tot = _totals(c_map)
        l_tot = _totals(l_map)
        cells: dict[str, dict] = {
            b: _cell(c_map.get(b, zero), l_map.get(b, zero), c_tot, l_tot)
            for b in bucket_order
        }
        # 'All Bills' column = the row's own total (share 100% in BOTH periods
        # -> pp Δ = 0) - re-aggregated, never averaged.
        cells["All Bills"] = _cell(c_tot, l_tot, c_tot, l_tot)
        rows.append({
            "dim_value": "(All)" if dv == "(All)" else _dim_value(dv),
            "is_total": dv == "(All)",
            "cfy_bills": c_tot["bills"],
            "lfy_bills": l_tot["bills"],
            "cfy_qty": c_tot["qty"],
            "lfy_qty": l_tot["qty"],
            "cfy_val": c_tot["val"],
            "lfy_val": l_tot["val"],
            "cells": cells,
        })
    return rows



# ---------------------------------------------------------------------------
# Per-bill brand contributions (Retailer-only Top Bills breakdown, §9)
# ---------------------------------------------------------------------------
def _build_contributions(fact: FactSpec) -> dict:
    """{internal_bill_id: [{brand, bill_val, contribution_pct}]} for EVERY
    valid bill of the fact table.

    Contribution % = brand's bill_val within THIS bill / bill's total bill_val
    * 100, computed from the RAW transaction rows grouped by (bill_key, brand)
    so multi-brand bills reconcile to ~100% (uses the ACTUAL per-brand value,
    NOT the dominant-line brand used for the store-master dimensions).
    """
    ds = _load_dataset(fact)
    bill_ids = set()
    if not ds.empty and "internal_bill_id" in ds.columns:
        bill_ids = {str(b) for b in ds["internal_bill_id"].dropna().unique()}
    if not bill_ids:
        return {}

    brand_q = fact.brand_column
    date_q = fact.date_column
    sq = quote_ident
    # Display brand NAME for the mix: a bill can legitimately contain several
    # brands and the business reads brand NAMES, not store-master codes.  Falls
    # back to a NULL column when the fact carries no brand-name column (the code
    # is then used as the label).
    brand_name_expr = (
        sq("brand")
        if column_exists(fact.schema, fact.table, "brand")
        else "CAST(NULL AS VARCHAR)"
    )
    # FY label computed inline (the shared `_FY_LABEL_SQL` in bill_analysis
    # references a `tx_date` alias that only exists inside its own CTE, so we
    # use the real column name here instead of importing it).
    fy_label_sql = (
        f"CASE WHEN EXTRACT(MONTH FROM {date_q}) >= 4 "
        f"THEN 'FY' || EXTRACT(YEAR FROM {date_q})::VARCHAR || '-' || "
        f"RIGHT((EXTRACT(YEAR FROM {date_q}) + 1)::VARCHAR, 2) "
        f"ELSE 'FY' || (EXTRACT(YEAR FROM {date_q}) - 1)::VARCHAR || '-' || "
        f"RIGHT(EXTRACT(YEAR FROM {date_q})::VARCHAR, 2) END"
    )
    sql = f"""
    WITH j AS (
        SELECT
            {fy_label_sql} AS fy_label,
            'FY' || RIGHT(CASE WHEN EXTRACT(MONTH FROM {date_q}) >= 4
                                THEN EXTRACT(YEAR FROM {date_q})
                                ELSE EXTRACT(YEAR FROM {date_q}) - 1 END::VARCHAR, 2) AS fy_short,
            EXTRACT(MONTH FROM {date_q})::INTEGER AS month_num,
            TRIM(CAST(bill_no AS VARCHAR)) AS bill_no,
            {sq(fact.store_column)} AS store_code,
            {sq(brand_q)} AS brand_code,
            {brand_name_expr} AS brand_name,
            SUM({fact.qty_expr}) AS qty,
            SUM({fact.val_expr}) AS bill_val
        FROM {fact.schema}.{fact.table}
        WHERE bill_no IS NOT NULL
          AND TRIM(CAST(bill_no AS VARCHAR)) <> ''
          AND UPPER(TRIM(CAST(bill_no AS VARCHAR))) NOT IN ('NA','N/A')
        GROUP BY ALL
    )
    SELECT fy_label, fy_short, month_num, bill_no, store_code, brand_code,
           brand_name, qty, bill_val
    FROM j
    """
    fine = execute_df(sql)
    if fine.empty:
        return {}
    # Rebuild internal_bill_id so we can join to the cached bill dataset.
    fine["internal_bill_id"] = (
        fine["store_code"].astype(str) + "-" + fine["fy_short"].astype(str)
        + "-" + fine["month_num"].astype(int).map(lambda m: f"{m:02d}")
        + "-" + fine["bill_no"].astype(str)
    )
    # Keep only the bills that survived the dimension filter (so contributions
    # reflect the active slicers).
    fine = fine[fine["internal_bill_id"].isin(bill_ids)]
    if fine.empty:
        return {}
    # Label every part with the brand NAME (what the business reads); a code that
    # has no name falls back to the code itself.
    names = fine["brand_name"].astype("string").fillna("").str.strip()
    fine["brand"] = names.where(names.ne(""), fine["brand_code"].astype("string"))
    out: dict = {}
    for bid, sub in fine.groupby("internal_bill_id", sort=False):
        out[str(bid)] = _contribution_parts(sub)
    return out


def _contribution_parts(sub: pd.DataFrame) -> list[dict]:
    """Per-brand contribution parts for ONE bill's brand-grouped rows.

    Contribution % = brand's bill_val within THIS bill / bill's total bill_val
    * 100 (sums to 100% for a complete bill).  Grouping is on the display brand
    NAME when the frame carries one (`brand`), otherwise on `brand_code`.
    Pure — unit-testable without a DB.
    """
    total = float(sub["bill_val"].sum())
    parts = []
    label_col = "brand" if "brand" in sub.columns else "brand_code"
    for brand, bsub in sub.groupby(label_col, dropna=False, sort=False):
        bv = float(bsub["bill_val"].sum())
        parts.append({
            "brand": None if (brand is None or pd.isna(brand)) else str(brand),
            "bill_val": bv,
            "contribution_pct": (bv / total * 100.0) if total else 0.0,
        })
    parts.sort(key=lambda p: p["bill_val"], reverse=True)
    return parts


# Per-process memo: the map covers EVERY valid bill of the fact table (the SQL
# is filter-independent - contributions always describe the true brand mix of
# the physical bill), so it is built ONCE and reused across all filter /
# dimension / date-range combinations.  Re-keying it per filter combination
# used to re-run the same full-table aggregation for every slicer toggle,
# which is what made the module feel slow.
_CONTRIB_FACT: FactSpec | None = None
_CONTRIB_MAP: dict = {}


def _contrib_cache(fact: FactSpec, filters: dict | None = None) -> dict:
    """Return the per-bill brand-contribution map, building it once.

    `filters` is accepted (and ignored) so call-sites can pass the active
    slicer context without changing the cache behaviour: the map is a
    per-fact singleton, and per-bill lookups keep every answer correct no
    matter which filters are applied.
    """
    global _CONTRIB_FACT, _CONTRIB_MAP
    if _CONTRIB_FACT is fact and _CONTRIB_MAP:
        return _CONTRIB_MAP
    _CONTRIB_FACT, _CONTRIB_MAP = fact, _build_contributions(fact)
    return _CONTRIB_MAP


def _brand_contribution(bill_id: str) -> list[dict]:
    return (_CONTRIB_MAP or {}).get(bill_id, [])


# ---------------------------------------------------------------------------
# Top Bills (req §9): ranked by bill_val desc, 1-based server-side rank.
# Deterministic tie-break: equal bill values -> earliest bill_date, then
# internal_bill_id.  The list is always in strict rank 1..n order.
# ---------------------------------------------------------------------------
def _top_bill_rows(df: pd.DataFrame, n: int, with_contrib: bool = False) -> list[dict]:
    if df is None or df.empty or n <= 0:
        return []
    top = df.dropna(subset=["bill_val"]).sort_values(
        ["bill_val", "bill_date", "internal_bill_id"],
        ascending=[False, True, True],
        kind="stable",
    ).head(n)
    out = []
    for rank, (_, r) in enumerate(top.iterrows(), start=1):
        rec = {
            "rank": rank,
            "internal_bill_id": str(r.get("internal_bill_id", "")),
            "bill_date": _ba._iso_date(r.get("bill_date")),
            "month": None if pd.isna(r.get("month")) else r.get("month"),
            "adonis_store_code": _na_or(r.get("adonis_store_code")),
            "brand": _na_or(r.get("brand")),
            "retailer_name": _na_or(r.get("retailer_name")),
            "qty": float(r["qty"]),
            "bill_val": float(r["bill_val"]),
        }
        if with_contrib:
            rec["brand_contributions"] = _brand_contribution(rec["internal_bill_id"])
        out.append(rec)
    return out


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def run_bill_kpi_analysis(
    fact: FactSpec,
    filters: dict[str, list[str]] | None,
    dimension: list[str] | str | None = None,
    date_range: dict | None = None,
    top_n: int = 25,
    dist_dim: str | None = None,
) -> dict:
    """Run the Bill_No Based KPI Analysis (req §1-9).

    Args:
        fact:       FactSpec for the tertiary fact table.
        filters:    {column: [values]} global slicers (Retailer/Brand/State/
                    Department/etc + Internal Month).
        dimension:  dimension(s) for the pivot summary table (order matters -
                    first = outer grouping).  Single string accepted.
        date_range: {"start": iso, "end": iso} OR None -> FY mode (req §5).
        top_n:      any positive user-selected count of ranked bills.
        dist_dim:   dimension for the qty/value distribution tables
                    (defaults to "all").

    Memoised on (fact, filters, dimension order, date range, Top-N, dist
    dimension, data token): every one of those is a UI control, so flipping
    between two view states - or re-mounting the tab - now costs a dict lookup
    instead of a full re-aggregation of the cached bill dataset.  The key is
    built from the SAME normalisation the body applies (dimension list,
    `snap_top_n`, raw dist dimension / date range), so two requests collide in
    the cache exactly when they produce the same payload.
    """
    if isinstance(dimension, str):
        dimension = [dimension]
    dims_key = tuple(d for d in (dimension or []) if d)
    date_range_key = (
        tuple(sorted((str(k), str(v)) for k, v in date_range.items())) if date_range else None
    )
    return _bill_kpi_cached(
        fact,
        filter_key(filters),
        dims_key,
        date_range_key,
        snap_top_n(top_n),
        str(dist_dim) if dist_dim else None,
        cache_token(),
    )


@lru_cache(maxsize=32)
def _bill_kpi_cached(
    fact: FactSpec,
    filters_key: tuple,
    dims_key: tuple,
    date_range_key: tuple | None,
    top_n_key: int,
    dist_dim_key: str | None,
    _token: tuple,
) -> dict:
    """Body of `run_bill_kpi_analysis` (the `_token` argument is the cache key)."""
    filters = {col: list(values) for col, values in filters_key}
    dimension = list(dims_key)
    date_range = {k: v for k, v in date_range_key} if date_range_key else None
    top_n = top_n_key
    dist_dim = dist_dim_key
    _validate_filters(fact, filters)
    if isinstance(dimension, str):
        dimension = [dimension]
    dimension = [d for d in (dimension or []) if d]
    available = {d["column"] for d in bill_dimensions()} | {"month_num"}
    for d in dimension:
        if d not in available:
            raise ValueError(f"Unknown dimension: {d}")

    # Top-N is a free user input; only non-positive values are normalised.
    top_n = snap_top_n(top_n)

    ds = _ba._filtered_bills(fact, filters or {})
    if ds.empty or "bill_date" not in ds.columns:
        return _empty_result(top_n, dimension)

    max_date = pd.to_datetime(ds["bill_date"].max())
    if max_date.tz is not None:
        max_date = max_date.tz_localize(None)

    cfy, lfy, window_meta = _period_windows(ds, date_range)

    # ---- Global (context-level) Active_Days for the SPD KPIs ---------------
    # Brand-anchored (req §3): if a single brand is in scope, use that brand's
    # global first sale date; otherwise the dataset-wide first sale date.
    scope_brand = None
    if "brand" in ds.columns and ds["brand"].nunique() == 1:
        b = ds["brand"].dropna().unique()
        scope_brand = b[0] if len(b) else None
    active_days = _active_days(ds, scope_brand, max_date)

    cfy_m = _metrics(cfy, active_days)
    lfy_m = _metrics(lfy, active_days)
    kpis = _kpi_cell(cfy_m, lfy_m, cfy_m, lfy_m)

    summary_rows = _dimension_summary_rows(cfy, lfy, dimension, active_days)

    # Distributions follow the user's dimension selection (§6): when a single
    # (or multiple) dimension is selected, the rows roll up at that dimension.
    # Brand selected -> one row per brand + the '(All)' total row.  Cells show
    # HOW MANY bills landed in each bucket (CFY / CONT% / LFY / CONT% / PP Δ,
    # the delta = CFY Cont% - LFY Cont%) - no UPT / ABV / ASP, and NOT qty/val
    # sums (user-confirmed contract).
    if not dist_dim or str(dist_dim).strip().lower() in ("", "all"):
        dist_dim = dimension[0] if dimension else "all"

    qty_distribution = _distribution_rows(
        cfy, lfy, dist_dim, "qty_bucket", QUANTITY_BUCKETS, active_days
    )
    val_distribution = _distribution_rows(
        cfy, lfy, dist_dim, "value_bucket", VALUE_BUCKETS, active_days
    )

    # Top Bills stays a lightweight ranked list; KPI contribution figures are
    # returned with the KPI and hierarchy payloads instead.  The per-bill brand
    # mix (Brand - value [cont% of THAT bill]) is only populated when the
    # contribution cache is actually built - warm it here so `_brand_contribution`
    # has data to serve (it is keyed per FactSpec + filter context and reused
    # across the CFY and LFY lists).
    _contrib_cache(fact, filters or {})
    top_bills = {
        "n": top_n,
        "cfy": _top_bill_rows(cfy, top_n, with_contrib=True),
        "lfy": _top_bill_rows(lfy, top_n, with_contrib=True),
    }

    return {
        "dimension": dimension,
        "dimension_labels": {d["column"]: d["label"] for d in bill_dimensions()},
        "date_range": date_range or None,
        "window_meta": window_meta,
        "kpis": kpis,
        "summary": {"dimensions": dimension, "rows": summary_rows},
        "qty_distribution": {"dim": dist_dim or "all", "metric": "bills", "buckets": QUANTITY_BUCKETS, "rows": qty_distribution},
        "value_distribution": {"dim": dist_dim or "all", "metric": "bills", "buckets": VALUE_BUCKETS, "rows": val_distribution},
        "top_bills": top_bills,
        "meta": {
            "transaction_rows": int(_ba._load_bill_dataset(fact)["row_count"].sum()),
            "bill_count": len(cfy),
            "active_days": active_days,
            "cfy_period": _period_bounds(cfy),
            "lfy_period": _period_bounds(lfy),
            "active_days_rule": (
                "brand-anchored: MAX(dataset bill_date) - MIN(brand global first sale "
                "date across all retailers) + 1. Retailer SPD for Brand X uses Brand X's "
                "overall first sale date, NOT the retailer's own first sale date. May "
                "make a retailer's SPD look diluted - intentional per business rule, "
                "NOT a bug."
            ),
            "note_retailer_kpi_grain": (
                "Single-dimension 'Retailer only' renders retailer-level KPIs for "
                "consistency with every other single-dimension case. The source spec "
                "literally says 'brand level' here - flagged to the business owner; "
                "treat as retailer-level until confirmed otherwise (see README §12)."
            ),
        },
    }


def _empty_result(top_n: int, dimension: list) -> dict:
    cm = _metrics(pd.DataFrame(), 0)
    return {
        "dimension": dimension,
        "dimension_labels": {d["column"]: d["label"] for d in bill_dimensions()},
        "date_range": None,
        "window_meta": {"mode": "date-range"},
        "kpis": _kpi_cell(cm, cm),
        "summary": {"dimensions": dimension, "rows": []},
        "qty_distribution": {"dim": "all", "metric": "bills", "buckets": QUANTITY_BUCKETS, "rows": []},
        "value_distribution": {"dim": "all", "metric": "bills", "buckets": VALUE_BUCKETS, "rows": []},
        "top_bills": {"n": top_n, "cfy": [], "lfy": []},
        "meta": {
            "transaction_rows": 0, "bill_count": 0, "active_days": 0,
            "active_days_rule": "empty dataset - no active days.",
        },
    }