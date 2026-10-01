"""
SQL Query Platform (Module III) execution engine.

Everything the SQL IDE's autocomplete needs (databases, tables, columns,
SQL functions) is discovered live from DuckDB's own catalog - see
`get_full_schema_tree()` in core.database and `list_sql_functions()` below.
Nothing is a hard-coded keyword list beyond the small set of SQL reserved
words that every SQL dialect shares (SELECT/FROM/WHERE/...), which are
language syntax, not schema.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError

import pandas as pd

from app.core.config import (
    MAX_SQL_ROWS_EXPORT,
    MAX_SQL_ROWS_PREVIEW,
    QUERY_TIMEOUT_SECONDS,
)
from app.core.database import get_connection

_executor = ThreadPoolExecutor(max_workers=4)

# The ANSI/DuckDB reserved keywords are language syntax, not schema, so a
# small static list here is not a "hard-coded schema assumption" - it's the
# same category of thing as knowing what `SELECT` means.
SQL_KEYWORDS = [
    "SELECT", "FROM", "WHERE", "GROUP BY", "ORDER BY", "HAVING", "LIMIT",
    "OFFSET", "JOIN", "LEFT JOIN", "RIGHT JOIN", "INNER JOIN", "FULL JOIN",
    "ON", "AS", "DISTINCT", "UNION", "UNION ALL", "INTERSECT", "EXCEPT",
    "WITH", "CASE", "WHEN", "THEN", "ELSE", "END", "AND", "OR", "NOT", "IN",
    "BETWEEN", "LIKE", "ILIKE", "IS NULL", "IS NOT NULL", "EXISTS", "ASC",
    "DESC", "INSERT INTO", "UPDATE", "DELETE FROM", "CREATE TABLE",
    "CREATE VIEW", "DROP TABLE", "ALTER TABLE", "VALUES", "SET",
    "PIVOT", "UNPIVOT", "QUALIFY", "WINDOW", "OVER", "PARTITION BY",
    "ROLLUP", "GROUPING SETS", "CUBE",
]


def list_sql_functions() -> list[str]:
    """DuckDB's own function catalog - fully dynamic, grows/shrinks with the
    DuckDB version in use, never hard-coded."""
    con = get_connection()
    rows = con.execute(
        "SELECT DISTINCT function_name FROM duckdb_functions() "
        "WHERE function_type IN ('scalar','aggregate','table') "
        "ORDER BY 1"
    ).fetchall()
    return [r[0] for r in rows]


def _run(sql: str) -> pd.DataFrame:
    con = get_connection()
    return con.execute(sql).fetchdf()


def execute_query(sql: str, limit: int | None = None) -> dict:
    sql_clean = sql.strip().rstrip(";")
    if not sql_clean:
        raise ValueError("Empty query")

    start = time.time()
    future = _executor.submit(_run, sql_clean)
    try:
        df = future.result(timeout=QUERY_TIMEOUT_SECONDS)
    except FutureTimeoutError:
        try:
            get_connection().interrupt()
        except Exception:  # noqa: S110, BLE001
            pass
        raise TimeoutError(
            f"Query exceeded the {QUERY_TIMEOUT_SECONDS}s timeout and was cancelled."
        )
    elapsed_ms = int((time.time() - start) * 1000)

    total_rows = len(df)
    effective_limit = limit or MAX_SQL_ROWS_PREVIEW
    truncated = total_rows > effective_limit
    preview = df.head(effective_limit)
    preview = preview.where(pd.notnull(preview), None)

    columns = [{"name": c, "type": str(dt)} for c, dt in zip(preview.columns, preview.dtypes)]
    return {
        "columns": columns,
        "rows": preview.to_dict(orient="records"),
        "row_count": total_rows,
        "returned_rows": len(preview),
        "truncated": truncated,
        "elapsed_ms": elapsed_ms,
    }


def execute_for_export(sql: str) -> pd.DataFrame:
    sql_clean = sql.strip().rstrip(";")
    con = get_connection()
    df = con.execute(f"SELECT * FROM ({sql_clean}) AS _q LIMIT {MAX_SQL_ROWS_EXPORT}").fetchdf()
    return df
