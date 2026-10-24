import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import duckdb
import pandas as pd

from app.services import analysis, soh_analysis
from app.services import base_stock_analysis as base_stock


class BaseStockAnalysisTests(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".duckdb")
        os.close(handle)
        os.remove(self.path)
        self.previous_soh_db = base_stock.SOH_DB
        base_stock.SOH_DB = Path(self.path)
        with duckdb.connect(self.path) as con:
            con.execute("""create table data (
                date timestamp, name varchar, brand varchar, code varchar,
                gc varchar, pc9 varchar, season varchar, qty bigint
            )""")
            con.executemany("insert into data values (?, ?, ?, ?, ?, ?, ?, ?)", [
                ("2026-09-01", "STORE A", "BRAND A", "B1", "MENS TOPS", "STYLE-1", "SEASON-1", 99),
                ("2026-10-01", "STORE A", "BRAND A", "B1", "MENS TOPS", "STYLE-1", "SEASON-1", 20),
            ])

    def tearDown(self):
        base_stock.SOH_DB = self.previous_soh_db
        try:
            os.remove(self.path)
        except FileNotFoundError:
            pass

    def _catalog(self):
        return [
            {"column": "retailer_name", "label": "RETAILER NAME", "type": "VARCHAR"},
            {"column": "brand", "label": "BRAND", "type": "VARCHAR"},
            {"column": "store_status", "label": "STORE STATUS", "type": "VARCHAR"},
        ]

    def test_latest_snapshot_stock_maps_to_tertiary_category_and_calculates_measures(self):
        sales = pd.DataFrame([{
            "category": "SHIRTS", "_category_key": "SHIRTS",
            "retailer_name": "STORE A", "total_sales": 100,
            "last_6m_sales": 24,
        }])
        category_map = pd.DataFrame([{
            "store_code": "STORE-A", "brand_code": "B1", "style": "STYLE-1",
            "season": "SEASON-1", "category": "SHIRTS",
        }])
        master = pd.DataFrame([{
            "store_code": "STORE-A", "brand_code": "B1", "retailer_name": "STORE A",
            "brand": "BRAND A", "store_status": "Active",
        }])

        def resolve_store_codes(stock, warnings):
            stock["store_code"] = "STORE-A"
            return stock

        with (
            patch.object(analysis, "get_dimension_catalog", return_value=self._catalog()),
            patch.object(analysis, "_build_filter_sql", return_value=("", [])),
            patch.object(base_stock, "execute", return_value=[(date(2026, 9, 30), date(2026, 4, 1))]),
            patch.object(base_stock, "execute_df", side_effect=[sales, category_map, master]),
            patch.object(soh_analysis, "_store_code_lookup", side_effect=resolve_store_codes),
        ):
            result = base_stock.run_analysis(
                ["retailer_name", "category"],
                {"brand": ["BRAND A"], "retailer_name": ["STORE A"], "store_status": ["Active"]},
            )

        self.assertEqual(result["stock_as_of"], "2026-10-01")
        self.assertEqual(result["last_6m_start"], "2026-04-01")
        self.assertEqual(len(result["rows"]), 1)
        row = result["rows"][0]
        self.assertEqual((row["category"], row["retailer_name"]), ("SHIRTS", "STORE A"))
        self.assertEqual(row["current_stock"], 20)
        self.assertEqual(row["total_sales"], 100)
        self.assertEqual(row["last_6m_sales"], 24)
        self.assertAlmostEqual(row["current_stock_contribution_pct"], 100)
        self.assertAlmostEqual(row["st_pct"], 120)
        self.assertAlmostEqual(row["f4m_requirement"], 16)
        self.assertAlmostEqual(row["requirement"], 4)

    def test_unmatched_styles_keep_stock_visible_under_soh_category(self):
        stock = pd.DataFrame([
            {"store_code": "STORE-A", "brand_code": "B1", "style": "S1", "season": "H1", "soh_category": "MENS TOPS", "current_stock": 10},
            {"store_code": "OTHER-STORE", "brand_code": "B1", "style": "S2", "season": "H1", "soh_category": "MENS TOPS", "current_stock": 5},
            {"store_code": "STORE-A", "brand_code": "B1", "style": "UNSOLD", "season": "H1", "soh_category": "MENS BOTTOMS", "current_stock": 7},
        ])
        category_map = pd.DataFrame([
            {"store_code": "STORE-A", "brand_code": "B1", "style": "S1", "season": "H1", "category": "SHIRTS"},
            {"store_code": "STORE-A", "brand_code": "B1", "style": "S2", "season": "H1", "category": "T-SHIRTS"},
        ])

        result = base_stock._map_stock_categories(stock, category_map)

        self.assertEqual(result["category"].tolist(), ["SHIRTS", "T-SHIRTS", "Unmapped SOH - MENS BOTTOMS"])
        self.assertEqual(result["current_stock"].sum(), 22)


if __name__ == "__main__":
    unittest.main()
