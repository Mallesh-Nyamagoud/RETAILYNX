"""
Category Performance Analysis (Tertiary Sales Analysis, Module IV, tab 4).

Row-relative (contribution) pivot over the tertiary fact table:

    Level 1:  Row-hierarchy LEVEL 1 dimension value  x  Category
    Level 2:  Row-hierarchy LEVEL 1 -> LEVEL 2      x  Category x Sub-Category

Measures per cell - THREE periods (LFY, LFYTD, CFYTD) for every KPI the UI
renders, so the UI never has to compare a year-to-date figure with a full-year
one:

    QTY       : LFY, LFYTD, CFYTD  (+ growth% CFYTD vs LFYTD)
    CONT.%    : LFY, LFYTD, CFYTD  (+ CHANGE IN CONT.% = CFYTD pp - LFYTD pp)
    ASP       : LFY, LFYTD, CFYTD  (+ growth% CFYTD vs LFYTD)
    AVG.MRP   : LFY, LFYTD, CFYTD  (+ growth% CFYTD vs LFYTD)

The LFYTD (last fiscal year-to-date) slice is the LIKE-FOR-LIKE comparison
window, so every `*_growth_lfytd_pct` / `change_in_cont` delta is CFYTD vs
LFYTD.  The historical CFY-vs-full-LFY pairs (`asp_growth_pct`,
`avg_mrp_growth_pct`) are still returned unchanged for compatibility.

Rows and slicers come from the PAGE-LEVEL controls only (this section has no
filters of its own):

    * Row Hierarchy  -> the `hierarchy` request field (level 1, level 2, ...)
    * Global slicers -> the `filters` request field.  Exactly like the pivot
      engine, every slicer keys off a `store_master.store_details` column
      (Retailer / Brand / Store Type / Department / Group / State / Store
      Status), so `dim.<col> IN (...)` semantics are preserved.  A fact-column
      slicer (`season`) is also honoured when supplied.

`CONT.%` is always the row-relative share (L1: against that row's own category
total, L2: against its PARENT category total), floored at 0 in the divide-by-
zero case - matching the section's stated contract.

Performance (the whole point of this module's rewrite)
-----------------------------------------------------
Nothing is re-queried per request:

    * the fact table is pulled ONCE (`lru_cache`) as the finest useful grain
      (store + brand + category + sub-category + season + date + 3 measures);
    * the store-master dimension columns are merged ONCE (single hash join);
    * filtering is ONE boolean-mask pass over that cached frame;
    * the aggregation is TWO vectorised groupbys (L1 keys, L2 keys) - the old
      implementation sliced a DataFrame once per brand x category (233 x 48
      passes) which is what made interactions slow;
    * the finished payload is memoised on (row dims, filters), so re-toggling
      a slicer or re-ordering the row hierarchy is instant.

Categories / sub-categories / the category order and the store-master column
catalogue are discovered dynamically - nothing about the data is hard-coded, so
new categories appear without a code change.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import pandas as pd

from app.core.database import (
    cache_token,
    column_exists,
    execute,
    execute_df,
    quote_ident,
)
from app.services.analysis import get_dimension_catalog
from app.services.fy import FYContext, build_fy_context, safe_div, safe_growth, safe_pct

# ---------------------------------------------------------------------------
# Fact table contract
# ---------------------------------------------------------------------------
FACT_SCHEMA = "tertiary_data"
FACT_TABLE = "data"
DATE_COL = "date"
BRAND_CODE_COL = "brand_code"
STORE_COL = "adonis_store_code"
QTY_COL = "qty"
VAL_COL = "bill_val"
MRP_COL = "mrp_value"
CATEGORY_COL = "category"
SUBCATEGORY_COL = "sub_category"
SEASON_COL = "season"

# Category display order (case-insensitive); anything not listed follows,
# alphabetically.  Any category containing "PROMO" is excluded outright.
CATEGORY_FIXED_ORDER = [
    "SHIRTS", "T-SHIRTS", "DENIM", "TROUSERS", "WINTER WEAR",
    "WOMENS WEAR", "FORMAL WEAR", "SHORTS",
]

# Level 1 / Level 2 row dimensions.  `DEFAULT_ROW_DIM` keeps the section's
# historical "Brand x Category" default for the (very common) case where the
# Row Hierarchy is still empty; it is a single constant, so switching the
# default is a one-line change.
DEFAULT_ROW_DIM = "brand"
MAX_ROW_DIMS = 2

# Store-master columns that are NOT user-facing dimensions (join keys / the
# auto-computed date columns) - mirrors analysis._EXCLUDED_DIMENSION_COLUMNS.
_EXCLUDED_DIM_COLUMNS = {"adonis_store_code", "brand_code", "ter_min_date", "ter_max_date"}

_MEASURE_COLS = ("qty_val", "val_val", "mrp_val")
_ZERO: tuple[float, float, float] = (0.0, 0.0, 0.0)


# ---------------------------------------------------------------------------
# Dynamic discovery (cached: one SQL round-trip per process, not per request)
# ---------------------------------------------------------------------------
def _filter_and_order_categories(raw: list) -> list:
    """Exclude PROMO categories, then present the rest in a fixed, friendly
    order (anything unlisted follows alphabetically)."""
    kept = [c for c in raw if "PROMO" not in str(c).upper()]
    order_map = {name.upper(): idx for idx, name in enumerate(CATEGORY_FIXED_ORDER)}
    return sorted(kept, key=lambda c: (order_map.get(str(c).upper(), 999), str(c)))


@lru_cache(maxsize=1)
def get_category_meta() -> dict:
    """The full category -> sub-category hierarchy, discovered live.

    One catalog query + one distinct-pair query (the previous implementation ran
    a separate DISTINCT query per category on every single request).
    """
    if not column_exists(FACT_SCHEMA, FACT_TABLE, CATEGORY_COL):
        return {"categories": [], "sub_categories": {}}

    raw = [
        r[0]
        for r in execute(
            f"SELECT DISTINCT {quote_ident(CATEGORY_COL)} FROM {FACT_SCHEMA}.{FACT_TABLE} "
            f"WHERE {quote_ident(CATEGORY_COL)} IS NOT NULL ORDER BY 1"
        )
    ]
    categories = _filter_and_order_categories(raw)
    wanted = {str(c) for c in categories}

    sub_map: dict[str, list] = {str(c): [] for c in categories}
    if column_exists(FACT_SCHEMA, FACT_TABLE, SUBCATEGORY_COL):
        rows = execute(
            f"SELECT DISTINCT {quote_ident(CATEGORY_COL)}, {quote_ident(SUBCATEGORY_COL)} "
            f"FROM {FACT_SCHEMA}.{FACT_TABLE} "
            f"WHERE {quote_ident(CATEGORY_COL)} IS NOT NULL "
            f"AND {quote_ident(SUBCATEGORY_COL)} IS NOT NULL "
            f"ORDER BY 2"
        )
        for cat, sub in rows:
            if str(cat) in wanted:
                sub_map.setdefault(str(cat), []).append(sub)

    return {"categories": categories, "sub_categories": sub_map}


@lru_cache(maxsize=1)
def _dimension_columns() -> tuple[str, ...]:
    """Every store-master column usable as a row level / slicer (dynamic)."""
    return tuple(
        d["column"] for d in get_dimension_catalog()
        if d["column"] not in _EXCLUDED_DIM_COLUMNS
    )


@lru_cache(maxsize=1)
def _available_dim_columns() -> frozenset[str]:
    return frozenset(_dimension_columns())


@lru_cache(maxsize=1)
def _load_fact_rows() -> pd.DataFrame:
    """The WHOLE tertiary fact at (store + brand + category + sub-category +
    season) grain - pulled once and reused by every request."""
    def col(name: str) -> str:
        # Keep a missing optional column as the SQL NULL expression; f.NULL is invalid.
        return f"f.{quote_ident(name)}" if column_exists(FACT_SCHEMA, FACT_TABLE, name) else "NULL"

    sql = f"""
        SELECT
            {col(STORE_COL)}        AS store_code,
            {col(BRAND_CODE_COL)}   AS brand_code,
            {col(CATEGORY_COL)}     AS category,
            {col(SUBCATEGORY_COL)}  AS sub_category,
            {col(SEASON_COL)}       AS season,
            {col(DATE_COL)}         AS tx_date,
            {col(QTY_COL)}          AS qty_val,
            {col(VAL_COL)}          AS val_val,
            {col(MRP_COL)}          AS mrp_val
        FROM {FACT_SCHEMA}.{FACT_TABLE} f
    """
    df = execute_df(sql)
    if df.empty:
        return df
    df["tx_date"] = pd.to_datetime(df["tx_date"], errors="coerce")
    for name in _MEASURE_COLS:
        df[name] = pd.to_numeric(df[name], errors="coerce").fillna(0.0)
    return df


def _cache_token() -> tuple:
    """Store-master freshness token for the cached dimension snapshot.

    Delegates to the shared `cache_token()` so the Category tab sees the SAME
    freshness signal as every other memoised read path: the enrichment job's
    result, plus a revision counter bumped by Store-Master edits, a manual
    status recompute and a factory reset.  (Previously only the enrichment
    job's own result was tracked, so a manual recompute or an admin edit could
    leave this cache serving the previous snapshot.)
    """
    return cache_token()


@lru_cache(maxsize=4)
def _load_store_dims(_token: tuple) -> pd.DataFrame:
    """Store-master dimension snapshot (keyed on the freshness token above)."""
    cols = [
        c for c in _dimension_columns()
        if column_exists("store_master", "store_details", c)
    ]
    keys = "adonis_store_code, brand_code"
    select = ", ".join(quote_ident(c) for c in cols)
    df = execute_df(
        f"SELECT {keys}{', ' + select if select else ''} FROM store_master.store_details"
    )
    return df.rename(columns={"adonis_store_code": "store_code"})


@lru_cache(maxsize=4)
def _load_facts(token: tuple) -> pd.DataFrame:
    """Fact rows + store-master dimension attributes, merged ONCE.

    The join is on (store, brand) - the same keys every other module joins on -
    so a slicer never fans a sale out across sibling stores.
    """
    df = _load_fact_rows()
    if df.empty:
        return df
    dim = _load_store_dims(token)
    if dim.empty:
        return df
    extra = [c for c in dim.columns if c not in ("store_code", "brand_code") and c not in df.columns]
    if not extra:
        return df
    return df.merge(
        dim[["store_code", "brand_code"] + extra],
        on=["store_code", "brand_code"],
        how="left",
    )


# ---------------------------------------------------------------------------
# Request-time helpers (pure pandas - no SQL, no re-aggregation of raw rows)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _fy_context() -> FYContext | None:
    """The shared FY window, anchored on the global MAX tertiary date."""
    row = execute(f"SELECT MAX({quote_ident(DATE_COL)}) FROM {FACT_SCHEMA}.{FACT_TABLE}")
    value = row[0][0] if row else None
    if value is None:
        return None
    return build_fy_context(value.date() if hasattr(value, "date") else value)


def _resolve_row_dims(hierarchy: list[str] | None) -> tuple[str, ...]:
    """Row Hierarchy -> (level 1, level 2).

    Unknown / not-yet-loaded columns are dropped; an empty Row Hierarchy keeps
    the section's historical Brand default (`DEFAULT_ROW_DIM`).
    """
    available = _available_dim_columns()
    picked = [str(d) for d in (hierarchy or []) if str(d) in available]
    if not picked and DEFAULT_ROW_DIM in available:
        picked = [DEFAULT_ROW_DIM]
    return tuple(picked[:MAX_ROW_DIMS])


def _apply_filters(df: pd.DataFrame, filters: dict[str, list[str]] | None) -> pd.DataFrame:
    """Global slicers as ONE boolean mask (no intermediate frame copies).

    Filter columns are store-master columns merged onto the fact rows, so
    `col IN (...)` behaves exactly like the pivot engine's `dim.col IN (...)`.
    A slicer whose column the dataset does not carry can never match anything
    and is ignored instead of failing the whole section.
    """
    if df.empty or not filters:
        return df
    mask = None
    for col, values in filters.items():
        if not values or col not in df.columns:
            continue
        col_mask = df[col].isin(values)
        mask = col_mask if mask is None else (mask & col_mask)
    if mask is None:
        return df
    return df[mask]


def _norm(value: Any) -> Any:
    """NaN/NaT/None collapse to a single `None` key (so dict lookups work)."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):  # array-likes: leave untouched
        return value
    return value


def _key(key: Any) -> tuple:
    """groupby index -> normalised key tuple (scalar for single-key groups)."""
    if isinstance(key, tuple):
        return tuple(_norm(k) for k in key)
    return (_norm(key),)


def _fmt_dim(value: Any) -> str:
    return "(blank)" if _norm(value) is None else str(value)


def _sum_index(df: pd.DataFrame, keys: list[str]) -> dict[tuple, tuple[float, float, float]]:
    """ONE vectorised groupby -> {(key...): (qty, value, mrp)}.

    Zip-ing the index with the three measure columns is markedly faster than
    `iterrows()` and never materialises one DataFrame per group.
    """
    if df.empty or not keys:
        return {}
    grouped = df.groupby(keys, dropna=False, sort=False, observed=True)[list(_MEASURE_COLS)].sum()
    out: dict[tuple, tuple[float, float, float]] = {}
    qty, val, mrp = (grouped[c].to_numpy() for c in _MEASURE_COLS)
    for raw_key, q, v, m in zip(grouped.index.tolist(), qty, val, mrp):
        out[_key(raw_key)] = (float(q), float(v), float(m))
    return out


def _rollup(
    src: dict[tuple, tuple[float, float, float]], positions: tuple[int, ...]
) -> dict[tuple, tuple[float, float, float]]:
    """Sum measure tuples grouped by (a subset of) their key positions."""
    acc: dict[tuple, list[float]] = {}
    for key, values in src.items():
        out_key = tuple(key[i] for i in positions)
        bucket = acc.get(out_key)
        if bucket is None:
            acc[out_key] = [values[0], values[1], values[2]]
        else:
            bucket[0] += values[0]
            bucket[1] += values[1]
            bucket[2] += values[2]
    return {k: (v[0], v[1], v[2]) for k, v in acc.items()}


def _union_values(roll_cfy: dict, roll_lfy: dict) -> list:
    """Dimension values ordered by CFY qty (desc), then LFY-only values by LFY
    qty - so rows that only traded last year still get their own row."""
    values = [k[0] for k in sorted(roll_cfy, key=lambda k: -roll_cfy[k][0])]
    seen = {str(v) for v in values}
    values.extend(
        k[0] for k in sorted(roll_lfy, key=lambda k: -roll_lfy[k][0]) if str(k[0]) not in seen
    )
    return values


def _cell(
    cfy: tuple[float, float, float],
    lfy: tuple[float, float, float],
    lytd: tuple[float, float, float],
    total_cfy: float,
    total_lfy: float,
    total_lytd: float,
    overall_cfy: float = 0.0,
    overall_lfy: float = 0.0,
    overall_lytd: float = 0.0,
) -> dict[str, Any]:
    """Every KPI one UI cell shows, for one row x category x sub-category slice.

    `total_cfy` / `total_lfy` is the CONT.% denominator: the row's own category
    total at Level 1, the PARENT category total at Level 2.
    """
    qty_c, val_c, mrp_c = cfy
    qty_l, val_l, mrp_l = lfy
    qty_lytd, val_lytd, mrp_lytd = lytd
    asp_c = safe_div(val_c, qty_c)
    asp_l = safe_div(val_l, qty_l)
    asp_lytd = safe_div(val_lytd, qty_lytd)
    avg_mrp_c = safe_div(mrp_c, qty_c)
    avg_mrp_l = safe_div(mrp_l, qty_l)
    avg_mrp_lytd = safe_div(mrp_lytd, qty_lytd)
    cont_c = safe_pct(qty_c, total_cfy)
    cont_l = safe_pct(qty_l, total_lfy)
    cont_lytd = safe_pct(qty_lytd, total_lytd)
    cont_across_c = safe_pct(qty_c, overall_cfy) if overall_cfy else 0.0
    cont_across_l = safe_pct(qty_l, overall_lfy) if overall_lfy else 0.0
    cont_across_lytd = safe_pct(qty_lytd, overall_lytd) if overall_lytd else 0.0
    return {
        "sale_cfy": qty_c,
        "sale_lfy": qty_l,
        "sale_lfytd": qty_lytd,
        "qty_cfy": qty_c,
        "qty_lfy": qty_l,
        "qty_lfytd": qty_lytd,
        "asp_cfy": asp_c,
        "asp_lfy": asp_l,
        "asp_lfytd": asp_lytd,
        # LIKE-FOR-LIKE growth: CFYTD vs LFYTD (the same elapsed window). Growth
        # divides by |base| so a negative prior period can never flip the sign.
        "qty_growth_lfytd_pct": safe_growth(qty_c, qty_lytd),
        "asp_growth_lfytd_pct": safe_growth(asp_c, asp_lytd),
        "avg_mrp_growth_lfytd_pct": safe_growth(avg_mrp_c, avg_mrp_lytd),
        # Historical CFY-vs-full-LFY growth (unchanged contract).
        "asp_growth_pct": safe_growth(asp_c, asp_l),
        "avg_mrp_cfy": avg_mrp_c,
        "avg_mrp_lfy": avg_mrp_l,
        "avg_mrp_lfytd": avg_mrp_lytd,
        "avg_mrp_growth_pct": safe_growth(avg_mrp_c, avg_mrp_l),
        "cont_pct_cfy": cont_c,
        "cont_pct_lfy": cont_l,
        "cont_pct_lfytd": cont_lytd,
        "change_in_cont": cont_c - cont_lytd,
        "cont_across_pct_cfy": cont_across_c,
        "cont_across_pct_lfy": cont_across_l,
        "cont_across_pct_lfytd": cont_across_lytd,
        "change_in_cont_across": cont_across_c - cont_across_lytd,
    }



def _level1_data(
    prefix: tuple,
    idx_cfy: dict[tuple, tuple[float, float, float]],
    idx_lfy: dict[tuple, tuple[float, float, float]],
    idx_lytd: dict[tuple, tuple[float, float, float]],
    categories: list,
    grand1_c: dict[tuple, tuple[float, float, float]] | None = None,
    grand1_l: dict[tuple, tuple[float, float, float]] | None = None,
    grand1_lytd: dict[tuple, tuple[float, float, float]] | None = None,
) -> dict[str, dict]:
    """{category: measures} for one Level-1 row, share vs its OWN row total."""
    cells: dict[str, tuple] = {}
    cat_map = {}
    total_c = 0.0
    total_l = 0.0
    total_lytd = 0.0
    for cat in categories:
        key = prefix + (cat,)
        c = idx_cfy.get(key, _ZERO)
        l = idx_lfy.get(key, _ZERO)
        lytd = idx_lytd.get(key, _ZERO)
        name = str(cat)
        cells[name] = (c, l, lytd)
        cat_map[name] = cat
        total_c += c[0]
        total_l += l[0]
        total_lytd += lytd[0]
        
    out = {}
    for name, (c, l, lytd) in cells.items():
        if grand1_c is not None and grand1_l is not None and grand1_lytd is not None:
            # overall across all row dimension values for THIS category
            orig_cat = cat_map[name]
            overall_c = grand1_c.get((orig_cat,), _ZERO)[0]
            overall_l = grand1_l.get((orig_cat,), _ZERO)[0]
            overall_lytd = grand1_lytd.get((orig_cat,), _ZERO)[0]
        else:
            overall_c = overall_l = overall_lytd = 0.0
        out[name] = _cell(c, l, lytd, total_c, total_l, total_lytd, overall_c, overall_l, overall_lytd)
    return out


def _level2_data(
    prefix: tuple,
    idx_cfy: dict[tuple, tuple[float, float, float]],
    idx_lfy: dict[tuple, tuple[float, float, float]],
    idx_lytd: dict[tuple, tuple[float, float, float]],
    categories: list,
    sub_categories: dict[str, list],
    grand2_c: dict[tuple, tuple[float, float, float]] | None = None,
    grand2_l: dict[tuple, tuple[float, float, float]] | None = None,
    grand2_lytd: dict[tuple, tuple[float, float, float]] | None = None,
) -> dict[str, dict[str, dict]]:
    """{category: {sub-category: measures}} for one Level-2 row, share vs the
    PARENT category total (exactly as the section documents it)."""
    out: dict[str, dict[str, dict]] = {}
    for cat in categories:
        subs = sub_categories.get(str(cat), [])
        if not subs:
            out[str(cat)] = {}
            continue
        cells: dict[str, tuple] = {}
        sub_map = {}
        cat_total_c = 0.0
        cat_total_l = 0.0
        cat_total_lytd = 0.0
        for sub in subs:
            key = prefix + (cat, sub)
            c = idx_cfy.get(key, _ZERO)
            l = idx_lfy.get(key, _ZERO)
            lytd = idx_lytd.get(key, _ZERO)
            name = str(sub)
            cells[name] = (c, l, lytd)
            sub_map[name] = sub
            cat_total_c += c[0]
            cat_total_l += l[0]
            cat_total_lytd += lytd[0]
            
        cat_out = {}
        for name, (c, l, lytd) in cells.items():
            if grand2_c is not None and grand2_l is not None and grand2_lytd is not None:
                orig_sub = sub_map[name]
                overall_c = grand2_c.get((cat, orig_sub), _ZERO)[0]
                overall_l = grand2_l.get((cat, orig_sub), _ZERO)[0]
                overall_lytd = grand2_lytd.get((cat, orig_sub), _ZERO)[0]
            else:
                overall_c = overall_l = overall_lytd = 0.0
            cat_out[name] = _cell(c, l, lytd, cat_total_c, cat_total_l, cat_total_lytd, overall_c, overall_l, overall_lytd)
        out[str(cat)] = cat_out
    return out


@lru_cache(maxsize=1)
def _dim_labels() -> dict[str, str]:
    """{column: pretty label} for the row-hierarchy headings."""
    return {d["column"]: d["label"] for d in get_dimension_catalog()}


def _group_children(roll: dict) -> dict:
    """{(v0, v1): measures} -> {v0: {(v1,): measures}} in ONE pass."""
    out: dict = {}
    for key, value in roll.items():
        out.setdefault(key[0], {})[key[1:]] = value
    return out


def _row(
    label: str,
    level: int,
    is_overall: bool,
    dim_values: dict,
    data: dict,
    path: list | None = None,
) -> dict:
    return {
        "row_label": label,
        "is_overall": is_overall,
        "_level": level,
        "dim_values": dim_values,
        "_path": path or [],
        "_data": data,
    }


def _build_rows(
    dims: tuple[str, ...],
    meta: dict,
    idx1_c: dict,
    idx1_l: dict,
    idx1_lytd: dict,
    idx2_c: dict,
    idx2_l: dict,
    idx2_lytd: dict,
) -> tuple[list, list]:
    """Level-1 and Level-2 rows, driven ONLY by the Row Hierarchy.

    Level 1 rows  = "Overall" grand total + every level-1 dimension value
                    (summed across every DEEPER row dimension, so each one is a
                    true total at its own grain - never an average of children).
    Level 2 rows  = the same level-1 values, each followed by its level-2
                    children (`_level` 1 / 2 lets the UI indent the drill-down).
    """
    categories = meta["categories"]
    subs = meta["sub_categories"]
    n = len(dims)
    cat_pos = (n,)          # position of `category` inside a Level-1 key
    sub_pos = (n, n + 1)    # positions of `category` + `sub_category` in a Level-2 key

    # Grand total: a GENUINE re-aggregation over the WHOLE filtered context, so
    # its lookup tables are rolled up to (category[, sub-category]).  With no row
    # dims those rollups are the identity, so one code path serves both cases.
    grand1_c = _rollup(idx1_c, cat_pos)
    grand1_l = _rollup(idx1_l, cat_pos)
    grand1_lytd = _rollup(idx1_lytd, cat_pos)
    grand2_c = _rollup(idx2_c, sub_pos)
    grand2_l = _rollup(idx2_l, sub_pos)
    grand2_lytd = _rollup(idx2_lytd, sub_pos)

    rows1 = [_row("Overall", 0, True, {}, _level1_data((), grand1_c, grand1_l, grand1_lytd, categories, grand1_c, grand1_l, grand1_lytd))]
    rows2 = [_row(
        "Overall", 0, True, {},
        _level2_data((), grand2_c, grand2_l, grand2_lytd, categories, subs, grand2_c, grand2_l, grand2_lytd),
    )]
    if not dims:
        return rows1, rows2

    dim0 = dims[0]

    # ---- Level 1: (level-1 value) x Category ------------------------------
    l1_c = _rollup(idx1_c, (0,) + cat_pos)
    l1_l = _rollup(idx1_l, (0,) + cat_pos)
    l1_lytd = _rollup(idx1_lytd, (0,) + cat_pos)
    for value in _union_values(_rollup(l1_c, (0,)), _rollup(l1_l, (0,))):
        label = _fmt_dim(value)
        rows1.append(_row(
            label, 1, False, {dim0: label},
            _level1_data((value,), l1_c, l1_l, l1_lytd, categories, grand1_c, grand1_l, grand1_lytd),
            [label],
        ))

    # ---- Level 2: (level-1 -> level-2 value) x Category x Sub-Category ----
    l2_c = _rollup(idx2_c, (0,) + sub_pos)
    l2_l = _rollup(idx2_l, (0,) + sub_pos)
    l2_lytd = _rollup(idx2_lytd, (0,) + sub_pos)
    child_c: dict = {}
    child_l: dict = {}
    child_lytd: dict = {}
    kids_c: dict = {}
    kids_l: dict = {}
    if len(dims) > 1:
        child_c = _rollup(idx2_c, (0, 1) + sub_pos)
        child_l = _rollup(idx2_l, (0, 1) + sub_pos)
        child_lytd = _rollup(idx2_lytd, (0, 1) + sub_pos)
        kids_c = _group_children(_rollup(child_c, (0, 1)))
        kids_l = _group_children(_rollup(child_l, (0, 1)))

    for value in _union_values(_rollup(l2_c, (0,)), _rollup(l2_l, (0,))):
        label = _fmt_dim(value)
        prefix = (value,)
        rows2.append(_row(
            label, 1, False, {dim0: label},
            _level2_data(prefix, l2_c, l2_l, l2_lytd, categories, subs, grand2_c, grand2_l, grand2_lytd),
            [label],
        ))
        if not child_c:
            continue
        dim1 = dims[1]
        for child in _union_values(kids_c.get(value, {}), kids_l.get(value, {})):
            child_label = _fmt_dim(child)
            rows2.append(_row(
                child_label, 2, False, {dim0: label, dim1: child_label},
                _level2_data(prefix + (child,), child_c, child_l, child_lytd, categories, subs, grand2_c, grand2_l, grand2_lytd),
                [label, child_label],
            ))
    return rows1, rows2


def _filter_items(filters: dict[str, list[str]] | None) -> tuple:
    """Hashable, order-independent cache key for the applied slicers."""
    return tuple(sorted(
        ((str(col), tuple(values)) for col, values in (filters or {}).items() if values),
        key=lambda item: item[0],
    ))


def run_category_analysis(
    filters: dict[str, list[str]] | None = None,
    hierarchy: list[str] | None = None,
) -> dict[str, Any]:
    """Main entry point - the full payload for the Category Performance tab.

    Both inputs come from the PAGE-LEVEL controls: `hierarchy` is the Row
    Hierarchy (level 1, level 2) and `filters` are the global slicers.  The
    result is memoised on that pair, so toggling a slicer back or re-ordering
    the hierarchy is served straight from memory.
    """
    dims = _resolve_row_dims(hierarchy)
    return dict(_cached_payload(dims, _filter_items(filters), cache_token()))


@lru_cache(maxsize=64)
def _cached_payload(dims: tuple[str, ...], filter_items: tuple, _token: tuple) -> dict[str, Any]:
    """`_token` is the freshness key (data revision + enrichment state) and is
    never used in the computation itself - it only ensures the payload is
    rebuilt when the store master it was derived from changes."""
    filters = {col: list(values) for col, values in filter_items}
    meta = get_category_meta()
    categories = meta["categories"]
    labels = _dim_labels()
    row_dims = [
        {"column": d, "label": labels.get(d, d.replace("_", " ").upper())} for d in dims
    ]

    payload: dict[str, Any] = {
        "categories": categories,
        "sub_categories": meta["sub_categories"],
        "row_dims": row_dims,
        "row_dim_chain": [d["label"] for d in row_dims],
        "rows_level1": [],
        "rows_level2": [],
        "fy_context": None,
    }

    fy = _fy_context()
    if fy is None or not categories:
        return payload
    payload["fy_context"] = fy.to_dict()

    df = _apply_filters(_load_facts(_cache_token()), filters)
    if not df.empty:
        tx = df["tx_date"]
        cfy = df[(tx >= pd.Timestamp(fy.current_fy_start)) & (tx <= pd.Timestamp(fy.current_fy_end))]
        lfy = df[(tx >= pd.Timestamp(fy.last_fy_start)) & (tx <= pd.Timestamp(fy.last_fy_end))]
        # TWO groupbys feed both tables: Level 1 keys, Level 2 keys.
        lfy_ytd = df[(tx >= pd.Timestamp(fy.last_fy_start)) & (tx <= pd.Timestamp(fy.lfy_ytd_end))]

        keys1 = list(dims) + [CATEGORY_COL]
        keys2 = list(dims) + [CATEGORY_COL, SUBCATEGORY_COL]
        idx1_c = _sum_index(cfy, keys1)
        idx1_l = _sum_index(lfy, keys1)
        idx1_lytd = _sum_index(lfy_ytd, keys1)
        idx2_c = _sum_index(cfy, keys2)
        idx2_l = _sum_index(lfy, keys2)
        idx2_lytd = _sum_index(lfy_ytd, keys2)
    else:
        idx1_c = idx1_l = idx1_lytd = idx2_c = idx2_l = idx2_lytd = {}

    rows1, rows2 = _build_rows(dims, meta, idx1_c, idx1_l, idx1_lytd, idx2_c, idx2_l, idx2_lytd)
    payload["rows_level1"] = rows1
    payload["rows_level2"] = rows2
    return payload


def run_category_brand_analysis(
    filters: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    return dict(_cached_category_brand_payload(_filter_items(filters), cache_token()))

@lru_cache(maxsize=64)
def _cached_category_brand_payload(filter_items: tuple, _token: tuple) -> dict[str, Any]:
    filters = {col: list(values) for col, values in filter_items}
    meta = get_category_meta()
    categories = meta["categories"]
    
    payload: dict[str, Any] = {
        "rows": [],
        "fy_context": None,
    }
    
    fy = _fy_context()
    if fy is None or not categories:
        return payload
    payload["fy_context"] = fy.to_dict()

    df = _apply_filters(_load_facts(_cache_token()), filters)
    if df.empty or "brand" not in df.columns:
        return payload

    tx = df["tx_date"]
    cfy = df[(tx >= pd.Timestamp(fy.current_fy_start)) & (tx <= pd.Timestamp(fy.current_fy_end))]
    lfy = df[(tx >= pd.Timestamp(fy.last_fy_start)) & (tx <= pd.Timestamp(fy.last_fy_end))]

    keys = [CATEGORY_COL, "brand"]
    idx_c = _sum_index(cfy, keys)
    idx_l = _sum_index(lfy, keys)

    all_keys = set(idx_c.keys()).union(set(idx_l.keys()))
    valid_cats = set(categories)
    
    rows = []
    for key in all_keys:
        cat, brand = key
        if str(cat) not in valid_cats:
            continue
        
        c_qty, c_val, c_mrp = idx_c.get(key, _ZERO)
        l_qty, l_val, l_mrp = idx_l.get(key, _ZERO)
        
        if c_qty == 0 and l_qty == 0:
            continue
        
        rows.append({
            "category": _fmt_dim(cat),
            "brand": _fmt_dim(brand),
            "tfy_qty": float(c_qty),
            "lfy_qty": float(l_qty),
            "tfy_value": float(c_val),
            "lfy_value": float(l_val),
            "tfy_mrp_value": float(c_mrp),
            "lfy_mrp_value": float(l_mrp),
        })
    
    payload["rows"] = rows
    return payload

