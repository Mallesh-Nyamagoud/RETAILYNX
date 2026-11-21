"""Top bills aggregated from matching transaction lines, across selected dates."""
from __future__ import annotations

import pandas as pd
from app.core.database import column_exists, execute_df, quote_ident
from app.services.analysis import FactSpec, get_dimension_catalog
from app.services.bill_analysis import _FY_LABEL_SQL, _iso_date


def run_top_bills(fact: FactSpec, filters: dict, n: int, date_range: dict | None = None) -> dict:
    dims = {d["column"] for d in get_dimension_catalog()}
    # Store master is unique at store + brand grain; defensive deduplication
    # prevents duplicate dimension records from multiplying sales values.
    attrs = sorted(dims - {"brand", "adonis_store_code", "brand_code"})
    extra = "".join(f", dim.{quote_ident(col)}" for col in attrs)
    fact_name = f"f.{quote_ident('brand')}" if column_exists(fact.schema, fact.table, "brand") else "NULL"
    brand_name = f"COALESCE(NULLIF(TRIM(dim.brand), ''), NULLIF(TRIM(CAST({fact_name} AS VARCHAR)), ''), CAST(f.{quote_ident(fact.brand_column)} AS VARCHAR))"
    allowed = dims | {"brand", "brand_code", "adonis_store_code", "month_num", "fy_label", "month"}
    clauses, params = [], []
    for col, values in filters.items():
        if col not in allowed:
            raise ValueError(f"Unknown filter column: {col}")
        if not values:
            continue
        expr = quote_ident(col)
        if col == "month":
            expr = "strftime(tx_date, '%b')"
        clauses.append(f"CAST({expr} AS VARCHAR) IN ({','.join('?' for _ in values)})")
        params.extend(str(value) for value in values)
    for key, op in (("start", ">="), ("end", "<=")):
        if date_range and date_range.get(key):
            value = pd.to_datetime(date_range[key], errors="raise").date().isoformat()
            clauses.append(f"CAST(tx_date AS DATE) {op} CAST(? AS DATE)")
            params.append(value)
    where = " AND ".join(clauses) or "TRUE"
    retailer = 'MAX(CAST(retailer_name AS VARCHAR))' if "retailer_name" in dims else "NULL::VARCHAR"
    sql = f"""
    WITH dim AS (
        SELECT * FROM store_master.store_details
        QUALIFY ROW_NUMBER() OVER (PARTITION BY adonis_store_code, brand_code ORDER BY brand) = 1
    ), source AS (
        SELECT f.{quote_ident(fact.date_column)} AS tx_date,
               COALESCE(CAST(f.{quote_ident(fact.store_column)} AS VARCHAR), '(no store)') AS adonis_store_code,
               CAST(f.{quote_ident(fact.brand_column)} AS VARCHAR) AS brand_code,
               TRIM(CAST(f.bill_no AS VARCHAR)) AS bill_no,
               {fact.qty_expr} AS qty, {fact.val_expr} AS bill_val,
               {brand_name} AS brand {extra}
        FROM {quote_ident(fact.schema)}.{quote_ident(fact.table)} f
        LEFT JOIN dim ON f.{quote_ident(fact.store_column)} = dim.adonis_store_code
                    AND f.{quote_ident(fact.brand_column)} = dim.brand_code
        WHERE f.bill_no IS NOT NULL AND TRIM(CAST(f.bill_no AS VARCHAR)) <> ''
          AND UPPER(TRIM(CAST(f.bill_no AS VARCHAR))) NOT IN ('NA', 'N/A')
          AND f.{quote_ident(fact.date_column)} IS NOT NULL
    ), dated AS (
        SELECT *, {_FY_LABEL_SQL} AS fy_label,
               EXTRACT(MONTH FROM tx_date)::INTEGER AS month_num,
               adonis_store_code || '-FY' || RIGHT(CAST(CASE WHEN EXTRACT(MONTH FROM tx_date) >= 4
                   THEN EXTRACT(YEAR FROM tx_date) ELSE EXTRACT(YEAR FROM tx_date) - 1 END AS VARCHAR), 2)
                 || '-' || LPAD(EXTRACT(MONTH FROM tx_date)::INTEGER::VARCHAR, 2, '0') || '-' || bill_no AS internal_bill_id
        FROM source
    ), parts AS (
        SELECT internal_bill_id, brand, MIN(CAST(tx_date AS DATE)) AS bill_date,
               MAX(adonis_store_code) AS adonis_store_code, {retailer} AS retailer_name,
               COALESCE(SUM(qty), 0) AS qty, COALESCE(SUM(bill_val), 0) AS bill_val
        FROM dated WHERE {where}
        GROUP BY internal_bill_id, brand
    ), bills AS (
        SELECT internal_bill_id, SUM(qty) AS total_qty, SUM(bill_val) AS total_val,
               MIN(bill_date) AS first_date
        FROM parts GROUP BY internal_bill_id
    ), ranked AS (
        SELECT *, ROW_NUMBER() OVER (ORDER BY total_val DESC NULLS LAST, first_date, internal_bill_id) AS rank,
               COUNT(*) OVER () AS bill_count
        FROM bills
    )
    SELECT p.*, r.total_qty, r.total_val, r.first_date, r.rank, r.bill_count
    FROM ranked r JOIN parts p USING (internal_bill_id)
    WHERE r.rank <= ? ORDER BY r.rank, p.bill_val DESC NULLS LAST, p.brand
    """
    fine = execute_df(sql, [*params, n])
    rows = []
    for bid, sub in fine.groupby("internal_bill_id", sort=False):
        first = sub.iloc[0]
        total = float(first.total_val or 0)
        parts = [{"brand": None if pd.isna(r.brand) else str(r.brand),
                  "bill_val": float(r.bill_val or 0),
                  "contribution_pct": float(r.bill_val or 0) / total * 100 if total else 0.0}
                 for r in sub.itertuples()]
        rows.append({"rank": int(first["rank"]), "internal_bill_id": str(bid),
                     "bill_date": _iso_date(first.first_date),
                     "month": pd.Timestamp(first.first_date).strftime("%b"),
                     "adonis_store_code": str(first.adonis_store_code),
                     "retailer_name": None if pd.isna(first.retailer_name) else str(first.retailer_name),
                     "brand": parts[0]["brand"], "qty": float(first.total_qty or 0),
                     "bill_val": total, "brand_contributions": parts})
    return {"dimension": [], "date_range": date_range, "window_meta": {"mode": "selected-data"},
            "top_bills": {"n": n, "overall": rows, "cfy": [], "lfy": [],
                          "scope_label": "Selected data" if any(filters.values()) or date_range else "All available data"},
            "meta": {"bill_count": int(fine.iloc[0].bill_count) if not fine.empty else 0}}
