"""Top N regressions: filtering, ranking, brand names and cache freshness."""
import unittest
from unittest.mock import patch
import pandas as pd
from app.services import bill_analysis as ba, bill_kpi as bk
from app.services.analysis import FactSpec

FACT = FactSpec(schema="tertiary_data", table="data", date_column="date", qty_expr="qty", val_expr="bill_val")

class TopNRegressionTests(unittest.TestCase):
    def setUp(self):
        bk._bill_kpi_cached.cache_clear()
        self.df = pd.DataFrame({
            "internal_bill_id": ["S-FY25-04-1", "T-FY25-04-2", "S-FY25-05-3", "S-FY24-04-4"],
            "bill_date": pd.to_datetime(["2025-04-01", "2025-04-02", "2025-05-01", "2024-04-01"]),
            "fy_label": ["FY2025-26"] * 3 + ["FY2024-25"],
            "month_num": [4, 4, 5, 4], "month": ["Apr", "Apr", "May", "Apr"],
            "adonis_store_code": ["S", "T", "S", "S"], "brand": ["Alpha", "Beta", "Alpha", "Alpha"],
            "retailer_name": ["R", "Q", "R", "R"], "qty": [1, 2, 3, 4],
            "bill_val": [100., 500., 300., 80.],
        })

    def tearDown(self):
        bk._bill_kpi_cached.cache_clear()

    def test_numeric_month_and_combined_filters(self):
        with patch.object(ba, "_load_bill_dataset", return_value=self.df):
            for value in (4, "4"):
                result = ba._filtered_bills(FACT, {"month_num": [value], "brand": ["Alpha"]})
                self.assertEqual(list(result.bill_val), [100., 80.])
            self.assertTrue(ba._filtered_bills(FACT, {"month_num": ["invalid"]}).empty)
            self.assertEqual(len(ba._filtered_bills(FACT, {})), 4)

    def test_month_filter_updates_other_slicer_options(self):
        bk._slicers_cached.cache_clear()
        with patch.object(bk, "_load_dataset", return_value=self.df), patch.object(bk, "bill_dimensions", return_value=[{"column": "brand", "label": "Brand"}]):
            slicers = bk.get_slicers(FACT, {"month_num": ["5"]})
        self.assertEqual(slicers["brand"], ["Alpha"])
        bk._slicers_cached.cache_clear()

    def test_top_only_filter_changes_dates_and_n(self):
        with patch.object(ba, "_load_bill_dataset", return_value=self.df), patch.object(bk, "bill_dimensions", return_value=[{"column": "brand", "label": "Brand"}]), patch.object(bk, "_contrib_cache", return_value={}), patch.object(bk, "_dimension_summary_rows", side_effect=AssertionError("hidden summary computed")), patch.object(bk, "_distribution_rows", side_effect=AssertionError("hidden distributions computed")):
            def run(filters, n=25):
                return bk.run_bill_kpi_analysis(FACT, filters, ["brand"], {"start": "2025-04-01", "end": "2025-05-31"}, n, top_bills_only=True)["top_bills"]
            self.assertEqual([r["bill_val"] for r in run({}, 2)["cfy"]], [500., 300.])
            filtered = run({"month_num": ["4"], "brand": ["Alpha"]})
            self.assertEqual([r["bill_val"] for r in filtered["cfy"]], [100.])
            self.assertEqual([r["bill_val"] for r in filtered["lfy"]], [80.])
            self.assertEqual(run({"brand": ["missing"]})["cfy"], [])
            self.assertEqual(len(run({}, 1)["cfy"]), 1)
            self.assertEqual(len(run({}, 999)["cfy"]), 3)

    def test_rank_ties_nan_and_negative_values(self):
        df = self.df.copy()
        df["bill_val"] = [100., 100., float("nan"), -10.]
        result = bk._top_bill_rows(df, 10)
        self.assertEqual([r["rank"] for r in result], [1, 2, 3])
        self.assertEqual([r["bill_val"] for r in result], [100., 100., -10.])
        self.assertEqual(result[0]["internal_bill_id"], "S-FY25-04-1")
        self.assertEqual(bk._top_bill_rows(df, 0), [])

    def test_brand_names_resolved_without_multiplying_values(self):
        fine = pd.DataFrame({"fy_short": ["FY25", "FY25"], "month_num": [4, 4], "bill_no": ["1", "1"], "store_code": ["S", "S"], "brand_code": ["A", "B"], "brand_name": ["A", None], "bill_val": [75., 25.]})
        master = pd.DataFrame({"brand_code": ["A", "A", "B"], "brand": ["Alpha", "Alpha", "Beta"]})
        with patch.object(bk, "_load_dataset", return_value=self.df), patch.object(bk, "column_exists", return_value=True), patch.object(bk, "execute_df", side_effect=[fine, master]):
            parts = bk._build_contributions(FACT)["S-FY25-04-1"]
        self.assertEqual([p["brand"] for p in parts], ["Alpha", "Beta"])
        self.assertEqual([p["contribution_pct"] for p in parts], [75., 25.])

    def test_contribution_cache_rebuilds_on_data_change_even_if_empty(self):
        with patch.object(bk, "_CONTRIB_FACT", None), patch.object(bk, "_CONTRIB_TOKEN", None), patch.object(bk, "_CONTRIB_MAP", {}), patch.object(bk, "cache_token", side_effect=[(1,), (1,), (2,)]), patch.object(bk, "_build_contributions", return_value={}) as build:
            bk._contrib_cache(FACT)
            bk._contrib_cache(FACT, {"brand": ["Alpha"]})
            self.assertEqual(build.call_count, 1)
            bk._contrib_cache(FACT)
            self.assertEqual(build.call_count, 2)

if __name__ == "__main__":
    unittest.main()
