"""Unit tests for the Bill_No Based KPI Analysis formula logic.

These tests are INDEPENDENT of the UI and of the database: they exercise the
pure helpers in app/services/bill_kpi.py (growth %, Active_Days/SPD calc,
bucket assignment edges, brand contribution %, pivot subtotal re-aggregation,
date-range windowing, Top-N snapping).

Run from C:\\webapp\\backend:
    python -m unittest tests.test_bill_kpi_logic -v
"""
import math
import unittest

import pandas as pd

from app.services import bill_analysis as ba
from app.services import bill_kpi as bk


class GrowthPctTests(unittest.TestCase):
    def test_positive_growth(self):
        self.assertAlmostEqual(bk._growth(120, 100), 20.0)

    def test_negative_growth(self):
        self.assertAlmostEqual(bk._growth(75, 100), -25.0)

    def test_zero_lfy_returns_none_never_divides_by_zero(self):
        self.assertIsNone(bk._growth(50, 0))
        self.assertIsNone(bk._growth(50, 0.0))

    def test_none_inputs_return_none(self):
        self.assertIsNone(bk._growth(None, 10))
        self.assertIsNone(bk._growth(10, None))

    def test_zero_cfy_zero_lfy_is_none(self):
        self.assertIsNone(bk._growth(0, 0))

    def test_result_is_finite(self):
        self.assertTrue(math.isfinite(bk._growth(3, 7)))


class ActiveDaysSdpTests(unittest.TestCase):
    """Brand-anchored Active_Days rule (req §3): the window start is the brand's
    GLOBAL first sale date (across all retailers), running to the dataset max."""

    def _df(self):
        return pd.DataFrame({
            "brand": ["B1", "B1", "B2", "B2"],
            "retailer_name": ["R1", "R2", "R1", "R2"],
            "qty": [2, 3, 1, 4],
            "bill_val": [1000.0, 2000.0, 500.0, 3000.0],
            "bill_date": pd.to_datetime(["2025-04-01", "2025-04-03", "2025-04-05", "2025-04-10"]),
        })

    def test_active_days_is_max_minus_brand_global_first_plus_one(self):
        df = self._df()
        max_ts = pd.to_datetime(df["bill_date"].max())
        # B1 first sale = 2025-04-01; dataset max = 2025-04-10 -> 10 days.
        self.assertEqual(bk._active_days(df, "B1", max_ts), 10)
        # B2 first sale = 2025-04-05 -> 6 days.
        self.assertEqual(bk._active_days(df, "B2", max_ts), 6)
        # No brand -> dataset-wide first sale 2025-04-01 -> 10 days.
        self.assertEqual(bk._active_days(df, None, max_ts), 10)

    def test_spd_uses_active_days_not_bill_count_of_days(self):
        df = self._df()
        m = bk._metrics(df, active_days=10)
        self.assertEqual(m["total_bills"], 4)
        self.assertEqual(m["qty"], 10.0)
        self.assertEqual(m["val"], 6500.0)
        # SPD[QTY] = qty / active_days (NOT distinct bill dates in the slice).
        self.assertAlmostEqual(m["spd_qty"], 10.0 / 10)
        self.assertAlmostEqual(m["spd_val"], 6500.0 / 10)
        # SPD denominator stays 10 even if the slice only has 3 distinct dates.
        subset = df.iloc[:3]
        m2 = bk._metrics(subset, active_days=10)
        self.assertAlmostEqual(m2["spd_qty"], subset["qty"].sum() / 10)
        self.assertNotEqual(subset["bill_date"].nunique(), 10)

    def test_empty_period_is_zero_safe(self):
        m = bk._metrics(pd.DataFrame(), 5)
        self.assertEqual(m["total_bills"], 0)
        self.assertIsNone(m["upt"])
        self.assertIsNone(m["spd_qty"])


class BucketAssignmentTests(unittest.TestCase):
    """The module reuses bill_analysis buckets (half-open [low, high) edges)."""

    def test_reused_bucket_lists(self):
        self.assertEqual(bk.QUANTITY_BUCKETS, ba.QUANTITY_BUCKETS)
        self.assertEqual(bk.VALUE_BUCKETS, ba.VALUE_BUCKETS)

    def test_qty_bucket_edges(self):
        self.assertEqual(ba._qty_bucket(1), "1 Qty Bill")
        self.assertEqual(ba._qty_bucket(4), "4 Qty Bill")
        self.assertEqual(ba._qty_bucket(5), ">4 Qty Bill")

    def test_value_bucket_edges_half_open(self):
        self.assertEqual(ba._value_bucket(2999.99), "0 - 3K")
        self.assertEqual(ba._value_bucket(3000), "3K - 5K")
        self.assertEqual(ba._value_bucket(15000), "> 15K")


class ContributionPercentTests(unittest.TestCase):
    def test_multi_brand_bill_reconciles_to_100(self):
        sub = pd.DataFrame({
            "brand_code": ["B1", "B1", "B2"],
            "bill_val": [1200.0, 800.0, 1000.0],
        })
        parts = bk._contribution_parts(sub)
        self.assertEqual(len(parts), 2)  # B1 (2000) and B2 (1000)
        self.assertAlmostEqual(sum(p["contribution_pct"] for p in parts), 100.0)
        self.assertEqual(parts[0]["brand"], "B1")  # highest value first
        self.assertAlmostEqual(parts[0]["contribution_pct"], 200.0 / 3.0)
        self.assertAlmostEqual(parts[1]["contribution_pct"], 100.0 / 3.0)

    def test_zero_value_bill_is_safe(self):
        sub = pd.DataFrame({"brand_code": ["B1"], "bill_val": [0.0]})
        parts = bk._contribution_parts(sub)
        self.assertEqual(parts[0]["contribution_pct"], 0.0)

    def test_null_brand_labeled(self):
        sub = pd.DataFrame({"brand_code": [None], "bill_val": [500.0]})
        parts = bk._contribution_parts(sub)
        self.assertIsNone(parts[0]["brand"])


class PivotSubtotalTests(unittest.TestCase):
    """Dimensional summary: grand-total rows are GENUINE re-aggregations at the
    grouping's grain - never an average of nested child rows."""

    def _df(self):
        return pd.DataFrame({
            "brand": ["B1", "B1", "B2", "B2"],
            "retailer_name": ["R1", "R2", "R1", "R3"],
            "qty": [2, 3, 1, 4],
            "bill_val": [1000.0, 2000.0, 500.0, 3000.0],
            "bill_date": pd.to_datetime(["2025-04-01"] * 4),
            "qty_bucket": ["2 Qty Bill", "3 Qty Bill", "1 Qty Bill", "4 Qty Bill"],
            "value_bucket": ["0 - 3K", "0 - 3K", "0 - 3K", "3K - 5K"],
        })

    def test_level1_brand_is_sum_of_children_not_average(self):
        df = self._df()
        rows = bk._dimension_summary_rows(df, df, ["brand", "retailer_name"], 10)
        # Grand total row first.
        self.assertEqual(rows[0]["dim_value"], "(All)")
        self.assertEqual(rows[0]["is_total"], True)
        # B1 level-1 subtotal = genuine re-aggregation over B1's 2 bills.
        b1 = next(r for r in rows if r["_level"] == 1 and r["brand"] == "B1")
        cells = {k["key"]: k for k in b1["kpis"]}
        self.assertEqual(cells["total_bills"]["cfy"], 2.0)
        self.assertAlmostEqual(cells["abv"]["cfy"], (1000.0 + 2000.0) / 2)
        # NOT the average of its two child (retailer) rows.
        child_cells = [r["kpis"] for r in rows if r["_level"] == 2 and r["brand"] == "B1"]
        avg_child = sum(
            next(k for k in c if k["key"] == "total_bills")["cfy"] for c in child_cells
        ) / len(child_cells)
        self.assertEqual(cells["total_bills"]["cfy"], 2.0)
        self.assertNotAlmostEqual(avg_child, 2.0, places=6)  # would be 1.5 if averaged

    def test_grand_total_is_whole_context_reaggregation(self):
        df = self._df()
        rows = bk._dimension_summary_rows(df, df, ["retailer_name"], 10)
        grand = rows[0]
        cells = {k["key"]: k for k in grand["kpis"]}
        self.assertEqual(cells["total_bills"]["cfy"], 4.0)
        self.assertAlmostEqual(
            cells["asp"]["cfy"],
            (1000 + 2000 + 500 + 3000) / (2 + 3 + 1 + 4),
        )

    def test_no_dims_returns_single_grand_total(self):
        df = self._df()
        rows = bk._dimension_summary_rows(df, df, [], 10)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["is_total"], True)

    def test_multi_dim_column_order_mirrors_selection(self):
        df = self._df()
        rows = bk._dimension_summary_rows(df, df, ["retailer_name", "brand"], 10)
        # Column order in the payload follows selection order.
        r1 = next(r for r in rows if r["_level"] == 1 and r["retailer_name"] == "R1")
        self.assertEqual(r1["retailer_name"], "R1")
        self.assertIsNone(r1.get("brand"))
        # First-selected dim is the outer grouping -> level-1 is_total flags.
        l1 = [r for r in rows if r["_level"] == 1]
        self.assertTrue(all(r["is_total"] for r in l1))


class DistributionPivotTests(unittest.TestCase):
    def _df(self):
        return pd.DataFrame({
            "brand": ["B1", "B1", "B2"],
            "qty": [1, 5, 4],
            "bill_val": [1000.0, 6000.0, 4000.0],
            "bill_date": pd.to_datetime(["2025-04-01"] * 3),
            "qty_bucket": ["1 Qty Bill", ">4 Qty Bill", "4 Qty Bill"],
            "value_bucket": ["0 - 3K", "5K - 8K", "3K - 5K"],
        })

    def test_bucket_bill_counts_reconcile_to_all_bills(self):
        df = self._df()
        rows = bk._distribution_rows(df, df, "all", "qty_bucket", bk.QUANTITY_BUCKETS, 10)
        self.assertEqual(len(rows), 1)
        cells = rows[0]["cells"]
        self.assertEqual(
            sum(cells[b]["cfy_bills"] for b in bk.QUANTITY_BUCKETS),
            cells["All Bills"]["cfy_bills"],
        )
        self.assertEqual(cells["All Bills"]["cfy_bills"], 3.0)

    def test_cell_is_bill_count_with_bill_based_share_and_pp_delta(self):
        df = self._df()
        rows = bk._distribution_rows(df, df, "all", "qty_bucket", bk.QUANTITY_BUCKETS, 10)
        cell = rows[0]["cells"][">4 Qty Bill"]
        # Bill counts + bill-based Cont% / pp Δ - no UPT / ABV / ASP / SPD,
        # and NOT qty/val sums as the headline figure.
        self.assertEqual(
            set(cell.keys()),
            {
                "metric", "cfy_bills", "lfy_bills", "cfy_qty", "lfy_qty",
                "cfy_val", "lfy_val", "share_cfy_pct", "share_lfy_pct", "growth_pct",
            },
        )
        self.assertEqual(cell["metric"], "bills")
        # "How many >4-qty bills happened": 1 bill.
        self.assertEqual(cell["cfy_bills"], 1.0)
        # Cont% is BILL-based: 1 of the row's 3 bills -> 33.3%
        # (a qty-based share would be 50%, a val-based one 54.5%).
        self.assertAlmostEqual(cell["share_cfy_pct"], 100.0 / 3.0)
        # pp Δ = CFY Cont% - LFY Cont% = 0 for identical periods.
        self.assertEqual(cell["growth_pct"], 0.0)

    def test_pp_delta_and_share_are_cont_based_for_value_buckets(self):
        cfy = self._df()
        lfy = pd.DataFrame({
            "brand": ["B1", "B1"],
            "qty": [1, 2],
            "bill_val": [2000.0, 2500.0],
            "bill_date": pd.to_datetime(["2024-04-01"] * 2),
            "qty_bucket": ["1 Qty Bill", "2 Qty Bill"],
            "value_bucket": ["0 - 3K", "0 - 3K"],
        })
        rows = bk._distribution_rows(cfy, lfy, "all", "value_bucket", bk.VALUE_BUCKETS, 10)
        cell = rows[0]["cells"]["0 - 3K"]
        # HOW MANY bills in the 0-3K value bucket: CFY 1, LFY 2.
        self.assertEqual(cell["cfy_bills"], 1.0)
        self.assertEqual(cell["lfy_bills"], 2.0)
        # Cont% of CFY bills: 1 / 3.
        self.assertAlmostEqual(cell["share_cfy_pct"], 100.0 / 3.0)
        # Cont% of LFY bills: 2 / 2.
        self.assertAlmostEqual(cell["share_lfy_pct"], 100.0)
        # pp Δ on CONT% (user-confirmed), NOT a % change on bill counts:
        #   33.333 - 100 = -66.667 pp  (the numeric value happens to match the
        #   old Cont%-growth formula only because share_lfy_pct = 100 here; a
        #   bill-count based number would be (1 - 2) / 2 * 100 = -50, which is
        #   intentionally NOT used).
        self.assertAlmostEqual(cell["growth_pct"], -200.0 / 3.0)

    def test_distribution_honors_dim_rollup(self):
        df = self._df()
        rows = bk._distribution_rows(df, df, "brand", "qty_bucket", bk.QUANTITY_BUCKETS, 10)
        dims = [r["dim_value"] for r in rows]
        self.assertEqual(dims, ["(All)", "B1", "B2"])
        b1 = next(r for r in rows if r["dim_value"] == "B1")
        self.assertIn("All Bills", b1["cells"])
        # B1 has 2 bills across buckets 1-qty + >4-qty.
        self.assertEqual(b1["cfy_bills"], 2.0)
        # B1's >4 bucket Cont% is relative to B1's OWN bill total (2 bills),
        # not the whole set - genuine re-aggregation at the row's grain.
        self.assertAlmostEqual(b1["cells"][">4 Qty Bill"]["share_cfy_pct"], 50.0)


class DateRangeModeTests(unittest.TestCase):
    def _df(self):
        # Two fiscal years of bills so date-range vs FY differ clearly.
        # fy_label mirrors the backend format (FY<start year>-<end yy>).
        return pd.DataFrame({
            "bill_date": pd.to_datetime([
                "2025-04-01", "2025-05-15", "2026-04-01", "2026-05-15",
                "2024-04-01", "2024-05-15",
            ]),
            "qty": [1, 2, 3, 4, 5, 6],
            "bill_val": [100.0, 200.0, 300.0, 400.0, 500.0, 600.0],
            "fy_label": [
                "FY2025-26", "FY2025-26", "FY2026-27", "FY2026-27",
                "FY2024-25", "FY2024-25",
            ],
        })

    def test_custom_range_shifts_lfy_back_one_year(self):
        df = self._df()
        rng = {"start": "2026-04-01", "end": "2026-05-31"}
        cfy, lfy, meta = bk._period_windows(df, rng)
        self.assertEqual(meta["mode"], "date-range")
        self.assertEqual(meta["cfy_start"], "2026-04-01")
        self.assertEqual(meta["lfy_start"], "2025-04-01")
        self.assertEqual(len(cfy), 2)
        self.assertEqual(len(lfy), 2)  # 2025-04-01 + 2025-05-15
        self.assertAlmostEqual(cfy["bill_val"].sum(), 700.0)
        self.assertAlmostEqual(lfy["bill_val"].sum(), 300.0)

    def test_fy_mode_uses_fy_labels(self):
        df = self._df()
        cfy, lfy, meta = bk._period_windows(df, None)
        self.assertEqual(meta["mode"], "fy")
        # Max date is 2026-05-15 -> current FY = FY25-26.
        self.assertEqual(len(cfy), 2)
        self.assertIn("fy_context", meta)


class TopBillsRankOrderTests(unittest.TestCase):
    """Top Bills always come back as a strict, deterministic rank 1..n:
    bill_val desc -> ties broken by earliest bill_date -> internal_bill_id."""

    def _df(self):
        return pd.DataFrame(
            {
                "internal_bill_id": [
                    "AD01-FY25-04-9", "AD01-FY25-04-1", "AD01-FY25-04-5",
                ],
                "bill_date": pd.to_datetime(["2025-06-03", "2025-06-02", "2025-06-02"]),
                "month": ["Jun", "Jun", "Jun"],
                "adonis_store_code": ["AD01"] * 3,
                "brand": ["B"] * 3,
                "retailer_name": ["R"] * 3,
                "qty": [1, 5, 2],
                "bill_val": [5000.0, 5000.0, 5000.0],
            }
        )

    def test_strict_rank_and_deterministic_tie_break(self):
        rows = bk._top_bill_rows(self._df(), 3)
        self.assertEqual([r["rank"] for r in rows], [1, 2, 3])
        self.assertEqual([r["bill_val"] for r in rows], [5000.0, 5000.0, 5000.0])
        # Earliest bill_date first, then lexicographic internal_bill_id.
        self.assertEqual(
            [r["internal_bill_id"] for r in rows],
            ["AD01-FY25-04-1", "AD01-FY25-04-5", "AD01-FY25-04-9"],
        )

    def test_none_and_empty_inputs(self):
        self.assertEqual(bk._top_bill_rows(None, 10), [])
        self.assertEqual(bk._top_bill_rows(pd.DataFrame(), 10), [])
        self.assertEqual(bk._top_bill_rows(self._df(), 0), [])


class SnapTopNTests(unittest.TestCase):
    def test_accepts_any_positive_count(self):
        self.assertEqual(bk.snap_top_n(5), 5)
        self.assertEqual(bk.snap_top_n(10), 10)
        self.assertEqual(bk.snap_top_n(7), 7)
        self.assertEqual(bk.snap_top_n(13), 13)
        self.assertEqual(bk.snap_top_n(24), 24)
        self.assertEqual(bk.snap_top_n(30), 30)

    def test_non_positive_clamped_to_one(self):
        self.assertEqual(bk.snap_top_n(2), 2)
        self.assertEqual(bk.snap_top_n(0), 1)
        self.assertEqual(bk.snap_top_n(-5), 1)

    def test_invalid_defaults_to_25(self):
        self.assertEqual(bk.snap_top_n("abc"), 25)
        self.assertEqual(bk.snap_top_n(None), 25)


class KpiCellTests(unittest.TestCase):
    def test_kpi_cell_contains_all_seven_kpis_with_trio(self):
        cm = bk._metrics(
            pd.DataFrame({"qty": [10], "bill_val": [5000], "bill_date": [pd.Timestamp("2025-04-01")]}), 10
        )
        lm = bk._metrics(
            pd.DataFrame({"qty": [5], "bill_val": [2000], "bill_date": [pd.Timestamp("2024-04-01")]}), 10
        )
        cell = {k["key"]: k for k in bk._kpi_cell(cm, lm)}
        self.assertEqual(
            set(cell.keys()),
            {"total_bills", "upt", "abv", "asp", "spd_qty", "spd_val", "active_days"},
        )
        for k in ("total_bills", "upt", "abv", "asp", "spd_qty", "spd_val"):
            self.assertTrue({"lfy", "cfy", "growth_pct"} <= set(cell[k]))

    def test_active_days_has_no_growth_pill(self):
        cm = bk._metrics(pd.DataFrame(), 10)
        cell = {k["key"]: k for k in bk._kpi_cell(cm, cm)}
        self.assertIsNone(cell["active_days"]["growth_pct"])


if __name__ == "__main__":
    unittest.main()
