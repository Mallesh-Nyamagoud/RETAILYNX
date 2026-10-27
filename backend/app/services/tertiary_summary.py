from __future__ import annotations
from functools import lru_cache
import calendar
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
    return {"fields":fields,"options":options,"years":years,"year_options":year_options,"months":months}
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
    annual_qty=(f"SUM(CASE WHEN month(f.date) IN ({month_cond}) THEN COALESCE(f.qty,0) ELSE 0 END)" if month_cond else "SUM(COALESCE(f.qty,0))")
    annual_val=(f"SUM(CASE WHEN month(f.date) IN ({month_cond}) THEN COALESCE(f.bill_val,0) ELSE 0 END)" if month_cond else "SUM(COALESCE(f.bill_val,0))")
    sql=f"""
    SELECT dim.{label} AS label,
      CASE WHEN month(f.date)>=4 THEN year(f.date) ELSE year(f.date)-1 END AS fy_start,
      {annual_qty} AS qty, {annual_val} AS val,
      SUM(CASE WHEN month(f.date) IN ({month_in}) THEN COALESCE(f.qty,0) ELSE 0 END) AS ytd_qty,
      SUM(CASE WHEN month(f.date) IN ({month_in}) THEN COALESCE(f.bill_val,0) ELSE 0 END) AS ytd_val
    FROM {FACT} f {JOIN} WHERE {' AND '.join(clauses)}
    GROUP BY 1,2 ORDER BY 1
    """
    df=execute_df(sql,params)
    if df.empty: return {"years":years,"anchor":anchor,"rows":[],"totals":{}}
    df["label"]=df["label"].fillna("Unassigned").astype(str); rows=[]
    for name,sub in df.groupby("label",sort=True):
        by_year={}
        for y in years:
            cur=sub[sub.fy_start==y]; prev=sub[sub.fy_start==y-1]
            by_year[str(y)]={"qty":float(cur.qty.sum()),"val":float(cur.val.sum()),"lfytd_qty":float(prev.ytd_qty.sum()),"lfytd_val":float(prev.ytd_val.sum())}
        rows.append({"label":name,"years":by_year})
    totals={}
    for y in years:
        cur=df[df.fy_start==y]; prev=df[df.fy_start==y-1]
        totals[str(y)]={"qty":float(cur.qty.sum()),"val":float(cur.val.sum()),"lfytd_qty":float(prev.ytd_qty.sum()),"lfytd_val":float(prev.ytd_val.sum())}
    return {"years":years,"anchor":anchor,"rows":rows,"totals":totals}
