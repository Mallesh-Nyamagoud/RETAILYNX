"""
DuckDB catalog manager.

The whole app runs on ONE DuckDB connection that has all four source
databases ATTACHed as named schemas. This gives us native cross-database SQL
(joins across store_master / order_form / secondary_data / tertiary_data)
without an ETL warehouse, and it is what powers the schema-driven SQL
Platform (Module III) - "databases" in that UI are simply the attached
schemas, "tables" are whatever information_schema reports, so nothing is
hard-coded.

DuckDB connections are not safe for concurrent use from multiple threads, so
all access goes through a single re-entrant lock.
"""
from __future__ import annotations

import logging
import shutil
import threading
from collections.abc import Iterable
from typing import Any

import duckdb
import pandas as pd

from app.core.config import ATTACH_SCHEMAS, SEED_FILES, WORKING_DIR

WORKING_FILES = {key: WORKING_DIR / f"{key}_working.duckdb" for key in SEED_FILES}

log = logging.getLogger(__name__)

_lock = threading.RLock()
_connection: duckdb.DuckDBPyConnection | None = None

# Status of the store-status enrichment job (see `_run_enrichment_background`
# below). Read via `get_enrichment_status()` - lets the frontend show "still
# computing" instead of silently seeing NULL store_status/ter_min/ter_max
# values for the few seconds/minutes it takes on a cold start.
_enrichment_status: dict = {"state": "idle", "detail": None, "updated": 0, "max_tertiary_date": None}

# Monotonic counter bumped whenever the WORKING data changes in a way that can
# invalidate a memoised read: a Store-Master edit, a status-enrichment rewrite,
# or a reset back to the seed files.  Together with the enrichment state it
# forms `cache_token()` - the ONE freshness key every cached read path uses,
# so a request is never served a payload built from superseded data.  Nothing
# about the business logic changes: the token only decides cache membership.
_db_initialized = False
_data_revision = 0


def bump_data_revision() -> int:
    """Invalidate every token-keyed cache (see `cache_token`)."""
    global _data_revision
    with _lock:
        _data_revision += 1
        return _data_revision


def cache_token() -> tuple:
    """Freshness token for memoised read paths.

    `(enrichment state, rows updated, data revision)` - three in-memory reads,
    no SQL.  Any cached payload keyed on this tuple is automatically discarded
    as soon as the underlying data (or the store-status enrichment) changes.
    """
    status = get_enrichment_status()
    return (status.get("state"), status.get("updated"), _data_revision)


def filter_key(filters: dict | None) -> tuple:
    """Hashable, order-independent cache key for a `{column: [values]}` filter
    dict (sorted keys AND sorted values).

    Sorting is cache-cosmetic only: the filters are AND-ed `IN (...)` clauses,
    so the value order inside a list has no effect on the result set - the
    payload is byte-identical whether the key was sorted or not.  Empty value
    lists (which every module already ignores) are dropped from the key.
    """
    return tuple(
        sorted(
            (str(col), tuple(sorted(str(v) for v in values)))
            for col, values in (filters or {}).items()
            if values
        )
    )


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
def _ensure_working_copies(force: bool = False) -> None:
    """Copy seed databases into writable working copies if missing."""
    WORKING_DIR.mkdir(parents=True, exist_ok=True)
    for key, working_path in WORKING_FILES.items():
        seed_path = SEED_FILES[key]
        wal_path = working_path.with_name(working_path.name + ".wal")
        if force or not working_path.exists():
            if working_path.exists():
                working_path.unlink()
            if wal_path.exists():
                wal_path.unlink()
            shutil.copyfile(seed_path, working_path)


def _attach_all(con: duckdb.DuckDBPyConnection) -> None:
    attached = {row[0] for row in con.execute("PRAGMA database_list").fetchall()}
    for key, schema in ATTACH_SCHEMAS.items():
        if schema in attached:
            continue
        path = WORKING_FILES[key]
        con.execute(f"ATTACH '{path.as_posix()}' AS {schema}")


def init_db(reset: bool = False, block_on_enrichment: bool = False) -> None:
    """Initialise (or reset) the catalog. Call once at app startup.

    IMPORTANT: `recompute_store_master_enrichment()` scans the full
    tertiary_data table and rewrites every store_master row. On a large
    dataset (or a slow/locked disk, or a WAL that has to replay after an
    unclean previous shutdown) that can take anywhere from seconds to
    several minutes. It used to run inline, synchronously, as part of this
    function - and since this function runs inside the FastAPI `lifespan`
    startup handler, uvicorn will not serve *any* request (not even
    `/api/health`) until it returns. A slow enrichment therefore froze the
    entire app, with every page showing an endless loading skeleton until
    the client's own axios timeout finally gave up.

    The database is fully attached and queryable as soon as `_attach_all`
    and `_bootstrap_store_master_columns` finish (both are fast: an ATTACH
    and a couple of ALTER TABLE ADD COLUMN calls). Everything after that -
    the enrichment - is dispatched to a background thread so the app becomes
    responsive immediately; store_status/ter_min_date/ter_max_date simply
    stay NULL until that thread finishes, same as they would if a store had
    no matching tertiary transactions at all. Pass block_on_enrichment=True
    to wait for it inline instead (e.g. in scripts/tests that need the
    enriched columns populated before continuing).
    """
    global _connection
    with _lock:
        _ensure_working_copies(force=reset)
        if _connection is not None and reset:
            try:
                _connection.close()
            except Exception:  # noqa: S110, BLE001
                pass
            _connection = None
        if _connection is None:
            catalog_path = ":memory:"  # Use in-memory DB for dev to avoid hot-reload file locks
            _connection = duckdb.connect(catalog_path)
        _attach_all(_connection)
        _bootstrap_store_master_columns(_connection)
    if reset:
        # A factory reset swaps in fresh working databases -> drop every
        # memoised payload built from the previous ones.
        bump_data_revision()
    _db_initialized = True

    if block_on_enrichment:
        _run_enrichment_background()
    else:
        threading.Thread(
            target=_run_enrichment_background,
            name="store-status-enrichment",
            daemon=True,
        ).start()


def get_enrichment_status() -> dict:
    """Current state of the background store-status enrichment job: one of
    idle / running / done / error, plus the result (or error) of the last
    run. Polled by the frontend so it can show a subtle "still computing
    store status" notice instead of just silently showing blanks."""
    with _lock:
        return dict(_enrichment_status)


def _run_enrichment_background() -> None:
    global _enrichment_status
    with _lock:
        _enrichment_status = {
            "state": "running",
            "detail": None,
            "updated": 0,
            "max_tertiary_date": None,
        }
    try:
        result = recompute_store_master_enrichment()
        with _lock:
            _enrichment_status = {"state": "done", "detail": None, **result}
    except Exception as e:  # never let a background thread crash silently
        log.exception("Store-status enrichment failed")
        with _lock:
            _enrichment_status = {
                "state": "error",
                "detail": str(e),
                "updated": 0,
                "max_tertiary_date": None,
            }


def get_connection() -> duckdb.DuckDBPyConnection:
    if _connection is None:
        init_db()
    return _connection  # type: ignore[return-value]


def checkpoint_and_close() -> None:
    """Flush WAL and close cleanly (called on graceful shutdown)."""
    global _connection
    with _lock:
        if _connection is not None:
            try:
                # _connection.execute("CHECKPOINT")
                _connection.close()
            except Exception as e:  # noqa: BLE001
                log.warning(f"Error during DB shutdown: {e}")
            finally:
                _connection = None


def reset_to_seed_data() -> None:
    """Factory-reset every working database back to the original uploads."""
    init_db(reset=True)


# ---------------------------------------------------------------------------
# Query helpers (thread-safe wrappers)
# ---------------------------------------------------------------------------
def execute_df(sql: str, params: Iterable[Any] | None = None) -> pd.DataFrame:
    with _lock:
        con = get_connection()
        if params:
            return con.execute(sql, list(params)).fetchdf()
        return con.execute(sql).fetchdf()


def execute(sql: str, params: Iterable[Any] | None = None) -> list[tuple]:
    with _lock:
        con = get_connection()
        if params:
            return con.execute(sql, list(params)).fetchall()
        return con.execute(sql).fetchall()


def executemany_or_script(sql: str) -> None:
    with _lock:
        con = get_connection()
        con.execute(sql)


# ---------------------------------------------------------------------------
# Schema introspection (used by the Schema Explorer / SQL autocomplete / all
# dynamic dimension pickers - NOTHING about table/column names is hard-coded
# beyond this point in the app).
# ---------------------------------------------------------------------------
def list_databases() -> list[str]:
    with _lock:
        con = get_connection()
        rows = con.execute(
            "SELECT database_name FROM duckdb_databases() "
            "WHERE database_name NOT IN ('system','temp') ORDER BY 1"
        ).fetchall()
        return [r[0] for r in rows]


def list_tables(database: str | None = None) -> list[dict]:
    with _lock:
        con = get_connection()
        q = (
            "SELECT table_catalog AS database_name, table_schema, table_name, table_type "
            "FROM information_schema.tables "
            "WHERE table_catalog NOT IN ('system','temp')"
        )
        params = []
        if database:
            q += " AND table_catalog = ?"
            params.append(database)
        q += " ORDER BY 1,2,3"
        df = con.execute(q, params).fetchdf()
        return df.to_dict(orient="records")


def list_columns(database: str | None = None, table: str | None = None) -> list[dict]:
    with _lock:
        con = get_connection()
        q = (
            "SELECT table_catalog AS database_name, table_schema, table_name, "
            "column_name, data_type, ordinal_position "
            "FROM information_schema.columns "
            "WHERE table_catalog NOT IN ('system','temp')"
        )
        params = []
        if database:
            q += " AND table_catalog = ?"
            params.append(database)
        if table:
            q += " AND table_name = ?"
            params.append(table)
        q += " ORDER BY 1,2,3,ordinal_position"
        df = con.execute(q, params).fetchdf()
        return df.to_dict(orient="records")


def get_full_schema_tree() -> list[dict]:
    """Nested database -> tables -> columns tree for the Schema Explorer /
    autocomplete engine on the frontend."""
    cols = list_columns()
    tree: dict[str, dict] = {}
    for row in cols:
        db = row["database_name"]
        tbl = row["table_name"]
        tree.setdefault(db, {"name": db, "tables": {}})
        tree[db]["tables"].setdefault(
            tbl, {"name": tbl, "fq_name": f"{db}.{tbl}", "columns": []}
        )
        tree[db]["tables"][tbl]["columns"].append(
            {"name": row["column_name"], "type": row["data_type"]}
        )
    out = []
    for db in sorted(tree):
        tables = [tree[db]["tables"][t] for t in sorted(tree[db]["tables"])]
        out.append({"name": db, "tables": tables})
    return out


def column_exists(database: str, table: str, column: str) -> bool:
    """Security-critical: used to validate any user-supplied identifier
    before it is interpolated into dynamic SQL (dimensions, filters, sort)."""
    with _lock:
        con = get_connection()
        row = con.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_catalog = ? "
            "AND table_name = ? AND column_name = ? LIMIT 1",
            [database, table, column],
        ).fetchone()
        return row is not None


def quote_ident(name: str) -> str:
    """Safely quote a validated SQL identifier."""
    return '"' + name.replace('"', '""') + '"'


# ---------------------------------------------------------------------------
# Store Master enrichment (Requirements: TER.MIN DATE / TER.MAX DATE /
# STORE STATUS must be derived from TERTIARY DATA)
# ---------------------------------------------------------------------------
def _bootstrap_store_master_columns(con: duckdb.DuckDBPyConnection) -> None:
    existing = {
        r[0]
        for r in con.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_catalog='store_master' AND table_name='store_details'"
        ).fetchall()
    }
    alters = []
    if "ter_min_date" not in existing:
        alters.append("ADD COLUMN ter_min_date DATE")
    if "ter_max_date" not in existing:
        alters.append("ADD COLUMN ter_max_date DATE")
    if "store_status" not in existing:
        alters.append("ADD COLUMN store_status VARCHAR")
    for clause in alters:
        con.execute(f"ALTER TABLE store_master.store_details {clause}")


def recompute_store_master_enrichment(con: duckdb.DuckDBPyConnection | None = None) -> dict:
    """
    Business rules for Store Master (updated spec):

      Scope: per STORE + BRAND, only for stores that HAVE tertiary sales data
      (SIS).  Everything is compared against the GLOBAL MAX date in the
      tertiary sales data (not the brand's own max date).

      - TER.MIN DATE = MIN(tertiary_data.date) for that STORE + BRAND
      - TER.MAX DATE = MAX(tertiary_data.date) for that STORE + BRAND
      - L2L: has tertiary sales in APRIL of the previous FY (or earlier).
      - Annualized: has sales data in the previous FY (compared to the global
        max date) but NOT April of it.
      - New: no sales in the previous FY but has sales in the current FY.
      - Closed: had sales previously but none in the LAST 3 MONTHS before the
        global max date (checked first - a store that stopped selling is
        Closed regardless of when it opened).
      - NON-SIS (store+brand not in tertiary data at all): keep 'NA' for
        store status; TER.MIN/TER.MAX dates stay empty.
    """
    owns_lock = con is None
    if owns_lock:
        _lock.acquire()
    try:
        con = con or get_connection()
        max_date_row = con.execute("SELECT MAX(date) FROM tertiary_data.data").fetchone()
        max_date = max_date_row[0] if max_date_row else None
        if max_date is None:
            bump_data_revision()
            return {"updated": 0, "max_tertiary_date": None}

        max_date_only = max_date.date() if hasattr(max_date, "date") else max_date
        max_date_literal = max_date_only.isoformat()
        con.execute(
            f"""
            CREATE OR REPLACE TEMP VIEW _fy_bounds AS
            SELECT
                CASE WHEN MONTH(DATE '{max_date_literal}') >= 4
                     THEN MAKE_DATE(YEAR(DATE '{max_date_literal}'), 4, 1)
                     ELSE MAKE_DATE(YEAR(DATE '{max_date_literal}') - 1, 4, 1)
                END AS current_fy_start,
                MAKE_DATE(CASE WHEN MONTH(DATE '{max_date_literal}') >= 4
                               THEN YEAR(DATE '{max_date_literal}')
                               ELSE YEAR(DATE '{max_date_literal}') - 1
                          END, 4, 1) - INTERVAL 1 YEAR AS last_fy_start,
                DATE '{max_date_literal}' AS global_max_date
            """
        )

        con.execute(
            """
            CREATE OR REPLACE TEMP VIEW _ter_agg AS
            -- Per STORE + BRAND first/last tertiary sale (SIS rows only).
            -- Aggregation MUST live in a GROUP BY - aggregates cannot be mixed
            -- with bare columns in the same SELECT (DuckDB BinderException).
            SELECT
                d.adonis_store_code,
                d.brand_code,
                MIN(d.date) AS ter_min_date,
                MAX(d.date) AS ter_max_date
            FROM tertiary_data.data d
            WHERE d.adonis_store_code IS NOT NULL AND d.brand_code IS NOT NULL
            GROUP BY d.adonis_store_code, d.brand_code
            """
        )

        con.execute(
            """
            CREATE OR REPLACE TEMP VIEW _store_status AS
            SELECT
                a.adonis_store_code,
                a.brand_code,
                a.ter_min_date,
                a.ter_max_date,
                CASE
                    -- Closed first: had sales previously but none in the last
                    -- 3 MONTHS before the GLOBAL MAX tertiary date.
                    WHEN a.ter_max_date < (b.global_max_date - INTERVAL 3 MONTH)
                        THEN 'Closed'
                    WHEN a.ter_min_date >= b.current_fy_start
                        THEN 'New'
                    WHEN a.ter_min_date >= b.last_fy_start
                         AND a.ter_min_date < b.current_fy_start
                        THEN CASE
                            -- April of the previous FY counts as L2L.
                            WHEN MONTH(a.ter_min_date) = 4 AND YEAR(a.ter_min_date) = YEAR(b.last_fy_start)
                                THEN 'L2L'
                            ELSE 'Annualized'
                        END
                    ELSE 'L2L'
                END AS store_status
            FROM _ter_agg a
            CROSS JOIN _fy_bounds b
            """
        )

        con.execute(
            """
            UPDATE store_master.store_details sd
            SET
                ter_min_date = s.ter_min_date,
                ter_max_date = s.ter_max_date,
                store_status = s.store_status
            FROM _store_status s
            WHERE sd.adonis_store_code = s.adonis_store_code
              AND sd.brand_code = s.brand_code
            """
        )
        # NON-SIS rows (store+brand with no tertiary data at all): keep 'NA'
        # as the store status; TER.MIN/TER.MAX dates stay empty.
        con.execute(
            "UPDATE store_master.store_details SET store_status = 'NA' WHERE store_status IS NULL"
        )
        updated = con.execute(
            "SELECT COUNT(*) FROM store_master.store_details WHERE store_status IS NOT NULL"
        ).fetchone()[0]
        # TER.MIN/TER.MAX/STORE STATUS were just rewritten -> any payload that
        # embeds them (Store Master KPIs/table, category mix, CSS slicers) must
        # be rebuilt rather than served from a token-keyed cache.
        bump_data_revision()
        return {"updated": int(updated), "max_tertiary_date": str(max_date)}
    finally:
        if owns_lock:
            _lock.release()
