"""Category-level tertiary sales and latest SOH stock analysis."""
from __future__ import annotations

import re

import duckdb
import pandas as pd

from app.core.database import execute, execute_df, quote_ident
from app.services import analysis, soh_analysis
from app.services.fy import safe_pct

SOH_DB = soh_analysis.SOH_DB
FILTER_COLUMNS = ("brand", "retailer_name", "store_status")


def get_dimensions() -> list[dict]:
    """The category is fixed; remaining row dimensions follow Tertiary Analysis."""
    return [{"column": "category", "label": "Category", "type": "VARCHAR"}] + [
        item for item in analysis.get_dimension_catalog() if item["column"] != "category"
    ]


def get_slicers() -> dict[str, list[str]]:
    available = analysis.get_slicer_options()
    return {column: available.get(column, []) for column in FILTER_COLUMNS if column in available}


def _norm(value) -> str:
    return re.sub(r"\s+", "", str(value or "")).upper()


def _filters_for_request(filters: dict[str, list[str]] | None) -> dict[str, list[str]]:
    selected = {}
    for column in FILTER_COLUMNS:
        values = (filters or {}).get(column) or []
        if values:
            selected[column] = [str(value) for value in values]
    return selected


def run_analysis(hierarchy: list[str] | None, filters: dict[str, list[str]] | None) -> dict:
    hierarchy = list(hierarchy or [])
    valid_dimensions = {item["column"] for item in get_dimensions()}
    invalid = [column for column in hierarchy if column not in valid_dimensions]
    if invalid:
        raise ValueError(f"Unknown row dimension(s): {invalid}")
    row_dimensions = [column for column in hierarchy if column != "category"]
    selected_filters = _filters_for_request(filters)
    filter_sql, filter_params = analysis._build_filter_sql(selected_filters)

    latest = execute("""
        SELECT MAX(CAST(date AS DATE)) AS max_date,
               DATE_TRUNC('month', MAX(CAST(date AS DATE))) - INTERVAL '5 months' AS six_month_start
        FROM tertiary_data.data
    """)
    if not latest or latest[0][0] is None:
        return {"rows": [], "warnings": [], "tertiary_as_of": None, "stock_as_of": None}
    sales_as_of, six_month_start = latest[0]
    sales_as_of = sales_as_of.date() if hasattr(sales_as_of, "date") else sales_as_of
    six_month_start = six_month_start.date() if hasattr(six_month_start, "date") else six_month_start

    dim_select = ", ".join(f"dim.{quote_ident(column)} AS {quote_ident(column)}" for column in row_dimensions)
    select_dims = f", {dim_select}" if dim_select else ""
    sales_rows = execute_df(f"""
        SELECT TRIM(CAST(f.category AS VARCHAR)) AS category,
               UPPER(TRIM(CAST(f.category AS VARCHAR))) AS _category_key{select_dims},
               SUM(f.qty) AS total_sales,
               SUM(f.qty) FILTER (WHERE CAST(f.date AS DATE) >= ? AND CAST(f.date AS DATE) <= ?) AS last_6m_sales
        FROM tertiary_data.data f
        LEFT JOIN store_master.store_details dim
          ON f.adonis_store_code = dim.adonis_store_code AND f.brand_code = dim.brand_code
        WHERE f.category IS NOT NULL {filter_sql}
        GROUP BY ALL
    """, [six_month_start, sales_as_of, *filter_params])
    if sales_rows.empty:
        return {"rows": [], "warnings": [], "tertiary_as_of": sales_as_of.isoformat(), "last_6m_start": six_month_start.isoformat(), "stock_as_of": None}

    warnings: list[str] = []
    if not SOH_DB.exists():
        sales_rows["current_stock"] = 0.0
        warnings.append("SOH source is missing; current stock is shown as 0.")
        combined = sales_rows
        stock_as_of = None
    else:
        with duckdb.connect(str(SOH_DB), read_only=True) as con:
            stock_as_of = con.execute("SELECT MAX(CAST(date AS DATE)) FROM data").fetchone()[0]
            stock = con.execute("""
                SELECT name AS store, code AS brand_code, gc AS category,
                       SUM(qty) AS current_stock
                FROM data
                WHERE CAST(date AS DATE) = (SELECT MAX(CAST(date AS DATE)) FROM data)
                  AND gc IS NOT NULL
                GROUP BY ALL
            """).df()
        if stock.empty:
            sales_rows["current_stock"] = 0.0
            warnings.append("No rows were found in the latest SOH snapshot; current stock is shown as 0.")
            combined = sales_rows
        else:
            stock = soh_analysis._store_code_lookup(stock, warnings)
            master_dimensions = list(dict.fromkeys([*row_dimensions, *FILTER_COLUMNS]))
            master_select = ", ".join(quote_ident(column) for column in master_dimensions)
            master = execute_df(f"""
                SELECT adonis_store_code AS store_code, brand_code, {master_select}
                FROM store_master.store_details
            """)
            master = master.drop_duplicates(subset=["store_code", "brand_code"]).copy()
            stock["_store_key"] = stock["store_code"].map(_norm)
            stock["_brand_key"] = stock["brand_code"].map(_norm)
            master["_store_key"] = master["store_code"].map(_norm)
            master["_brand_key"] = master["brand_code"].map(_norm)
            stock = stock.merge(
                master[["_store_key", "_brand_key", *master_dimensions]],
                on=["_store_key", "_brand_key"], how="left",
            )
            for column, values in selected_filters.items():
                if values:
                    stock = stock[stock[column].astype(str).isin(values)]
            stock["_category_key"] = stock["category"].astype(str).str.strip().str.upper()
            group_keys = ["_category_key", *row_dimensions]
            stock_rows = stock.groupby(group_keys, dropna=False, as_index=False)["current_stock"].sum()
            combined = sales_rows.merge(stock_rows, on=group_keys, how="left")
            combined["current_stock"] = combined["current_stock"].fillna(0)

    combined["total_sales"] = pd.to_numeric(combined["total_sales"], errors="coerce").fillna(0)
    combined["last_6m_sales"] = pd.to_numeric(combined["last_6m_sales"], errors="coerce").fillna(0)
    combined["current_stock"] = pd.to_numeric(combined["current_stock"], errors="coerce").fillna(0)
    combined["total_sales_contribution_pct"] = combined["total_sales"].map(lambda value: safe_pct(value, combined["total_sales"].sum()))
    combined["last_6m_contribution_pct"] = combined["last_6m_sales"].map(lambda value: safe_pct(value, combined["last_6m_sales"].sum()))
    combined["current_stock_contribution_pct"] = combined["current_stock"].map(lambda value: safe_pct(value, combined["current_stock"].sum()))
    combined["st_pct"] = combined.apply(lambda row: safe_pct(row["last_6m_sales"], row["current_stock"]), axis=1)
    combined["f4m_requirement"] = combined["last_6m_sales"] / 6 * 4
    combined["requirement"] = combined["current_stock"] - combined["f4m_requirement"]
    combined = combined.drop(columns=["_category_key"], errors="ignore")
    return {
        "rows": combined.to_dict("records"),
        "warnings": warnings,
        "tertiary_as_of": sales_as_of.isoformat(),
        "last_6m_start": six_month_start.isoformat(),
        "stock_as_of": stock_as_of.isoformat() if stock_as_of else None,
    }
