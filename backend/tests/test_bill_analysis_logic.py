"""Unit tests for the Bill No. Based Analysis formula logic.

These tests are INDEPENDENT of the UI and of the database: they exercise the
pure helpers in app/services/bill_analysis.py (KPI formulas, growth %, bucket
assignment, bill-detail ranking and brand-contribution percentages).

Run from C:\\webapp\\backend:
    python -m unittest tests.test_bill_analysis_logic -v
"""
import math
import unittest

import pandas as pd

from app.services import bill_analysis as ba


class GrowthPctTests(unittest.TestCase):
    def test_positive_growth(self):
        self.assertAlmostEqual(ba._growth(120, 100), 20.0)

    def test_negative_growth(self):
        self.assertAlmostEqual(ba._growth(75, 100), -25.0)

    def test_zero_lfy_returns_none_never_divides_by_zero(self):
        self.assertIsNone(ba._growth(50, 0))
        self.assertIsNone(ba._growth(50, 0.0))

    def test_none_inputs_return_none(self):
        self.assertIsNone(ba._growth(None, 10))
        self.assertIsNone(ba._growth(10, None))
        self.assertIsNone(ba._growth(None, None))

    def test_zero_cfy_zero_lfy_is_none_not_nan(self):
        self.assertIsNone(ba._growth(0, 0))

    def test_result_is_finite(self):
        g = ba._growth(3, 7)
        self.assertTrue(math.isfinite(g))


class QuantityBucketTests(unittest.TestCase):
    def test_exact_edges(self):
        self.assertEqual(ba._qty_bucket(1), "1 Qty Bill")
        self.assertEqual(ba._qty_bucket(2), "2 Qty Bill")
        self.assertEqual(ba._qty_bucket(3), "3 Qty Bill")
        self.assertEqual(ba._qty_bucket(4), "4 Qty Bill")

    def test_above_four(self):
        self.assertEqual(ba._qty_bucket(5), ">4 Qty Bill")
        self.assertEqual(ba._qty_bucket(100), ">4 Qty Bill")

    def test_fractional_qty_below_two_counts_as_one(self):
        self.assertEqual(ba._qty_bucket(1.5), "1 Qty Bill")

    def test_null_defaults_to_over_four(self):
        self.assertEqual(ba._qty_bucket(None), ">4 Qty Bill")
        self.assertEqual(ba._qty_bucket(float("nan")), ">4 Qty Bill")

    def test_every_bucket_label_is_in_bucket_order(self):
        for q in (0, 1, 2, 3, 4, 5):
            self.assertIn(ba._qty_bucket(q), ba.QUANTITY_BUCKETS)


class ValueBucketTests(unittest.TestCase):
    """Half-open [low, high) edges: exactly 3,000 lands in "3K - 5K"."""

    def test_zero_and_below_three_k(self):
        self.assertEqual(ba._value_bucket(0), "0 - 3K")
        self.assertEqual(ba._value_bucket(2999.99), "0 - 3K")

    def test_exactly_3000_is_in_3k_5k(self):
        self.assertEqual(ba._value_bucket(3000), "3K - 5K")

    def test_exactly_5000_is_in_5k_8k(self):
        self.assertEqual(ba._value_bucket(5000), "5K - 8K")

    def test_exactly_8000_is_in_8k_10k(self):
        self.assertEqual(ba._value_bucket(8000), "8K - 10K")

    def test_exactly_10000_is_in_10k_12k(self):
        self.assertEqual(ba._value_bucket(10000), "10K - 12K")

    def test_exactly_12000_is_in_12k_15k(self):
        self.assertEqual(ba._value_bucket(12000), "12K - 15K")

    def test_exactly_15000_is_over_15k(self):
        self.assertEqual(ba._value_bucket(15000), "> 15K")

    def test_null_defaults_to_lowest_bucket(self):
        self.assertEqual(ba._value_bucket(None), "0 - 3K")
        self.assertEqual(ba._value_bucket(float("nan")), "0 - 3K")

    def test_every_bucket_label_is_in_bucket_order(self):
        for v in (0, 3000, 5000, 8000, 10000, 12000, 15000):
            self.assertIn(ba._value_bucket(v), ba.VALUE_BUCKETS)


class KpiFormulaTests(unittest.TestCase):
    def _df(self, rows):
        return pd.DataFrame(rows, columns=["qty", "bill_val", "bill_date"])

    def test_upt_abv_asp_formulas(self):
        df = self._df(
            [
                [2, 1000.0, "2025-04-01"],
                [3, 2000.0, "2025-04-01"],
            ]
        )
        m = ba._period_metrics(df)
        self.assertEqual(m["total_bills"], 2)
        self.assertEqual(m["qty"], 5)
        self.assertAlmostEqual(m["upt"], 5 / 2)      # qty / bills
        self.assertAlmostEqual(m["abv"], 3000 / 2)   # val / bills
        self.assertAlmostEqual(m["asp"], 3000 / 5)   # val / qty

    def test_empty_period_is_zero_safe(self):
        m = ba._period_metrics(self._df([]))
        self.assertEqual(m["total_bills"], 0)
        self.assertIsNone(m["upt"])
        self.assertIsNone(m["abv"])
        self.assertIsNone(m["asp"])

    def test_kpis_carry_growth_and_none_when_lfy_zero(self):
        cfy = {"total_bills": 12, "upt": 2.0, "abv": 500.0, "asp": 250.0}
        lfy = {"total_bills": 10, "upt": 2.5, "abv": 400.0, "asp": 160.0}
        kpis = {k["key"]: k for k in ba._kpis(cfy, lfy)}
        self.assertAlmostEqual(kpis["total_bills"]["growth_pct"], 20.0)
        self.assertAlmostEqual(kpis["upt"]["growth_pct"], -20.0)
        self.assertAlmostEqual(kpis["abv"]["growth_pct"], 25.0)
        self.assertAlmostEqual(kpis["asp"]["growth_pct"], 56.25)

        zero_lfy = {k: 0 for k in lfy}
        kpis0 = {k["key"]: k for k in ba._kpis(cfy, zero_lfy)}
        for k in kpis0.values():
            self.assertIsNone(k["growth_pct"])


class TopBillTests(unittest.TestCase):
    def _df(self):
        return pd.DataFrame(
            {
                "internal_bill_id": ["AD01-FY25-04-3", "AD01-FY25-04-1", "AD01-FY25-04-2"],
                "bill_date": pd.to_datetime(["2025-06-02", "2025-06-01", "2025-06-03"]),
                "month": ["Jun", "Jun", "Jun"],
                "adonis_store_code": ["AD01"] * 3,
                "brand": ["B"] * 3,
                "retailer_name": ["R"] * 3,
                "qty": [1, 5, 2],
                "bill_val": [3000.0, 10000.0, 6500.0],
            }
        )

    def test_ranked_by_bill_val_desc_and_limited(self):
        rows = ba._top_bill_rows(self._df(), 2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["internal_bill_id"], "AD01-FY25-04-1")
        self.assertEqual(rows[1]["internal_bill_id"], "AD01-FY25-04-2")
        self.assertEqual(rows[0]["bill_val"], 10000.0)
        # Server-side rank is stable and 1-based.
        self.assertEqual([r["rank"] for r in rows], [1, 2])

    def test_none_and_empty_inputs(self):
        self.assertEqual(ba._top_bill_rows(None, 10), [])
        self.assertEqual(ba._top_bill_rows(self._df(), 0), [])

    def test_tied_values_are_deterministic_oldest_then_id(self):
        df = pd.DataFrame(
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
        rows = ba._top_bill_rows(df, 3)
        # All three tie at 5000: the tie-break is earliest bill_date, then id,
        # so the list is ALWAYS a strict, deterministic rank 1..n.
        self.assertEqual([r["rank"] for r in rows], [1, 2, 3])
        self.assertEqual([r["bill_val"] for r in rows], [5000.0, 5000.0, 5000.0])
        self.assertEqual(
            [r["internal_bill_id"] for r in rows],
            ["AD01-FY25-04-1", "AD01-FY25-04-5", "AD01-FY25-04-9"],
        )


class HierarchyKpiCellTests(unittest.TestCase):
    """N-level row hierarchy: every row carries ALL four bill KPIs, each with
    its LFY / CFY / Growth trio, and level-1 rows are genuine re-aggregations
    at the selected dimension's grain (never an average of child rows)."""

    def _df(self):
        return pd.DataFrame(
            {
                "brand": ["B1", "B1", "B2", "B2"],
                "adonis_store_code": ["S1", "S2", "S1", "S3"],
                "qty": [2, 3, 1, 4],
                "bill_val": [1000.0, 2000.0, 500.0, 3000.0],
                "bill_date": pd.to_datetime(["2025-04-01"] * 4),
            }
        )

    def test_every_row_has_all_four_kpis_with_lfy_cfy_growth_trio(self):
        rows = ba._hierarchy_rows(self._df(), self._df(), ["brand", "adonis_store_code"])
        self.assertEqual(len(rows), 6)  # 2 brands + 4 stores
        for r in rows:
            keys = {k["key"] for k in r["kpis"]}
            self.assertEqual(keys, {"total_bills", "upt", "abv", "asp"})
            for k in r["kpis"]:
                self.assertTrue({"lfy", "cfy", "growth_pct"} <= set(k))

    def test_level1_is_grand_total_at_brand_grain(self):
        rows = ba._hierarchy_rows(self._df(), self._df(), ["brand", "adonis_store_code"])
        b1 = rows[0]
        self.assertEqual(b1["_label"], "B1")
        self.assertEqual(b1["bills"], 2)
        cells = {k["key"]: k for k in b1["kpis"]}
        # B1 = qty 5, value 3000 across 2 bills -> computed directly, not averaged
        self.assertAlmostEqual(cells["abv"]["cfy"], 1500.0)
        self.assertAlmostEqual(cells["upt"]["cfy"], 2.5)
        self.assertAlmostEqual(cells["asp"]["cfy"], 600.0)

    def test_child_rows_are_own_grain_under_parent(self):
        rows = ba._hierarchy_rows(self._df(), self._df(), ["brand", "adonis_store_code"])
        s1 = [r for r in rows if r["_level"] == 2 and r["_label"] == "S1"]
        self.assertEqual(len(s1), 2)  # S1 sells under both B1 and B2
        b1_s1 = [r for r in s1 if r["brand"] == "B1"][0]
        self.assertEqual(b1_s1["bills"], 1)
        abv = {k["key"]: k for k in b1_s1["kpis"]}["abv"]
        self.assertAlmostEqual(abv["cfy"], 1000.0)

    def test_brand_total_is_sum_not_average_of_child_rows(self):
        rows = ba._hierarchy_rows(self._df(), self._df(), ["brand", "adonis_store_code"])
        b1 = rows[0]
        children = [r for r in rows if r["_level"] == 2 and r["brand"] == "B1"]
        self.assertEqual(b1["bills"], sum(c["bills"] for c in children))
        self.assertNotEqual(b1["bills"], sum(c["bills"] for c in children) / len(children))

    def test_growth_uses_recomputed_lfy_at_same_cell(self):
        rows = ba._hierarchy_rows(self._df(), self._df(), ["brand"])
        k = {x["key"]: x for x in rows[0]["kpis"]}["total_bills"]
        self.assertEqual(k["cfy"], 2)
        self.assertEqual(k["lfy"], 2)
        self.assertAlmostEqual(k["growth_pct"], 0.0)

    def test_empty_lfy_cells_stay_zero_safe(self):
        rows = ba._hierarchy_rows(self._df(), self._df().head(0), ["brand"])
        k = {x["key"]: x for x in rows[0]["kpis"]}["total_bills"]
        self.assertEqual(k["lfy"], 0.0)
        self.assertIsNone(k["growth_pct"])

    def test_supports_three_levels(self):
        df = self._df().assign(state="GJ")
        rows = ba._hierarchy_rows(df, df, ["brand", "adonis_store_code", "state"])
        self.assertEqual({r["_level"] for r in rows}, {1, 2, 3})
        # 2 brands + 4 stores + 4 store-state rows
        self.assertEqual(len(rows), 10)


class DistributionPivotTests(unittest.TestCase):
    """Buckets become COLUMN HEADERS; each cell carries all four KPI trios and
    the 'All Bills' column reconciles with the sum of the bucket columns."""

    def _df(self):
        return pd.DataFrame(
            {
                "brand": ["B1", "B1", "B1", "B2", "B2"],
                "qty": [1, 2, 5, 3, 4],
                "qty_bucket": [
                    "1 Qty Bill", "2 Qty Bill", ">4 Qty Bill",
                    "3 Qty Bill", "4 Qty Bill",
                ],
                "bill_val": [1000.0, 2000.0, 6000.0, 3000.0, 4000.0],
                "value_bucket": [
                    "0 - 3K", "0 - 3K", "5K - 8K", "3K - 5K", "3K - 5K",
                ],
                "bill_date": pd.to_datetime(["2025-04-01"] * 5),
            }
        )

    def test_rows_are_dim_values_and_columns_are_buckets(self):
        rows = ba._distribution_rows(
            self._df(), self._df(), "brand", "qty_bucket", ba.QUANTITY_BUCKETS
        )
        self.assertEqual([r["dim_value"] for r in rows], ["(All)", "B1", "B2"])
        self.assertEqual(
            set(rows[0]["cells"].keys()),
            set(ba.QUANTITY_BUCKETS) | {"All Bills"},
        )

    def test_every_bucket_cell_has_all_four_kpi_trios(self):
        rows = ba._distribution_rows(
            self._df(), self._df(), "all", "qty_bucket", ba.QUANTITY_BUCKETS
        )
        cell = rows[0]["cells"]["2 Qty Bill"]
        self.assertEqual({k["key"] for k in cell}, {"total_bills", "upt", "abv", "asp"})
        for k in cell:
            self.assertTrue({"lfy", "cfy", "growth_pct"} <= set(k))

    def test_sum_of_bucket_bills_equals_all_bills(self):
        rows = ba._distribution_rows(
            self._df(), self._df(), "all", "qty_bucket", ba.QUANTITY_BUCKETS
        )
        cells = rows[0]["cells"]

        def bills(cmap, bucket):
            return next(k for k in cmap[bucket] if k["key"] == "total_bills")

        summed = sum(bills(cells, b)["cfy"] for b in ba.QUANTITY_BUCKETS)
        self.assertEqual(summed, bills(cells, "All Bills")["cfy"])
        self.assertEqual(bills(cells, "All Bills")["cfy"], 5)

    def test_bucket_ratio_metrics_use_bucket_grain(self):
        rows = ba._distribution_rows(
            self._df(), self._df(), "brand", "qty_bucket", ba.QUANTITY_BUCKETS
        )
        # B1's single >4 bill: qty 5, value 6000.
        b1 = next(r for r in rows if r["dim_value"] == "B1")
        cell = {k["key"]: k for k in b1["cells"][">4 Qty Bill"]}
        self.assertEqual(cell["total_bills"]["cfy"], 1)
        self.assertAlmostEqual(cell["upt"]["cfy"], 5.0)
        self.assertAlmostEqual(cell["abv"]["cfy"], 6000.0)
        self.assertAlmostEqual(cell["asp"]["cfy"], 1200.0)

    def test_zero_lfy_growth_is_none_not_divide_by_zero(self):
        rows = ba._distribution_rows(
            self._df(), self._df().head(0), "all", "qty_bucket", ba.QUANTITY_BUCKETS
        )
        cell = {k["key"]: k for k in rows[0]["cells"]["1 Qty Bill"]}
        self.assertEqual(cell["total_bills"]["lfy"], 0.0)
        self.assertIsNone(cell["total_bills"]["growth_pct"])
        self.assertIsNone(cell["upt"]["lfy"])

    def test_bills_share_percent_present_and_correct(self):
        rows = ba._distribution_rows(
            self._df(), self._df(), "all", "qty_bucket", ba.QUANTITY_BUCKETS
        )
        cell = {k["key"]: k for k in rows[0]["cells"]["1 Qty Bill"]}
        self.assertIn("share_cfy_pct", cell["total_bills"])
        self.assertAlmostEqual(cell["total_bills"]["share_cfy_pct"], 20.0)  # 1 of 5


class InternalBillIdContractTests(unittest.TestCase):
    """The dataset grain: one row per (FY, month, bill_no, store)."""

    def test_dataset_columns_include_canonical_id(self):
        import inspect

        src = inspect.getsource(ba._load_bill_dataset)
        self.assertIn("internal_bill_id", src)
        self.assertIn("bill_key", src)

    def test_entry_point_signature_drops_drill_down(self):
        import inspect

        sig = inspect.signature(ba.run_bill_analysis)
        self.assertIn("hierarchy", sig.parameters)
        self.assertIn("qty_dim", sig.parameters)
        self.assertEqual(sig.parameters["top_n"].default, 25)
        self.assertNotIn("detail_dims", sig.parameters)


if __name__ == "__main__":
    unittest.main()
