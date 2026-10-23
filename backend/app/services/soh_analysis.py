from pathlib import Path
import duckdb
import pandas as pd
from app.core.config import BACKEND_DIR
from app.core.database import execute_df
SOH_DB = BACKEND_DIR / "data" / "soh_data_src.duckdb"
def get_dates():
    if not SOH_DB.exists(): return []
    with duckdb.connect(str(SOH_DB), read_only=True) as con:
        return [str(r[0])[:10] for r in con.execute("select distinct date from data order by date").fetchall()]
def get_summary(opening, ending, threshold=1.0):
    if not SOH_DB.exists(): return {"rows": [], "dates": [], "message": "SOH source is missing."}
    with duckdb.connect(str(SOH_DB), read_only=True) as con:
        df = con.execute("""select name as store, brand, gc as category, pc9 as style, season,
          sum(qty) filter(where cast(date as date)=cast(? as date)) opening_soh,
          sum(qty) filter(where cast(date as date)=cast(? as date)) ending_soh,
          string_agg(cast(correct_size as varchar)||'-'||cast(qty as varchar), ', ') filter(where cast(date as date)=cast(? as date)) end_soh_sizewise,
          max(mrp) mrp from data where cast(date as date) in(cast(? as date),cast(? as date)) group by all""",
          [opening,ending,ending,opening,ending]).df()
    if df.empty: return {"rows": [], "dates": get_dates()}
    df[["opening_soh","ending_soh"]]=df[["opening_soh","ending_soh"]].fillna(0)
    sales = execute_df("""
        select sm.retailer_name as store, sm.brand, b.product_code_code as style, b.season,
               sum(b.qty) filter(where cast(b.bill_date as date)>cast(? as date)) as sale,
               sum(b.qty) as total_sale
        from secondary_data.data b
        left join store_master.store_details sm
          on b.adonis_store_code=sm.adonis_store_code and b.brand_code=sm.brand_code
        where cast(b.bill_date as date)<=cast(? as date)
        group by all
    """, [opening, ending])
    if not sales.empty:
        sales["_style"] = sales["style"].astype(str).str.strip().str.upper()
        sales["_store"] = sales.store.astype(str).str.strip().str.upper()
        sales["_brand"] = sales.brand.astype(str).str.strip().str.upper()
        sales["_season"] = sales.season.astype(str).str.strip().str.upper()
        df["_style"] = df["style"].astype(str).str.strip().str.upper()
        df["_store"] = df.store.astype(str).str.strip().str.upper()
        df["_brand"] = df.brand.astype(str).str.strip().str.upper()
        df["_season"] = df.season.astype(str).str.strip().str.upper()
        sales = sales.groupby(["_store", "_brand", "_style", "_season"], as_index=False).sale.sum()
        df = df.merge(sales, on=["_store", "_brand", "_style", "_season"], how="left")
        df["sale"] = df["sale"].fillna(0)
        df["total_sale"] = df["total_sale"].fillna(0)
        df = df.drop(columns=["_style", "_store", "_brand", "_season"])
    else:
        df["sale"] = 0
        df["total_sale"] = 0
    # Reconcile the two snapshots with sales; this is estimated net transfer, not a transfer ledger.
    df["transferred_between"] = df.ending_soh - df.opening_soh + df.sale
    available_stock = df.opening_soh + df.sale
    df["st_pct"] = (df.sale / available_stock.replace(0, pd.NA)).fillna(0)
    df["opening_soh_clearance"] = (df.sale / df.opening_soh.replace(0, pd.NA)).fillna(0)
    return {"rows":df[df.st_pct<=threshold].fillna(0).to_dict("records"),"dates":get_dates()}
