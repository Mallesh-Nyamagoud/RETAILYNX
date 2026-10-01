"""
Store Master (Module II): KPI cards, slicers, the editable store table, and
admin edit support.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from functools import lru_cache
from typing import Any

from app.core.database import (
    bump_data_revision,
    cache_token,
    column_exists,
    execute,
    execute_df,
    filter_key,
    get_connection,
    quote_ident,
    recompute_store_master_enrichment,
)

SCHEMA, TABLE = "store_master", "store_details"
ADMIN_PASSWORD = "ADONIS@13719"

_NON_SLICER_COLUMNS = {"adonis_store_code", "brand_code", "ter_min_date", "ter_max_date"}


def _require_admin_password(password: str | None) -> None:
    if password != ADMIN_PASSWORD:
        raise PermissionError("Invalid admin password")


def _to_date(value):
    if value is None or value == "":
        return None
    if hasattr(value, "date"):
        return value.date()
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    return value


def determine_store_status(ter_min_date, ter_max_date, global_max_date, current_fy_start, last_fy_start):
    """Per STORE + BRAND status (updated spec).  All comparisons are against
    the GLOBAL MAX date in the tertiary sales data.

      - Closed: had sales previously but none in the last 3 months before the
        global max date (checked first - a store that stopped selling is
        Closed regardless of when it opened).
      - New: no sales in the previous FY but has sales in the current FY.
      - Annualized: sales began in the previous FY but not in April of it.
      - L2L: sales began in April of the previous FY (or earlier).
      - NA: NON-SIS - no tertiary sales data at all.
    """
    ter_min_date = _to_date(ter_min_date)
    ter_max_date = _to_date(ter_max_date)
    global_max_date = _to_date(global_max_date)
    current_fy_start = _to_date(current_fy_start)
    last_fy_start = _to_date(last_fy_start)

    if ter_min_date is None or ter_max_date is None:
        return "NA"
    if global_max_date is not None and ter_max_date < (global_max_date - timedelta(days=90)):
        return "Closed"
    if ter_min_date >= current_fy_start:
        return "New"
    if last_fy_start is not None and ter_min_date >= last_fy_start and ter_min_date < current_fy_start:
        if ter_min_date.month == 4 and ter_min_date.year == last_fy_start.year:
            return "L2L"
        return "Annualized"
    return "L2L"


# Statuses that make a door "active".  A store with MULTIPLE brands counts as
# ONE active door if ANY ONE of its brands is L2L / Annualized / New -
# irrespective of how many brands exist (user-confirmed rule).
ACTIVE_STATUSES = {"L2L", "Annualized", "New"}


def _distinct_doors(rows, status):
    """Distinct ADONIS STORE CODES whose status equals `status` (NA-safe)."""
    return len({
        str(r.get("adonis_store_code"))
        for r in rows
        if r.get("adonis_store_code") is not None
        and (r.get("store_status") or "NA") == status
    })


def _active_door_count(rows):
    """TOTAL ACTIVE DOORS: counted on ADONIS STORE CODE - a store counts as
    ONE active door if ANY ONE of its brands is L2L / Annualized / New,
    irrespective of how many brands exist."""
    return len({
        str(r.get("adonis_store_code"))
        for r in rows
        if r.get("adonis_store_code") is not None
        and (r.get("store_status") or "NA") in ACTIVE_STATUSES
    })


def _brand_summary_rows(rows):
    """BRAND-wise store status summary, grouped by BRAND NAME (not brand_code):
    Brand | Total Active Doors | L2L | Annualized | New | Non-SIS."""
    by_brand = defaultdict(list)
    for r in rows:
        by_brand[r.get("brand") or "Unknown"].append(r)
    out = []
    for brand, brows in by_brand.items():
        out.append({
            "brand": brand,
            "total_active_doors": _active_door_count(brows),
            "l2l": _distinct_doors(brows, "L2L"),
            "annualized": _distinct_doors(brows, "Annualized"),
            "new": _distinct_doors(brows, "New"),
            "non_sis": _distinct_doors(brows, "NA"),
        })
    out.sort(key=lambda r: (-r["total_active_doors"], r["brand"]))
    return out


def _counts_by_status(rows):
    unique_codes = set()
    counts_by_status = defaultdict(set)
    for row in rows:
        status = (row.get("store_status") or "Unknown").strip() or "Unknown"
        code = row.get("adonis_store_code")
        if code is None:
            continue
        unique_codes.add(str(code))
        counts_by_status[status].add(str(code))

    counts = {status: len(codes) for status, codes in counts_by_status.items()}
    total_doors = len(unique_codes)
    closed = counts.get("Closed", 0)
    active_doors = total_doors - closed
    counts["total_active_doors"] = active_doors
    counts["total_doors"] = total_doors
    return counts


def _ensure_store_status_enrichment() -> None:
    # store_status is written for EVERY row by recompute_store_master_enrichment
    # (SIS rows get their real status, NON-SIS rows get 'NA' in the final
    # sweep), so `store_status IS NULL` is a precise "enrichment incomplete"
    # signal.  Checking ter_min_date/ter_max_date too would be WRONG: NON-SIS
    # rows legitimately leave those two date columns null, and counting them
    # as "missing" triggered a full recompute (with bump_data_revision) on
    # EVERY read -> cache_token() changed every call -> every token-keyed
    # cache thrashed. This is purely a completeness gate: it never mutates data
    # or skip an actually-needed recompute.
    missing = execute(
        f"SELECT COUNT(*) FROM {SCHEMA}.{TABLE} WHERE store_status IS NULL"
    )
    if missing and int(missing[0][0]) > 0:
        recompute_store_master_enrichment()


@lru_cache(maxsize=1)
def _columns_cached() -> tuple[tuple[str, str], ...]:
    """Column catalog, read ONCE per process.

    `store_details`' column SET never changes while the app is running (the
    enrichment columns are ALTER-added by the startup bootstrap), so this is a
    safe lifetime cache.  Previously `information_schema` was re-queried up to
    three times per request (`get_slicer_columns` -> `_filter_sql`,
    `get_table`'s validation + its search-column list).
    """
    rows = execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        f"WHERE table_catalog='{SCHEMA}' AND table_name='{TABLE}' ORDER BY ordinal_position"
    )
    return tuple((r[0], r[1]) for r in rows)


def get_all_columns() -> list[dict]:
    return [{"name": name, "type": dtype} for name, dtype in _columns_cached()]


@lru_cache(maxsize=1)
def _slicer_columns_cached() -> tuple[tuple[str, str], ...]:
    return tuple(
        (name, name.replace("_", " ").upper())
        for name, dtype in _columns_cached()
        if name not in _NON_SLICER_COLUMNS and dtype == "VARCHAR"
    )


def get_slicer_columns() -> list[dict]:
    return [{"column": col, "label": label} for col, label in _slicer_columns_cached()]


@lru_cache(maxsize=8)
def _slicer_options_cached(_token: tuple) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Distinct values per slicer column, rebuilt only when the data changes
    (the `_token` argument is the cache key, never used in the computation)."""
    out: list[tuple[str, tuple[str, ...]]] = []
    for col, _label in _slicer_columns_cached():
        quoted = quote_ident(col)
        rows = execute(
            f"SELECT DISTINCT {quoted} FROM {SCHEMA}.{TABLE} WHERE {quoted} IS NOT NULL ORDER BY 1"
        )
        out.append((col, tuple(r[0] for r in rows)))
    return tuple(out)


def get_slicer_options() -> dict[str, list[str]]:
    return {col: list(values) for col, values in _slicer_options_cached(cache_token())}


def _filter_sql(filters: dict[str, list[str]]) -> tuple[str, list[Any]]:
    clauses, params = [], []
    valid = {c["column"] for c in get_slicer_columns()}
    for col, values in (filters or {}).items():
        if not values:
            continue
        if col not in valid:
            raise ValueError(f"Unknown filter column: {col}")
        placeholders = ",".join(["?"] * len(values))
        clauses.append(f"{quote_ident(col)} IN ({placeholders})")
        params.extend(values)
    if not clauses:
        return "", []
    return " AND " + " AND ".join(clauses), params


def get_kpis(filters: dict[str, list[str]] | None = None) -> dict:
    """Store Master KPIs (updated spec).

    ONE KPI card: TOTAL ACTIVE DOORS - counted on ADONIS STORE CODE; a store
    with multiple brands counts ONCE if ANY ONE brand is L2L / Annualized /
    New, irrespective of how many brands exist.

    Plus the BRAND-wise store status summary table grouped by BRAND NAME
    (not brand_code): Brand | Total Active Doors | L2L | Annualized | New |
    Non-SIS.

    Memoised on (filters, data token): two or three SQL round-trips per slicer
    click become a dict lookup, and the payload is dropped automatically the
    moment the store master (or its status enrichment) changes.
    """
    return dict(_kpis_cached(filter_key(filters), cache_token()))


@lru_cache(maxsize=32)
def _kpis_cached(filters_key: tuple, _token: tuple) -> dict:
    """Body of `get_kpis` (the `_token` argument is the cache key only)."""
    filters = {col: list(values) for col, values in filters_key}
    _ensure_store_status_enrichment()
    filter_sql, params = _filter_sql(filters)
    df = execute_df(
        f"""
        SELECT
            adonis_store_code,
            COALESCE(brand, 'Unknown') AS brand,
            COALESCE(store_status, 'NA') AS store_status
        FROM {SCHEMA}.{TABLE}
        WHERE 1=1 {filter_sql}
        """,
        params,
    )
    rows = df.to_dict(orient="records")
    total_doors = len({r.get("adonis_store_code") for r in rows if r.get("adonis_store_code")})

    return {
        "total_active_doors": _active_door_count(rows),
        "total_doors": total_doors,
        "by_status": {
            status: _distinct_doors(rows, status)
            for status in ("L2L", "Annualized", "New", "Closed", "NA")
        },
        "brand_summary": _brand_summary_rows(rows),
    }


def get_table(
    filters: dict[str, list[str]] | None = None,
    search: str | None = None,
    sort_by: str | None = None,
    sort_dir: str = "asc",
    page: int = 1,
    page_size: int = 50,
) -> dict:
    _ensure_store_status_enrichment()
    filter_sql, params = _filter_sql(filters or {})
    valid_cols = {c["name"] for c in get_all_columns()}

    search_sql = ""
    if search:
        searchable = [c["name"] for c in get_all_columns() if c["type"] == "VARCHAR"]
        like_clauses = " OR ".join(f"{quote_ident(c)} ILIKE ?" for c in searchable)
        search_sql = f" AND ({like_clauses})"
        params = params + [f"%{search}%" for _ in searchable]

    order_sql = ""
    if sort_by:
        if sort_by not in valid_cols:
            raise ValueError(f"Unknown sort column: {sort_by}")
        direction = "DESC" if str(sort_dir).lower() == "desc" else "ASC"
        order_sql = f" ORDER BY {quote_ident(sort_by)} {direction}"
    else:
        order_sql = " ORDER BY adonis_store_code ASC"

    count_row = execute(
        f"SELECT COUNT(*) FROM {SCHEMA}.{TABLE} WHERE 1=1 {filter_sql}{search_sql}", params
    )
    total = int(count_row[0][0])

    page = max(page, 1)
    offset = (page - 1) * page_size
    df = execute_df(
        f"SELECT * FROM {SCHEMA}.{TABLE} WHERE 1=1 {filter_sql}{search_sql}{order_sql} "
        f"LIMIT {int(page_size)} OFFSET {int(offset)}",
        params,
    )
    df = df.where(df.notnull(), None)
    return {
        "rows": df.to_dict(orient="records"),
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def update_store(adonis_store_code: str, brand_code: str, updates: dict[str, Any], password: str | None = None) -> dict:
    _require_admin_password(password)
    valid_cols = {c["name"] for c in get_all_columns()}
    protected = {"adonis_store_code", "brand_code"}
    set_clauses, params = [], []
    for col, val in updates.items():
        if col in protected:
            continue
        if col not in valid_cols:
            raise ValueError(f"Unknown column: {col}")
        set_clauses.append(f"{quote_ident(col)} = ?")
        params.append(val)
    if not set_clauses:
        raise ValueError("No valid fields to update")

    con = get_connection()
    params.extend([adonis_store_code, brand_code])
    con.execute(
        f"UPDATE {SCHEMA}.{TABLE} SET {', '.join(set_clauses)} "
        "WHERE adonis_store_code = ? AND brand_code = ?",
        params,
    )
    try:
        con.execute("CHECKPOINT")
    except Exception:  # noqa: S110, BLE001
        pass
    # An edit changes dimension values / status attributes -> drop every
    # token-keyed read cache so KPIs, slicers, CSS and category mix re-read.
    bump_data_revision()
    row = con.execute(
        f"SELECT * FROM {SCHEMA}.{TABLE} WHERE adonis_store_code = ? AND brand_code = ?",
        [adonis_store_code, brand_code],
    ).fetchdf()
    row = row.where(row.notnull(), None)
    return row.to_dict(orient="records")[0] if len(row) else {}


def create_store(adonis_store_code: str, brand_code: str, values: dict[str, Any], password: str | None = None) -> dict:
    _require_admin_password(password)
    if not column_exists(SCHEMA, TABLE, "adonis_store_code"):
        raise ValueError("store_details table missing adonis_store_code")
    con = get_connection()
    existing = con.execute(
        f"SELECT 1 FROM {SCHEMA}.{TABLE} WHERE adonis_store_code=? AND brand_code=?",
        [adonis_store_code, brand_code],
    ).fetchone()
    if existing:
        raise ValueError("A store with this ADONIS STORE CODE + BRAND CODE already exists")

    valid_cols = {c["name"] for c in get_all_columns()}
    cols = ["adonis_store_code", "brand_code"]
    vals: list[Any] = [adonis_store_code, brand_code]
    for col, val in values.items():
        if col in cols or col not in valid_cols:
            continue
        cols.append(col)
        vals.append(val)
    placeholders = ",".join(["?"] * len(cols))
    con.execute(
        f"INSERT INTO {SCHEMA}.{TABLE} ({', '.join(quote_ident(c) for c in cols)}) "
        f"VALUES ({placeholders})",
        vals,
    )
    bump_data_revision()
    row = con.execute(
        f"SELECT * FROM {SCHEMA}.{TABLE} WHERE adonis_store_code=? AND brand_code=?",
        [adonis_store_code, brand_code],
    ).fetchdf()
    row = row.where(row.notnull(), None)
    return row.to_dict(orient="records")[0] if len(row) else {}


def delete_store(adonis_store_code: str, brand_code: str, password: str | None = None) -> None:
    _require_admin_password(password)
    con = get_connection()
    con.execute(
        f"DELETE FROM {SCHEMA}.{TABLE} WHERE adonis_store_code=? AND brand_code=?",
        [adonis_store_code, brand_code],
    )
    bump_data_revision()
