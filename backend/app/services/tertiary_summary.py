from __future__ import annotations
from functools import lru_cache
import calendar
from app.core.database import cache_token, execute, execute_df, quote_ident
from app.services.analysis import _build_filter_sql
FACT = "tertiary_data.data"
CANDIDATES = {"store": ("adonis_store_code",), "department": ("department",), "store_status": ("store_status",), "store_type": ("store_type",), "brand": ("brand_code",), "state": ("state", "state_name"), "group": ("group", "store_group")}
def _fields():
    cols = {r[0] for r in execute("SELECT column_name FROM information_schema.columns WHERE table_catalog='store_master' AND table_name='store_details'")}
    return {k: next((v for v in vs if v in cols), None) for k, vs in CANDIDATES.items() if any(v in cols for v in vs)}
def config(): return _config_cached(cache_token())
@lru_cache(maxsize=4)
def _config_cached(_token):
    fields = _fields(); options = {}
    for key, col in fields.items():
        q = quote_ident(col); options[key] = [r[0] for r in execute(f"SELECT DISTINCT {q} FROM store_master.store_details WHERE {q} IS NOT NULL ORDER BY 1")]
    starts = [r[0] for r in execute(f"SELECT DISTINCT CASE WHEN month(date)>=4 THEN year(date) ELSE year(date)-1 END::INTEGER FROM {FACT} WHERE date IS NOT NULL ORDER BY 1")]
    return {"fields": fields, "options": options, "years": starts, "months": [{"value": i, "label": calendar.month_name[i]} for i in range(1,13)]}
def report(row_dimension, filters=None):
    cfg = config(); fields = cfg["fields"]
    if row_dimension not in fields: raise ValueError(f"Unavailable row dimension: {row_dimension}")
    filters = filters or {}; dim_filters = {fields[k]: v for k,v in filters.items() if k in fields and v}
    filter_sql, params = _build_filter_sql(dim_filters); clauses = ["1=1" + filter_sql]
    if filters.get("fy"):
        ys = [int(v) for v in filters["fy"]]; clauses.append("(CASE WHEN month(f.date)>=4 THEN year(f.date) ELSE year(f.date)-1 END) IN (" + ",".join("?" for _ in ys) + ")"); params.extend(ys)
    if filters.get("month"):
        ms = [int(v) for v in filters["month"]]; clauses.append("month(f.date) IN (" + ",".join("?" for _ in ms) + ")"); params.extend(ms)
    col = fields[row_dimension]
    sql = f"SELECT dim.{quote_ident(col)} AS label, CASE WHEN month(f.date)>=4 THEN year(f.date) ELSE year(f.date)-1 END AS fy_start, SUM(COALESCE(f.qty,0)) AS qty, SUM(COALESCE(f.bill_val,0)) AS val FROM {FACT} f LEFT JOIN store_master.store_details dim ON f.adonis_store_code=dim.adonis_store_code AND f.brand_code=dim.brand_code WHERE {' AND '.join(clauses)} GROUP BY 1,2 ORDER BY 1"
    df = execute_df(sql, params); years = cfg["years"]
    if df.empty: return {"years": years, "rows": [], "totals": {}}
    df["label"] = df["label"].fillna("Unassigned").astype(str); rows=[]
    for label, sub in df.groupby("label", sort=True): rows.append({"label":label,"years":{str(y):{"qty":float(sub.loc[sub.fy_start==y,"qty"].sum()),"val":float(sub.loc[sub.fy_start==y,"val"].sum())} for y in years}})
    totals={str(y):{"qty":float(df.loc[df.fy_start==y,"qty"].sum()),"val":float(df.loc[df.fy_start==y,"val"].sum())} for y in years}
    return {"years":years,"rows":rows,"totals":totals}
