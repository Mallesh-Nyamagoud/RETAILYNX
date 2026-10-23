"""SOH month-to-month calculation regression cases."""
import os
import tempfile
import unittest
from unittest.mock import patch

import duckdb
import pandas as pd

from app.services import soh_analysis


class SohAnalysisLogicTests(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".duckdb")
        os.close(handle)
        os.remove(self.path)
        self.previous_db = soh_analysis.SOH_DB
        soh_analysis.SOH_DB = type(self.previous_db)(self.path)
        with duckdb.connect(self.path) as con:
            con.execute("""create table data (
                date timestamp, name varchar, brand varchar, code varchar,
                gc varchar, pc9 varchar, season varchar, correct_size varchar,
                qty bigint, mrp double
            )""")
            rows = [
                ("2026-07-01", "STORE A", "BRAND", "B1", "CAT", "STYLE-1", "SEASON-1", "S", 5, 100.0),
                ("2026-07-01", "STORE A", "BRAND", "B1", "CAT", "STYLE-1", "SEASON-1", "S", 1, 100.0),
                ("2026-07-01", "STORE A", "BRAND", "B1", "CAT", "STYLE-1", "SEASON-1", "M", 2, 100.0),
                ("2026-09-01", "STORE A", "BRAND", "B1", "CAT", "STYLE-1", "SEASON-1", "S", 1, 100.0),
                ("2026-09-01", "STORE A", "BRAND", "B1", "CAT", "STYLE-1", "SEASON-1", "S", 1, 100.0),
                ("2026-09-01", "STORE A", "BRAND", "B1", "CAT", "STYLE-1", "SEASON-1", "M", 1, 100.0),
                ("2026-07-01", "STORE B", "BRAND", "B1", "CAT", "STYLE-1", "SEASON-1", "M", 4, 100.0),
                ("2026-09-01", "STORE B", "BRAND", "B1", "CAT", "STYLE-1", "SEASON-1", "M", 2, 100.0),
            ]
            con.executemany("insert into data values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)

    def tearDown(self):
        soh_analysis.SOH_DB = self.previous_db
        try:
            os.remove(self.path)
        except FileNotFoundError:
            pass

    def test_filter_options_query_returns_values_for_all_dimensions(self):
        options = soh_analysis.get_filter_options()
        self.assertEqual(options["store"], ["STORE A", "STORE B"])
        self.assertEqual(options["brand"], ["BRAND"])
        self.assertEqual(options["category"], ["CAT"])
        self.assertEqual(options["style"], ["STYLE-1"])
        self.assertEqual(options["season"], ["SEASON-1"])

    def test_monthly_style_sales_returns_stock_and_size_breakdown(self):
        tertiary = pd.DataFrame([
            ["STORE A", "STORE-A", "B1", "STYLE-1", "OLD-SEASON", 2],
            ["STORE B", "STORE-B", "B1", "STYLE-1", "SEASON-1", 4],
        ], columns=["store", "store_code", "brand_code", "style", "season", "tertiary_net_sales"])
        transfers = pd.DataFrame([
            ["STORE A", "STORE-A", "B1", "STYLE-1", "OLD-SEASON", 3, -1],
            ["STORE B", "STORE-B", "B1", "STYLE-1", "SEASON-1", 0, 0],
        ], columns=["store", "store_code", "brand_code", "style", "season", "secondary_transfer_qty", "secondary_return_qty"])
        mapping = pd.DataFrame([
            ["STORE A", "B1", "STORE-A"], ["STORE B", "B1", "STORE-B"],
        ], columns=["master_store", "brand_code", "store_code"])
        with patch.object(soh_analysis, "execute_df", side_effect=[mapping, tertiary, transfers]) as execute:
            result = soh_analysis.get_summary("2026-07-01", "2026-09-01")
        self.assertIn("store_master.store_details", execute.call_args_list[0].args[0])
        self.assertIn("tertiary_data.data", execute.call_args_list[1].args[0])
        self.assertIn("sum(qty)", execute.call_args_list[1].args[0])
        self.assertNotIn("return_qty", execute.call_args_list[1].args[0])
        self.assertIn("qty > 0", execute.call_args_list[2].args[0])
        self.assertIn("qty < 0", execute.call_args_list[2].args[0])
        self.assertIn("secondary_data.data", execute.call_args_list[2].args[0])

        self.assertEqual(len(result["rows"]), 2)
        store_a = next(row for row in result["rows"] if row["store"] == "STORE A")
        store_b = next(row for row in result["rows"] if row["store"] == "STORE B")
        self.assertEqual((store_a["category"], store_a["style"], store_a["season"]), ("CAT", "STYLE-1", "SEASON-1"))
        self.assertEqual((store_a["opening_soh"], store_a["tertiary_net_sales"]), (8, 2))
        self.assertEqual(store_a["total_style_net_sales"], 6)
        self.assertEqual(store_a["ending_soh"], 3)
        self.assertEqual(store_a["end_soh_sizewise"], "M-1, S-2")
        self.assertEqual((store_a["secondary_transfer_qty"], store_a["secondary_return_qty"]), (3, -1))
        self.assertAlmostEqual(store_a["st_pct"], 0.2)
        self.assertAlmostEqual(store_a["opening_soh_clearance"], 0.25)
        self.assertEqual(store_b["total_style_net_sales"], 6)
        self.assertAlmostEqual(store_b["st_pct"], 1.0)

    def test_same_snapshot_period_has_zero_intervening_sales(self):
        mapping = pd.DataFrame([
            ["STORE A", "B1", "STORE-A"], ["STORE B", "B1", "STORE-B"],
        ], columns=["master_store", "brand_code", "store_code"])
        empty_sales = pd.DataFrame(columns=["store", "brand_code", "style", "season", "tertiary_net_sales"])
        empty_transfers = pd.DataFrame(columns=["store", "brand_code", "style", "season", "secondary_transfer_qty", "secondary_return_qty"])
        with patch.object(soh_analysis, "execute_df", side_effect=[mapping, empty_sales, empty_transfers]):
            result = soh_analysis.get_summary("2026-07-01", "2026-07-01")
        row = next(row for row in result["rows"] if row["store"] == "STORE A")
        self.assertEqual(row["tertiary_net_sales"], 0)
        self.assertEqual(row["opening_soh"], row["ending_soh"])

    def test_missing_sales_source_keeps_stock_and_warns(self):
        mapping = pd.DataFrame([
            ["STORE A", "B1", "STORE-A"], ["STORE B", "B1", "STORE-B"],
        ], columns=["master_store", "brand_code", "store_code"])
        empty_transfers = pd.DataFrame(columns=["store", "brand_code", "style", "season", "secondary_transfer_qty", "secondary_return_qty"])
        with patch.object(soh_analysis, "execute_df", side_effect=[mapping, RuntimeError("source unavailable"), empty_transfers]):
            result = soh_analysis.get_summary("2026-07-01", "2026-09-01")
        self.assertTrue(result["rows"])
        self.assertEqual(result["rows"][0]["tertiary_net_sales"], 0)
        self.assertTrue(any("could not be loaded" in warning for warning in result["warnings"]))
        self.assertEqual(result["rows"][0]["secondary_transfer_qty"], 0)


if __name__ == "__main__":
    unittest.main()
