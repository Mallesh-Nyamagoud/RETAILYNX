"""Category-level tertiary sales and latest SOH stock analysis."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import duckdb
import pandas as pd

from app.core.database import cache_token, execute, execute_df, quote_ident
from app.services import analysis, soh_analysis
from app.services.fy import safe_pct

SOH_DB = soh_analysis.SOH_DB
STORE_FILTER_COLUMNS = ("brand", "retailer_name", "store_status")
PRODUCT_FILTER_COLUMNS = ("category_group", "season")
PRODUCT_DIMENSION_COLUMNS = ("category_group", "subcategory", "season")
FILTER_COLUMNS = (*STORE_FILTER_COLUMNS, *PRODUCT_FILTER_COLUMNS)


def get_dimensions() -> list[dict]:
    """Expose tertiary product attributes and the Store Master row dimensions."""
    product_dimensions = [
        {"column": "category", "label": "Category", "type": "VARCHAR"},
        {"column": "category_group", "label": "Category Group", "type": "VARCHAR"},
        {"column": "subcategory", "label": "Subcategory", "type": "VARCHAR"},
        {"column": "season", "label": "Season", "type": "VARCHAR"},
    ]
    product_columns = {item["column"] for item in product_dimensions}
    return product_dimensions + [
        item for item in analysis.get_dimension_catalog()
        if item["column"] not in product_columns
    ]


def get_slicers() -> dict[str, list[str]]:
    available = analysis.get_slicer_options()
    result = {column: available.get(column, []) for column in STORE_FILTER_COLUMNS if column in available}
    result.update(_product_slicer_options(cache_token()))
    return result


@lru_cache(maxsize=4)
def _product_slicer_options(_token: tuple) -> dict[str, list[str]]:
    rows = execute_df("""
        SELECT DISTINCT TRIM(CAST("CG" AS VARCHAR)) AS category_group,
                        TRIM(CAST("SEASON" AS VARCHAR)) AS season
        FROM tertiary_data.data
        WHERE "CG" IS NOT NULL OR "SEASON" IS NOT NULL
    """)
    if rows.empty:
        return {"category_group": [], "season": []}
    return {
        column: sorted(rows[column].dropna().astype(str).loc[lambda values: values.str.len() > 0].unique().tolist())
        for column in PRODUCT_FILTER_COLUMNS
    }


def _norm(value) -> str:
    return re.sub(r"\s+", "", str(value or "")).upper()


def _filters_for_request(filters: dict[str, list[str]] | None) -> dict[str, list[str]]:
    selected = {}
    for column in FILTER_COLUMNS:
        values = (filters or {}).get(column) or []
        if values:
            selected[column] = [str(value) for value in values]
    return selected


def _map_stock_categories(stock: pd.DataFrame, category_map: pd.DataFrame) -> pd.DataFrame:
    """Keep SOH product fields; use tertiary history only to fill missing fields."""
    stock = stock.copy()
    category_map = category_map.copy()
    key_fields = (("store_code", "_store_key"), ("brand_code", "_brand_key"),
                  ("style", "_style_key"), ("season", "_season_key"))
    output_fields = ("category_group", "category", "subcategory")
    for frame in (stock, category_map):
        for source, normalized in key_fields:
            frame[normalized] = frame[source].map(_norm)
    for column in output_fields:
        if column not in stock:
            stock[column] = None
        if column not in category_map:
            category_map[column] = ""
        category_map[column] = category_map[column].fillna("").astype(str).str.strip()
        stock[column] = stock[column].map(
            lambda value: None if pd.isna(value) or not str(value).strip() else str(value).strip()
        )
    category_map = category_map[category_map["category"] != ""]
    for column in output_fields:
        stock[f"_mapped_{column}"] = stock[column]

    match_grains = (
        ("_store_key", "_brand_key", "_style_key", "_season_key"),
        ("_store_key", "_brand_key", "_style_key"),
        ("_brand_key", "_style_key", "_season_key"),
        ("_brand_key", "_style_key"),
    )
    for keys in match_grains:
        candidates = category_map[[*keys, *output_fields]].drop_duplicates()
        candidates = candidates[~candidates.duplicated(subset=list(keys), keep=False)]
        lookup = {
            tuple(row[key] for key in keys): tuple(row[column] for column in output_fields)
            for row in candidates.to_dict("records")
        }
        unresolved = stock[[f"_mapped_{column}" for column in output_fields]].isna().any(axis=1)
        indexes = stock.index[unresolved]
        mapped = [
            lookup.get(tuple(values))
            for values in stock.loc[indexes, list(keys)].itertuples(index=False, name=None)
        ]
        for offset, column in enumerate(output_fields):
            fill_indexes = indexes[stock.loc[indexes, f"_mapped_{column}"].isna()]
            stock.loc[fill_indexes, f"_mapped_{column}"] = [
                value[offset] if value else None
                for value, keep in zip(mapped, stock.loc[indexes, f"_mapped_{column}"].isna())
                if keep
            ]

    unmapped = stock["_mapped_category"].isna()
    unmapped_qty = float(stock.loc[unmapped, "current_stock"].sum())
    if unmapped_qty:
        stock.loc[unmapped, "_mapped_category"] = stock.loc[unmapped, "soh_category"].map(
            lambda value: "Unmapped SOH - " + (str(value).strip() if pd.notna(value) and str(value).strip() else "Unclassified")
        )
    for column in output_fields:
        stock[column] = stock[f"_mapped_{column}"]
    stock["_category_key"] = stock["category"].astype(str).str.strip().str.upper()
    return stock


def _find_source_column(columns: list[str], *candidates: str) -> str | None:
    normalized = {
        re.sub(r"[^a-z0-9]", "", column.lower()): column
        for column in columns
    }
    for candidate in candidates:
        match = normalized.get(re.sub(r"[^a-z0-9]", "", candidate.lower()))
        if match:
            return match
    return None


@lru_cache(maxsize=4)
def _latest_stock_categories_cached(token: tuple, soh_path: str, soh_mtime_ns: int, soh_size: int):
    """Prepare latest SOH rows once; filter changes reuse this expensive join."""
    del token, soh_mtime_ns, soh_size
    warnings: list[str] = []
    with duckdb.connect(soh_path, read_only=True) as con:
        columns = [row[0] for row in con.execute("DESCRIBE data").fetchall()]
        source = {
            "store": _find_source_column(columns, "name", "store", "store_name", "retailer_name", "retailer name"),
            "brand_code": _find_source_column(columns, "code", "brand_code"),
            "style": _find_source_column(columns, "pc9", "style", "style_code"),
            "season": _find_source_column(columns, "season", "season_name"),
            "category_group": _find_source_column(columns, "category_group", "category group", "categorygroup", "cg"),
            "category": _find_source_column(columns, "category"),
            "subcategory": _find_source_column(columns, "subcategory", "sub_category", "sub category"),
            "soh_category": _find_source_column(columns, "gc"),
            "qty": _find_source_column(columns, "qty", "quantity", "current_qty", "current_stock", "stock_qty"),
            "date": _find_source_column(columns, "date", "snapshot_date", "soh_date"),
        }
        required = ("store", "brand_code", "qty", "date")
        missing = [column for column in required if source[column] is None]
        if missing:
            raise ValueError(f"SOH source is missing required columns: {missing}")
        select_fields = [
            f"{quote_ident(source['store'])} AS store",
            f"{quote_ident(source['brand_code'])} AS brand_code",
            f"{quote_ident(source['style'])} AS style" if source["style"] else "NULL AS style",
            f"{quote_ident(source['season'])} AS season" if source["season"] else "NULL AS season",
        ]
        for field in ("category_group", "category", "subcategory"):
            expression = quote_ident(source[field]) if source[field] else "NULL"
            select_fields.append(f"{expression} AS {field}")
        soh_category_expr = quote_ident(source["soh_category"]) if source["soh_category"] else "NULL"
        select_fields.append(f"{soh_category_expr} AS soh_category")
        select_fields.append(f"SUM({quote_ident(source['qty'])}) AS current_stock")
        stock_as_of = con.execute(
            f"SELECT MAX(CAST({quote_ident(source['date'])} AS DATE)) FROM data"
        ).fetchone()[0]
        stock = con.execute(f"""
            SELECT {", ".join(select_fields)}
            FROM data
            WHERE CAST({quote_ident(source['date'])} AS DATE) = (
                SELECT MAX(CAST({quote_ident(source['date'])} AS DATE)) FROM data
            )
            GROUP BY ALL
        """).df()
    if stock.empty:
        return stock, stock_as_of, ()
    stock = soh_analysis._store_code_lookup(stock, warnings)
    if stock[["category_group", "category", "subcategory"]].isna().any().any():
        category_map = execute_df("""
            SELECT adonis_store_code AS store_code, brand_code,
                   "Style_Code" AS style, "SEASON" AS season,
                   "CG" AS category_group, category, sub_category AS subcategory
            FROM tertiary_data.data
            WHERE category IS NOT NULL
            GROUP BY ALL
        """)
        stock = _map_stock_categories(stock, category_map)
    unmapped_qty = float(stock.loc[stock["category"].str.startswith("Unmapped SOH -"), "current_stock"].sum())
    if unmapped_qty:
        warnings.append(f"{unmapped_qty:,.0f} units from the latest SOH snapshot had no tertiary style match; they are listed by SOH category.")
    return stock, stock_as_of, tuple(warnings)


def _latest_stock_categories():
    stat = Path(SOH_DB).stat()
    stock, stock_as_of, warnings = _latest_stock_categories_cached(
        cache_token(), str(SOH_DB), stat.st_mtime_ns, stat.st_size,
    )
    return stock.copy(), stock_as_of, warnings


def run_analysis(hierarchy: list[str] | None, filters: dict[str, list[str]] | None) -> dict:
    hierarchy = list(hierarchy or [])
    valid_dimensions = {item["column"] for item in get_dimensions()}
    invalid = [column for column in hierarchy if column not in valid_dimensions]
    if invalid:
        raise ValueError(f"Unknown row dimension(s): {invalid}")
    row_dimensions = [column for column in hierarchy if column != "category"]
    selected_filters = _filters_for_request(filters)
    store_filters = {column: selected_filters[column] for column in STORE_FILTER_COLUMNS if column in selected_filters}
    filter_sql, filter_params = analysis._build_filter_sql(store_filters)
    product_filter_sql = []
    product_filter_params = []
    if selected_filters.get("category_group"):
        values = selected_filters["category_group"]
        product_filter_sql.append(f' AND TRIM(CAST(f."CG" AS VARCHAR)) IN ({",".join(["?"] * len(values))})')
        product_filter_params.extend(values)
    if selected_filters.get("season"):
        values = selected_filters["season"]
        product_filter_sql.append(f' AND TRIM(CAST(f."SEASON" AS VARCHAR)) IN ({",".join(["?"] * len(values))})')
        product_filter_params.extend(values)
    filter_sql += "".join(product_filter_sql)

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

    source_dimensions = {
        "category_group": 'TRIM(CAST(f."CG" AS VARCHAR)) AS "category_group"',
        "subcategory": 'TRIM(CAST(f.sub_category AS VARCHAR)) AS "subcategory"',
        "season": 'TRIM(CAST(f."SEASON" AS VARCHAR)) AS "season"',
    }
    dim_select = ", ".join(
        source_dimensions[column] if column in source_dimensions
        else f"dim.{quote_ident(column)} AS {quote_ident(column)}"
        for column in row_dimensions
    )
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
    """, [six_month_start, sales_as_of, *filter_params, *product_filter_params])
    if sales_rows.empty:
        return {"rows": [], "warnings": [], "tertiary_as_of": sales_as_of.isoformat(), "last_6m_start": six_month_start.isoformat(), "stock_as_of": None}

    warnings: list[str] = []
    if not SOH_DB.exists():
        sales_rows["current_stock"] = 0.0
        warnings.append("SOH source is missing; current stock is shown as 0.")
        combined = sales_rows
        stock_as_of = None
    else:
        stock, stock_as_of, stock_warnings = _latest_stock_categories()
        warnings.extend(stock_warnings)
        if stock.empty:
            sales_rows["current_stock"] = 0.0
            warnings.append("No rows were found in the latest SOH snapshot; current stock is shown as 0.")
            combined = sales_rows
        else:
            master_dimensions = list(dict.fromkeys([
                *[column for column in row_dimensions if column not in PRODUCT_DIMENSION_COLUMNS],
                *STORE_FILTER_COLUMNS,
            ]))
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
            group_keys = ["_category_key", *row_dimensions]
            stock_rows = stock.groupby(group_keys, dropna=False, as_index=False).agg(
                current_stock=("current_stock", "sum"),
                category_stock=("category", "first"),
            )
            combined = sales_rows.merge(stock_rows, on=group_keys, how="outer")
            combined["category"] = combined["category"].fillna(combined["category_stock"])
            combined = combined.drop(columns=["category_stock"])
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
