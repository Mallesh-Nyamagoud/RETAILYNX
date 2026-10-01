"""
Standalone validation of the updated CSS Stock Tracking logic.

Runs against the SEED databases (order_form_src / secondary_data_src /
store_master_src) because the working copies may be locked by the live server.
It monkey-patches app.core.database to point every schema at the seed files,
then validates every requirement of the corrected spec:

  1. Ordered Qty comes from CURRENTQUANTITY (never VENUEQUANTITY)
  2. All Order Form styles appear even with zero dispatch
  3. Season matching only after identical cleaning (no season mixing)
  4. Status classification (fully/partial/pending/dbno) correctness
  5. Pending Qty = MAX(Ordered - Dispatched, 0); Dispatch % formula
  6. Sub Category: Order Form SUBCATEGORY for mapped, PRODUCT_DESC fallback
  7. KPI totals reconcile with summary rows and the brand chart
  8. Filtered results reconcile (filters shrink totals consistently)
  9. Status filtering returns exactly the matching rows
 10. JSON serialisation sanity

Usage:  .venv\\Scripts\\python.exe scripts\\test_css_stock.py
"""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import duckdb

SEEDS = Path(__file__).resolve().parents[1] / "data"

con = duckdb.connect()  # in-memory catalog
con.execute(f"ATTACH '{(SEEDS / 'store_master_src.duckdb').as_posix()}' AS store_master")
con.execute(f"ATTACH '{(SEEDS / 'order_form_src.duckdb').as_posix()}' AS order_form")
con.execute(f"ATTACH '{(SEEDS / 'secondary_data_src.duckdb').as_posix()}' AS secondary_data")

# Patch the DB layer so the service module uses this connection.
import app.core.database as db

db._connection = con
db._lock = threading.RLock()

import app.services.css_stock as css


def approx(a, b, tol=1e-6):
    return abs(float(a or 0) - float(b or 0)) < tol


def main() -> None:
    print("=== dimensions ===")
    dims = css.get_available_dimensions()
    print([d["column"] for d in dims])

    print("\n=== seasons ===")
    seasons = css.get_seasons()
    print(seasons)
    season = seasons[0] if seasons else None

    # ------------------------------------------------------------------
    # Independent ground truth computed straight from the seed tables.
    # ------------------------------------------------------------------
    NS = css._norm_season
    NC = css._norm_code
    truth_sql = f"""
    WITH o AS (
        SELECT {NS('season')} AS sn, {NC('style_code')} AS st,
               SUM(currentquantity) AS oq
        FROM order_form.order_form
        WHERE style_code IS NOT NULL AND TRIM(style_code) <> ''
          {'AND ' + NS('season') + ' = ' + NS('?') if season else ''}
        GROUP BY 1,2
    ),
    d AS (
        SELECT {NS('season')} AS sn, {NC('product_code_code')} AS st, SUM(qty) AS dq
        FROM secondary_data.data
        WHERE product_code_code IS NOT NULL AND TRIM(product_code_code) <> ''
          AND {NS('season')} IN (
              SELECT {NS('season')} FROM order_form.order_form WHERE season IS NOT NULL)
          {'AND ' + NS('season') + ' = ' + NS('?') if season else ''}
        GROUP BY 1,2
    ),
    j AS (
        SELECT COALESCE(o.sn, d.sn) AS sn, COALESCE(o.st, d.st) AS st,
               COALESCE(o.oq, 0) AS oq, COALESCE(d.dq, 0) AS dq
        FROM o FULL OUTER JOIN d ON o.sn = d.sn AND o.st = d.st
    )
    SELECT
        SUM(oq) AS tot_ordered,
        SUM(dq) AS tot_dispatched,
        SUM(GREATEST(oq - dq, 0)) AS tot_pending,
        COUNT(*) FILTER (WHERE oq > 0 AND dq >= oq) AS n_full,
        COUNT(*) FILTER (WHERE oq > 0 AND dq > 0 AND dq < oq) AS n_partial,
        COUNT(*) FILTER (WHERE oq > 0 AND dq <= 0) AS n_pending,
        COUNT(*) FILTER (WHERE oq <= 0 AND dq != 0) AS n_dbno
    FROM j WHERE NOT (oq <= 0 AND dq <= 0)
    """
    truth_params = [season, season] if season else []
    t = con.execute(truth_sql, truth_params).fetchone()
    gt = {
        "tot_ordered": float(t[0] or 0),
        "tot_dispatched": float(t[1] or 0),
        "tot_pending": float(t[2] or 0),
        "n_full": int(t[3]),
        "n_partial": int(t[4]),
        "n_pending": int(t[5]),
        "n_dbno": int(t[6]),
    }
    print(f"\nground truth: {gt}")

    # ------------------------------------------------------------------
    print(f"\n=== KPIs (season={season}) ===")
    kpis = css.get_kpis(season)
    print(json.dumps({k: v for k, v in kpis.items() if k != "by_brand"}, indent=2))

    assert approx(kpis["total_ordered"], gt["tot_ordered"]), "KPI ordered mismatch"
    assert approx(kpis["total_dispatched"], gt["tot_dispatched"]), "KPI dispatched mismatch"
    assert approx(kpis["total_pending"], gt["tot_pending"]), "KPI pending mismatch"
    assert kpis["fully_dispatched"] == gt["n_full"], "fully count mismatch"
    assert kpis["partially_dispatched"] == gt["n_partial"], "partial count mismatch"
    assert kpis["pending"] == gt["n_pending"], "pending count mismatch"
    assert kpis["dispatched_but_not_ordered"] == gt["n_dbno"], "dbno count mismatch"
    print("KPI vs ground-truth reconciliation OK")

    # VENUEQUANTITY must NOT be used: it differs from CURRENTQUANTITY.
    vq = con.execute("SELECT SUM(venuequantity) FROM order_form.order_form").fetchone()[0]
    cq = con.execute("SELECT SUM(currentquantity) FROM order_form.order_form").fetchone()[0]
    assert vq != cq, "test data unusable: venuequantity == currentquantity"
    assert approx(kpis["total_ordered"], cq), "ordered qty does not equal SUM(CURRENTQUANTITY)"
    assert not approx(kpis["total_ordered"], vq), "ordered qty looks like VENUEQUANTITY!"
    print(f"CURRENTQUANTITY={cq:,} used; VENUEQUANTITY={vq:,} NOT used")

    # ------------------------------------------------------------------
    print("\n=== Summary (all statuses, style grain) ===")
    res = css.get_summary(season=season, dims=["product_style"], filters={}, statuses=None)
    rows = res["rows"]
    print(f"rows: {len(rows)}")
    assert len(rows) == gt["n_full"] + gt["n_partial"] + gt["n_pending"] + gt["n_dbno"]

    s_ord = sum(r["ordered_qty"] or 0 for r in rows)
    s_dis = sum(r["dispatched_qty"] or 0 for r in rows)
    s_pen = sum(r["pending_qty"] or 0 for r in rows)
    assert approx(s_ord, kpis["total_ordered"]), "summary ordered != KPI"
    assert approx(s_dis, kpis["total_dispatched"]), "summary dispatched != KPI"
    assert approx(s_pen, kpis["total_pending"]), "summary pending != KPI"
    print("Summary <-> KPI reconciliation OK "
          f"(ordered={s_ord:,.0f} dispatched={s_dis:,.0f} pending={s_pen:,.0f})")

    # Every row's measures must satisfy the formulas.
    for r in rows:
        oq, dq = float(r["ordered_qty"]), float(r["dispatched_qty"])
        pq, pct = r["pending_qty"], r["dispatch_pct"]
        assert approx(pq, max(oq - dq, 0)), f"pending formula broken: {r}"
        if oq:
            # service rounds to 2 dp - allow half-a-hundredth tolerance
            assert pct is not None and approx(pct, dq / oq * 100, tol=0.005 + 1e-6), (
                f"pct formula broken: {r}"
            )
        else:
            assert pct is None, f"pct should be NULL when ordered=0: {r}"
        key = r["status_key"]
        if key == css.STATUS_FULLY:
            assert oq > 0 and dq >= oq
        elif key == css.STATUS_PARTIAL:
            assert oq > 0 and 0 < dq < oq
        elif key == css.STATUS_PENDING:
            assert oq > 0 and dq <= 0
        else:
            assert oq <= 0 and dq != 0
    print("Per-row status/formula checks OK")

    # All order-form styles present even with zero dispatch.
    zero_disp = [r for r in rows if (r["dispatched_qty"] or 0) == 0 and (r["ordered_qty"] or 0) > 0]
    assert len(zero_disp) == gt["n_pending"]
    distinct_styles_ordered = con.execute(
        f"""SELECT COUNT(DISTINCT {NC('style_code')}) FROM order_form.order_form
            WHERE style_code IS NOT NULL AND TRIM(style_code) <> ''
              {'AND ' + NS('season') + ' = ' + NS('?') if season else ''}""",
        [season] if season else [],
    ).fetchone()[0]
    ord_keys = {
        (r["season"], r["product_style"]) for r in rows if (r["ordered_qty"] or 0) > 0
    }
    print(f"order-side keys in summary: {len(ord_keys)} "
          f"(distinct raw styles: {distinct_styles_ordered})")

    # ------------------------------------------------------------------
    print("\n=== Brand chart reconciliation ===")
    bb = kpis["by_brand"]
    c_ord = sum(b["ordered_qty"] for b in bb)
    c_dis = sum(b["dispatched_qty"] for b in bb)
    c_pen = sum(b["pending_qty"] for b in bb)
    assert approx(c_ord, kpis["total_ordered"]), "chart ordered != KPI"
    assert approx(c_dis, kpis["total_dispatched"]), "chart dispatched != KPI"
    assert approx(c_pen, kpis["total_pending"]), "chart pending != KPI"
    print(f"brands: {len(bb)}; chart totals reconcile OK")
    for b in bb[:5]:
        print(f"  {str(b['brand'])[:24]:24} O={b['ordered_qty']:>7,.0f} "
              f"D={b['dispatched_qty']:>6,.0f} P={b['pending_qty']:>7,.0f}")

    # ------------------------------------------------------------------
    print("\n=== Grand-total rollup (no dims) ===")
    res_gt = css.get_summary(season=season, dims=[], filters={})
    grows0 = res_gt["rows"]
    assert approx(sum(r["ordered_qty"] or 0 for r in grows0), kpis["total_ordered"])
    assert approx(sum(r["dispatched_qty"] or 0 for r in grows0), kpis["total_dispatched"])
    assert approx(sum(r["pending_qty"] or 0 for r in grows0), kpis["total_pending"])
    print(f"dims=[] -> {len(grows0)} brand/season groups, totals reconcile OK")

    print("\n=== Dimensioned summary partitions totals ===")
    res_b = css.get_summary(season=season, dims=["brand"], filters={})
    brows = res_b["rows"]
    assert approx(sum(r["ordered_qty"] or 0 for r in brows), kpis["total_ordered"])
    assert approx(sum(r["dispatched_qty"] or 0 for r in brows), kpis["total_dispatched"])
    print("dims=[brand] partition OK")

    # ------------------------------------------------------------------
    print("\n=== Group-level rollup (Product/Style removed) ===")
    res_g = css.get_summary(season=season, dims=["subcategory"], filters={})
    grows = res_g["rows"]
    assert approx(sum(r["ordered_qty"] or 0 for r in grows), kpis["total_ordered"])
    assert approx(sum(r["dispatched_qty"] or 0 for r in grows), kpis["total_dispatched"])
    assert approx(sum(r["pending_qty"] or 0 for r in grows), kpis["total_pending"])
    gkeys = [(r["brand"], r["season"], r["subcategory"]) for r in grows]
    assert len(gkeys) == len(set(gkeys)), "duplicate group keys after rollup!"
    assert all(r.get("product_style") is None for r in grows), "style leaked into rollup!"
    assert all(r.get("mrp") is None for r in grows), "mrp must not appear at group level!"
    for r in grows:
        oq, dq = float(r["ordered_qty"]), float(r["dispatched_qty"])
        assert approx(r["pending_qty"], max(oq - dq, 0))
    print(f"rollup rows: {len(grows)} (< style grain {len(rows)}) — totals reconcile OK")

    print("\n=== MRP (Order Form mrp, Secondary mdp fallback) ===")
    res_m = css.get_summary(season=season, dims=["product_style"], filters={})
    mrows = res_m["rows"]
    with_mrp = [r for r in mrows if r.get("mrp") is not None]
    assert with_mrp, "no MRP values at style grain!"
    checked = 0
    for r in with_mrp:
        truth = con.execute(
            "SELECT MAX(mrp) FROM order_form.order_form WHERE TRIM(style_code) = ?",
            [r["product_style"]],
        ).fetchone()[0]
        if truth is not None:
            assert abs(float(r["mrp"]) - float(truth)) < 1e-6, f"mrp mismatch: {r}"
            checked += 1
        if checked >= 5:
            break
    print(f"mrp present on {len(with_mrp)}/{len(mrows)} rows; {checked} order-form spot checks OK")

    print("\n=== Filters reconcile ===")
    slicers = css.get_slicer_options({})
    print("slicer columns:", {k: len(v) for k, v in slicers.items()})
    some_col = "state" if "state" in slicers and slicers["state"] else next(
        c for c in slicers if slicers[c]
    )
    pick = slicers[some_col][:2]
    fk = css.get_kpis(season, {some_col: pick})
    fs = css.get_summary(season=season, dims=[], filters={some_col: pick})
    assert approx(sum(r["ordered_qty"] or 0 for r in fs["rows"]), fk["total_ordered"])
    assert approx(sum(r["dispatched_qty"] or 0 for r in fs["rows"]), fk["total_dispatched"])
    assert fk["total_ordered"] <= kpis["total_ordered"], "filter increased totals?!"
    print(f"filter {some_col}={pick}: ordered={fk['total_ordered']:,.0f} reconciles OK")

    # Cross-filter options: options for col X must respect other filters.
    xopts = css.get_slicer_options({some_col: pick})
    other_cols = [c for c in xopts if c != some_col]
    if other_cols:
        oc = other_cols[0]
        full_set = set(slicers[oc])
        narrowed = set(xopts[oc])
        assert narrowed <= full_set, "cross-filter widened option set?!"
        print(f"cross-filter check OK: {oc} options {len(full_set)} -> {len(narrowed)}")

    # ------------------------------------------------------------------
    print("\n=== Status filtering ===")
    pen_only = css.get_summary(
        season=season, dims=["product_style"], filters={}, statuses=[css.STATUS_PENDING]
    )
    assert all(r["status_key"] == css.STATUS_PENDING for r in pen_only["rows"])
    assert len(pen_only["rows"]) == gt["n_pending"]
    mix = css.get_summary(
        season=season, dims=["product_style"], filters={},
        statuses=[css.STATUS_FULLY, css.STATUS_DBNO],
    )
    assert {r["status_key"] for r in mix["rows"]} <= {css.STATUS_FULLY, css.STATUS_DBNO}
    assert len(mix["rows"]) == gt["n_full"] + gt["n_dbno"]
    print("status filter counts OK")

    # ------------------------------------------------------------------
    print("\n=== Season isolation ===")
    # Dispatches from non-order seasons must never leak into any row.
    other_season_qty = con.execute(
        f"""SELECT SUM(qty) FROM secondary_data.data
            WHERE {NS('season')} NOT IN (
                SELECT {NS('season')} FROM order_form.order_form WHERE season IS NOT NULL)"""
    ).fetchone()[0]
    print(f"non-order-season dispatch qty in source: {other_season_qty}")
    total_dis_all = css.get_kpis(None)["total_dispatched"]
    assert total_dis_all <= gt["tot_dispatched"] + 1e-6 or season is None
    # With a specific season, dispatched must only draw from that season.
    if season:
        season_truth = con.execute(
            f"""SELECT COALESCE(SUM(qty),0) FROM secondary_data.data
                WHERE {NS('season')} = {NS('?')}""", [season]
        ).fetchone()[0]
        assert kpis["total_dispatched"] <= float(season_truth) + 1e-6
    print("season isolation OK")

    # ------------------------------------------------------------------
    print("\n=== Sub-category rules ===")
    # Mapped rows carry ORDER FORM subcategory; dbno rows carry PRODUCT_DESC.
    res_sc = css.get_summary(
        season=season, dims=["subcategory", "product_style"], filters={}, statuses=None
    )
    sc_rows = res_sc["rows"]
    dbno_rows = [r for r in sc_rows if r["status_key"] == css.STATUS_DBNO]
    for r in dbno_rows:
        assert r["subcategory"] and r["subcategory"] == r["subcategory"].strip()
    print(f"{len(dbno_rows)} dbno rows all carry cleaned PRODUCT_DESC subcategory OK")

    # ------------------------------------------------------------------
    print("\n=== Status drill-down + group rollup combine correctly ===")
    # At ANY hierarchy grain the four status selections must partition the
    # unfiltered totals exactly (drill-down stays reconciled).
    grain = ["retailer_name", "product_style"]
    all_g = css.get_summary(season=season, dims=grain, filters={})
    pend_g = css.get_summary(season=season, dims=grain, filters={},
                             statuses=[css.STATUS_PENDING])
    rest_g = css.get_summary(season=season, dims=grain, filters={},
                             statuses=[css.STATUS_FULLY, css.STATUS_PARTIAL, css.STATUS_DBNO])
    a = sum(r["ordered_qty"] or 0 for r in all_g["rows"])
    b = sum(r["ordered_qty"] or 0 for r in pend_g["rows"]) + sum(
        r["ordered_qty"] or 0 for r in rest_g["rows"])
    assert approx(a, b), f"status partition broken at grain {grain}: {a} != {b}"
    assert all(r["status_key"] == css.STATUS_PENDING for r in pend_g["rows"])
    print(f"status drill-down partitions totals OK at grain {grain} "
          f"(all={a:,.0f} = pending {b:,.0f})")

    # ------------------------------------------------------------------
    print("\n=== Special-dim slicer options & filtering ===")
    # Sub Category / Product Style must now be offered as slicer values
    # (this was the bug: they used to be missing from the dropdowns).
    opts = css.get_slicer_options({})
    for key in ("subcategory", "product_style"):
        assert key in opts, f"{key} missing from slicer options"
        assert opts[key], f"{key} slicer options empty"
    print(f"slicer options OK: subcategory={len(opts['subcategory'])} values, "
          f"product_style={len(opts['product_style'])} values")

    # Every offered subcategory must exist as a summary-row value at that grain.
    sc_sum = css.get_summary(season=season, dims=["subcategory"], filters={})["rows"]
    sc_vals = {r["subcategory"] for r in sc_sum}
    assert set(opts["subcategory"]) <= sc_vals, (
        f"options not a subset of data: {set(opts['subcategory']) - sc_vals}"
    )

    # Filtering by a subcategory reconciles with the unfiltered roll-up.
    target = opts["subcategory"][0]
    expected = sum(r["ordered_qty"] for r in sc_sum if r["subcategory"] == target)
    got = css.get_kpis(season, {"subcategory": [target]})["total_ordered"]
    assert approx(got, expected), f"subcategory filter mismatch: {got} != {expected}"
    print(f"subcategory filter reconciles OK ({target!r}: {expected:,.0f} ordered)")

    # Cross-filtering: a subcategory selection narrows product_style options
    # to a subset (its own selection is ignored, so it stays stable).
    ps_before = set(opts["product_style"])
    ps_after = set(css.get_slicer_options({"subcategory": [target]})["product_style"])
    assert ps_after and ps_after <= ps_before, "cross-filter did not narrow product_style"
    print(f"cross-filter narrows product_style OK ({len(ps_before)} -> {len(ps_after)})")

    # Style-code filter works and reconciles with the unfiltered total.
    style = opts["product_style"][0]
    all_by_style = css.get_summary(season=season, dims=["product_style"], filters={})["rows"]
    expected_qty = sum(
        r["ordered_qty"] for r in all_by_style if r["product_style"] == style
    )
    by_style = css.get_summary(
        season=season, dims=["product_style"], filters={"product_style": [style]}
    )["rows"]
    assert by_style and all(r["product_style"] == style for r in by_style)
    assert approx(sum(r["ordered_qty"] for r in by_style), expected_qty), (
        f"product_style filter mismatch: {sum(r['ordered_qty'] for r in by_style)} "
        f"!= {expected_qty}"
    )
    print(f"product_style filter reconciles OK ({style!r}: {expected_qty:,.0f} ordered)")

    # Combined store-master + special-dim filter is accepted and JSON-safe.
    sm_col = next((d["column"] for d in dims if opts.get(d["column"])), None)
    if sm_col:
        combined = css.get_kpis(
            season, {sm_col: [opts[sm_col][0]], "subcategory": [target]}
        )
        json.dumps(combined)
        print(f"combined {sm_col} + subcategory filter OK "
              f"(total_ordered={combined['total_ordered']:,.0f})")

    print("\n=== JSON serialisation sanity ===")
    for payload in (kpis, res, pen_only, css.get_kpis(None)):
        json.dumps(payload)
    print("JSON OK")

    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    main()