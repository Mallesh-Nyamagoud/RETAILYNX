"""Validate the committed SOH, secondary sales, and store master seeds.

Run from the repo root with:
    python backend/scripts/validate_soh_sources.py
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import duckdb

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "backend" / "data"
EXPECTED = {
    "soh_data_src.duckdb": ("data", {"date", "name", "brand", "code", "pc9", "correct_size", "qty", "season"}),
    "secondary_data_src.duckdb": ("data", {"bill_date", "customer_name", "brand_code", "season", "product_code_code", "qty"}),
    "store_master_src.duckdb": ("store_details", {"adonis_store_code", "retailer_name", "brand", "brand_code"}),
}


def main() -> int:
    issues = []
    con = duckdb.connect(":memory:")
    for alias, filename in (("soh", "soh_data_src.duckdb"), ("sales", "secondary_data_src.duckdb"), ("stores", "store_master_src.duckdb")):
        path = DATA / filename
        if not path.exists():
            issues.append(f"Missing {path}")
            continue
        con.execute(f"ATTACH '{path.as_posix()}' AS {alias} (READ_ONLY)")
        table, needed = EXPECTED[filename]
        columns = {r[0] for r in con.execute(f"DESCRIBE {alias}.{table}").fetchall()}
        missing = sorted(needed - columns)
        if missing:
            issues.append(f"{filename} missing columns: {missing}")

    if issues:
        print(json.dumps({"ok": False, "issues": issues}, indent=2))
        return 1

    snapshots = con.execute("""
        select cast(date as date) as snapshot_date, count(*) as row_count
        from soh.data group by 1 order by 1
    """).fetchall()
    key_match = con.execute(r"""
        with soh_keys as (
          select distinct upper(regexp_replace(trim(name), '\s+', '', 'g')) store,
            upper(regexp_replace(trim(code), '\s+', '', 'g')) brand_code,
            upper(regexp_replace(trim(pc9), '\s+', '', 'g')) style,
            upper(regexp_replace(trim(season), '\s+', '', 'g')) season
          from soh.data
        ), sales_keys as (
          select distinct upper(regexp_replace(trim(customer_name), '\s+', '', 'g')) store,
            upper(regexp_replace(trim(brand_code), '\s+', '', 'g')) brand_code,
            upper(regexp_replace(trim(product_code_code), '\s+', '', 'g')) style,
            upper(regexp_replace(trim(season), '\s+', '', 'g')) season
          from sales.data
        )
        select count(*) total, count(*) filter(where x.store is not null) matched
        from soh_keys s left join sales_keys x using(store, brand_code, style, season)
    """).fetchone()
    store_match = con.execute("""
        select count(distinct upper(trim(s.name))),
          count(distinct case when m.retailer_name is not null then upper(trim(s.name)) end),
          count(distinct case when x.customer_name is not null then upper(trim(s.name)) end)
        from soh.data s
        left join stores.store_details m on upper(trim(s.name))=upper(trim(m.retailer_name))
        left join (select distinct upper(trim(customer_name)) customer_name from sales.data) x
          on upper(trim(s.name))=x.customer_name
    """).fetchone()
    unmatched_sales_stores = [r[0] for r in con.execute("""
        select distinct s.name from soh.data s
        where not exists (select 1 from sales.data x
          where upper(trim(x.customer_name))=upper(trim(s.name)))
        order by 1
    """).fetchall()]
    missing_season_rows = con.execute("""
        select count(*) from sales.data where season is null or trim(season)=''
    """).fetchone()[0]
    result = {
        "ok": bool(snapshots),
        "field_mapping": {
            "soh.name": "secondary_data.customer_name",
            "soh.code": "secondary_data.brand_code",
            "soh.pc9": "secondary_data.product_code_code",
            "soh.season": "secondary_data.season",
        },
        "snapshots": [{"date": str(d), "rows": n} for d, n in snapshots],
        "distinct_soh_store_brand_style_season_keys": key_match[0],
        "keys_matching_secondary_sales": key_match[1],
        "key_match_rate_pct": round(100 * key_match[1] / key_match[0], 1) if key_match[0] else 0,
        "distinct_soh_stores": store_match[0],
        "stores_in_store_master": store_match[1],
        "stores_with_sales_source": store_match[2],
        "soh_stores_missing_from_sales": unmatched_sales_stores,
        "secondary_rows_missing_season": missing_season_rows,
        "notes": ["Sales matches are exact on normalized store, brand code, style, and season.",
                  "Store master coverage is reported separately; SOH sales matching does not depend on it.",
                  "Missing store or season coverage means a style may have no sales match."],
    }
    print(json.dumps(result, indent=2))
    return 0 if snapshots else 1


if __name__ == "__main__":
    sys.exit(main())
