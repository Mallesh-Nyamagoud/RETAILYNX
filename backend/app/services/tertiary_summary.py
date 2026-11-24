from __future__ import annotations
from functools import lru_cache
import calendar
from datetime import date
from app.core.database import cache_token, execute, execute_df, filter_key, quote_ident
from app.services.analysis import _build_filter_sql
FACT = "tertiary_data.data"
JOIN = "LEFT JOIN store_master.store_details dim ON f.adonis_store_code=dim.adonis_store_code AND f.brand_code=dim.brand_code"
CANDIDATES = {"store": ("retailer_name", "adonis_store_code"), "department": ("department",), "store_status": ("store_status",), "store_type": ("store_type",), "brand": ("brand", "brand_code"), "state": ("state", "state_name"), "group": ("group", "store_group")}


def _fields():
    cols = {r[0] for r in execute("SELECT column_name FROM information_schema.columns WHERE table_catalog='store_master' AND table_name='store_details'")}
    return {k: next(v for v in vs if v in cols) for k,vs in CANDIDATES.items() if any(v in cols for v in vs)}
def config(filters=None):
    return _config_cached(filter_key(filters), cache_token())
@lru_cache(maxsize=64)
def _config_cached(filters_key, _token):
    filters = {k:list(v) for k,v in filters_key}
    fields = _fields(); options = {}
    for key,col in fields.items():
        other = {fields[k]:v for k,v in filters.items() if k in fields and k != key and v}
        where,params = _build_filter_sql(other); q=quote_ident(col)
        clauses = [f"dim.{q} IS NOT NULL"]
        if where: clauses.append(where.removeprefix(" AND "))
        months = [int(v) for v in filters.get("month", []) if str(v).isdigit()]
        if months:
            clauses.append("month(f.date) IN (" + ",".join("?" for _ in months) + ")"); params.extend(months)
        fys = [int(v) for v in filters.get("fy", []) if str(v).isdigit()]
        if fys:
            clauses.append("(CASE WHEN month(f.date)>=4 THEN year(f.date) ELSE year(f.date)-1 END) IN (" + ",".join("?" for _ in fys) + ")"); params.extend(fys)
        options[key] = [str(r[0]) for r in execute(f"SELECT DISTINCT dim.{q} FROM {FACT} f {JOIN} WHERE {' AND '.join(clauses)} ORDER BY 1",params)]
    dim_filters = {fields[k]:v for k,v in filters.items() if k in fields and v}
    dim_where,dim_params = _build_filter_sql(dim_filters)
    year_clauses = ["f.date IS NOT NULL"]
    if dim_where: year_clauses.append(dim_where.removeprefix(" AND "))
    selected_months = [int(v) for v in filters.get("month", []) if str(v).isdigit()]
    if selected_months:
        year_clauses.append("month(f.date) IN (" + ",".join("?" for _ in selected_months) + ")")
    year_options = [r[0] for r in execute(f"SELECT DISTINCT CASE WHEN month(f.date)>=4 THEN year(f.date) ELSE year(f.date)-1 END::INTEGER FROM {FACT} f {JOIN} WHERE {' AND '.join(year_clauses)} ORDER BY 1", dim_params + selected_months)]
    years = [r[0] for r in execute(f"SELECT DISTINCT CASE WHEN month(date)>=4 THEN year(date) ELSE year(date)-1 END::INTEGER FROM {FACT} WHERE date IS NOT NULL ORDER BY 1")]
    month_clauses = ["f.date IS NOT NULL"]
    if dim_where: month_clauses.append(dim_where.removeprefix(" AND "))
    selected_years = [int(v) for v in filters.get("fy", []) if str(v).isdigit()]
    if selected_years:
        month_clauses.append("(CASE WHEN month(f.date)>=4 THEN year(f.date) ELSE year(f.date)-1 END) IN (" + ",".join("?" for _ in selected_years) + ")")
    month_nums = [r[0] for r in execute(f"SELECT DISTINCT month(f.date)::INTEGER FROM {FACT} f {JOIN} WHERE {' AND '.join(month_clauses)} ORDER BY 1", dim_params + selected_years)]
    months = [{"value":i,"label":calendar.month_name[i]} for i in month_nums]
    latest = execute(f"SELECT MAX(date) FROM {FACT}")[0][0]
    current_fy = (latest.year if latest.month >= 4 else latest.year - 1) if latest else None
    current_fy_partial = bool(latest and current_fy is not None and latest < date(current_fy + 1, 3, 31))
    return {"fields":fields,"options":options,"years":years,"year_options":year_options,"months":months,"current_fy":current_fy,"current_fy_partial":current_fy_partial}
def _anchor_and_months(filters, years):
    chosen = [int(v) for v in filters.get("fy",[]) if str(v).isdigit()]
    anchor = max(chosen) if chosen else (max(years) if years else None)
    months = [int(v) for v in filters.get("month",[]) if str(v).isdigit()]
    if months:
        # A month selection defines the same selected calendar months for each FY; LFYTD reaches the latest selected month.
        cutoff = max(months, key=lambda m: (m-4)%12)
        lfytd_months = [m for m in range(1,13) if (m-4)%12 <= (cutoff-4)%12]
    else:
        month_row = execute(f"SELECT MAX(month(date)) FROM {FACT} WHERE (CASE WHEN month(date)>=4 THEN year(date) ELSE year(date)-1 END)=?", [anchor]) if anchor is not None else [(3,)]
        cutoff = month_row[0][0] or 3
        lfytd_months = [m for m in range(1,13) if (m-4)%12 <= (cutoff-4)%12]
    return anchor, months, lfytd_months
def report(row_dimension, filters=None):
    if row_dimension == "store_brand_rank":
        return store_brand_rank(filters or {})
    return _report_cached(row_dimension, filter_key(filters), cache_token())
@lru_cache(maxsize=64)
def _report_cached(row_dimension, filters_key, _token):
    filters = {k:list(v) for k,v in filters_key}
    filters = filters or {}; fields=_fields()
    if row_dimension not in fields: raise ValueError(f"Unavailable row dimension: {row_dimension}")
    cfg=config(filters); years=cfg["years"]; anchor,months,lfytd_months=_anchor_and_months(filters,years)
    dimfilters={fields[k]:v for k,v in filters.items() if k in fields and v}; where,params=_build_filter_sql(dimfilters); clauses=["1=1"+where]

    label=quote_ident(fields[row_dimension]); month_in=",".join(str(m) for m in lfytd_months) or "0"
    month_cond=(",".join(str(m) for m in months) if months else "")
    def annual_sum(column):
        value = f"COALESCE(f.{quote_ident(column)},0)"
        return f"SUM(CASE WHEN month(f.date) IN ({month_cond}) THEN {value} ELSE 0 END)" if month_cond else f"SUM({value})"

    def ytd_sum(column):
        return f"SUM(CASE WHEN month(f.date) IN ({month_in}) THEN COALESCE(f.{quote_ident(column)},0) ELSE 0 END)"

    sql=f"""
    SELECT dim.{label} AS label,
      CASE WHEN month(f.date)>=4 THEN year(f.date) ELSE year(f.date)-1 END AS fy_start,
      {annual_sum('qty')} AS qty,
      {annual_sum('bill_val')} AS val,
      {annual_sum('mrp_value')} AS mrp_value,
      {annual_sum('discount')} AS discount,
      {ytd_sum('qty')} AS ytd_qty,
      {ytd_sum('bill_val')} AS ytd_val,
      {ytd_sum('mrp_value')} AS ytd_mrp_value,
      {ytd_sum('discount')} AS ytd_discount
    FROM {FACT} f {JOIN} WHERE {' AND '.join(clauses)}
    GROUP BY 1,2 ORDER BY 1
    """
    df=execute_df(sql,params)
    if df.empty: return {"years":years,"anchor":anchor,"current_fy":cfg["current_fy"],"current_fy_partial":cfg["current_fy_partial"],"rows":[],"totals":{}}
    df["label"]=df["label"].fillna("Unassigned").astype(str); rows=[]

    def metric_values(frame, prefix=""):
        qty = float(frame[f"{prefix}qty"].sum())
        val = float(frame[f"{prefix}val"].sum())
        mrp_value = float(frame[f"{prefix}mrp_value"].sum())
        discount = float(frame[f"{prefix}discount"].sum())
        return {
            "qty": qty,
            "val": val,
            "mrp_value": mrp_value,
            "discount": discount,
            "discount_outflow": (discount / mrp_value * 100) if mrp_value else None,
        }

    for name,sub in df.groupby("label",sort=True):
        by_year={}
        for y in years:
            cur=sub[sub.fy_start==y]
            full=metric_values(cur)
            ytd=metric_values(cur, "ytd_")
            by_year[str(y)]={**full, **{"lfytd_" + key: value for key, value in ytd.items()}}
        rows.append({"label":name,"years":by_year})
    totals={}
    for y in years:
        cur=df[df.fy_start==y]
        full=metric_values(cur)
        ytd=metric_values(cur, "ytd_")
        totals[str(y)]={**full, **{"lfytd_" + key: value for key, value in ytd.items()}}
    return {"years":years,"anchor":anchor,"current_fy":cfg["current_fy"],"current_fy_partial":cfg["current_fy_partial"],"rows":rows,"totals":totals}


def store_brand_rank(filters):
    cfg = config(filters)
    if not {"store", "brand"}.issubset(cfg["fields"]):
        raise ValueError("Store and brand fields are required")
    brands = [b for b in cfg["options"].get("brand", []) if not filters.get("brand") or b in filters["brand"]]
    stores = {}; totals = {}; anchor = None; partial = False
    for brand in brands:
        result = report("store", {**filters, "brand": [brand]})
        full_result = report("store", {**filters, "brand": [brand], "month": []}) if filters.get("month") else result
        full_rows = {row["label"]: row for row in full_result["rows"]}
        anchor = result["anchor"]
        partial = result["current_fy_partial"] and anchor == result["current_fy"]
        previous_key = "lfytd_val" if partial else "val"
        totals[brand] = {"current": result["totals"].get(str(anchor), {}).get("val", 0),
                         "previous": result["totals"].get(str(anchor-1), {}).get(previous_key, 0)} if anchor else {"current":0,"previous":0}
        totals[brand]["full"] = full_result["totals"].get(str(anchor-1), {}).get("val", 0) if anchor else 0
        for row in result["rows"]:
            current = row["years"].get(str(anchor), {}).get("val", 0)
            previous = row["years"].get(str(anchor-1), {}).get(previous_key, 0) if anchor else 0
            stores.setdefault(row["label"], {})[brand] = {"current": current, "previous": previous,
                "full": full_rows.get(row["label"], {}).get("years", {}).get(str(anchor-1), {}).get("val", 0) if anchor else 0}
    rows = []
    periods = ("current", "previous", "full")
    overall_totals = {key: sum(values[key] for values in totals.values()) for key in periods}
    overall = overall_totals["current"]
    brands.sort(key=lambda brand: (-totals[brand]["current"], brand))
    for name, cells in stores.items():
        store_totals = {key: sum(cell[key] for cell in cells.values()) for key in periods}
        ranked = sorted(cells.values(), key=lambda cell: cell["current"], reverse=True)
        last = None
        for index, cell in enumerate(ranked):
            if cell["current"] != last:
                rank = index + 1
                last = cell["current"]
            cell["rank"] = rank
            for key in periods:
                cell[key + "_cont"] = cell[key] / store_totals[key] * 100 if store_totals[key] else None
        rows.append({"label": name, "cells": cells, "totals": store_totals,
                     "contribution": store_totals["current"] / overall * 100 if overall else None,
                     "contributions": {key: store_totals[key] / overall_totals[key] * 100 if overall_totals[key] else None for key in periods}})
    rows.sort(key=lambda row: (-row["totals"]["current"], row["label"]))
    return {"anchor": anchor, "partial": partial, "brands": brands, "totals": totals, "overall_totals": overall_totals, "rows": rows}
