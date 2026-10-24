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
                date timestamp, "Store Name" varchar, brand varchar, "Brand Code" varchar,
                gc varchar, "Style Code" varchar, season varchar, quantity bigint,
                "Category Group" varchar, category varchar, subcategory varchar
            )""")
            con.executemany("insert into data values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [
                ("2026-09-01", "STORE A", "BRAND A", "B1", "MENS TOPS", "STYLE-1", "SEASON-1", 99, "TOPS", None, None),
                ("2026-10-01", "STORE A", "BRAND A", "B1", "MENS TOPS", "STYLE-1", "SEASON-1", 20, "TOPS", None, None),
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
            "category_group": "TOPS", "subcategory": "DENIM",
            "retailer_name": "STORE A", "total_sales": 100,
            "last_6m_sales": 24,
        }])
        category_map = pd.DataFrame([{
            "store_code": "STORE-A", "brand_code": "B1", "style": "STYLE-1",
            "season": "SEASON-1", "category_group": "TOPS",
            "category": "SHIRTS", "subcategory": "DENIM",
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
            patch.object(base_stock, "execute_df", side_effect=[sales, category_map, master]) as execute_df_mock,
            patch.object(soh_analysis, "_store_code_lookup", side_effect=resolve_store_codes),
        ):
            result = base_stock.run_analysis(
                ["category_group", "category", "subcategory", "retailer_name"],
                {
                    "brand": ["BRAND A"], "retailer_name": ["STORE A"],
                    "store_status": ["Active"], "category_group": ["TOPS"],
                    "season": ["SEASON-1"],
                },
            )

        sales_query, sales_params = execute_df_mock.call_args_list[0].args
        self.assertIn('f."CG"', sales_query)
        self.assertIn('f."SEASON"', sales_query)
        self.assertEqual(sales_params[-2:], ["TOPS", "SEASON-1"])
        self.assertEqual(result["stock_as_of"], "2026-10-01")
        self.assertEqual(result["last_6m_start"], "2026-04-01")
        self.assertEqual(len(result["rows"]), 1)
        row = result["rows"][0]
        self.assertEqual(
            (row["category_group"], row["category"], row["subcategory"], row["retailer_name"]),
            ("TOPS", "SHIRTS", "DENIM", "STORE A"),
        )
        self.assertEqual(row["current_stock"], 20)
        self.assertEqual(row["total_sales"], 100)
        self.assertEqual(row["last_6m_sales"], 24)
        self.assertAlmostEqual(row["current_stock_contribution_pct"], 100)
        self.assertAlmostEqual(row["st_pct"], 120)
        self.assertAlmostEqual(row["f4m_requirement"], 16)
        self.assertAlmostEqual(row["requirement"], 4)

    def test_soh_category_group_is_preserved_while_missing_subcategory_is_filled(self):
        stock = pd.DataFrame([{
            "store_code": "STORE-A", "brand_code": "B1", "style": "S1",
            "season": "H1", "soh_category": "MENS TOPS", "current_stock": 8,
            "category_group": "TOPS", "category": "SHIRTS", "subcategory": None,
        }])
        category_map = pd.DataFrame([{
            "store_code": "STORE-A", "brand_code": "B1", "style": "S1",
            "season": "H1", "category_group": "OTHER", "category": "SHIRTS",
            "subcategory": "DENIM",
        }])

        result = base_stock._map_stock_categories(stock, category_map)

        self.assertEqual(result.loc[0, "category_group"], "TOPS")
        self.assertEqual(result.loc[0, "category"], "SHIRTS")
        self.assertEqual(result.loc[0, "subcategory"], "DENIM")

    def test_unmatched_styles_keep_stock_visible_under_soh_category(self):
        stock = pd.DataFrame([
            {"store_code": "STORE-A", "brand_code": "B1", "style": "S1", "season": "H1", "soh_category": "MENS TOPS", "current_stock": 10},
            {"store_code": "OTHER-STORE", "brand_code": "B1", "style": "S2", "season": "H1", "soh_category": "MENS TOPS", "current_stock": 5},
            {"store_code": "STORE-A", "brand_code": "B1", "style": "UNSOLD", "season": "H1", "soh_category": "MENS BOTTOMS", "current_stock": 7},
        ])
        category_map = pd.DataFrame([
            {"store_code": "STORE-A", "brand_code": "B1", "style": "S1", "season": "H1", "category_group": "DENIM", "category": "SHIRTS", "subcategory": "MENS"},
            {"store_code": "STORE-A", "brand_code": "B1", "style": "S2", "season": "H1", "category_group": "DENIM", "category": "T-SHIRTS", "subcategory": "MENS"},
        ])

        result = base_stock._map_stock_categories(stock, category_map)

        self.assertEqual(result["category"].tolist(), ["SHIRTS", "T-SHIRTS", "Unmapped SOH - MENS BOTTOMS"])
        self.assertEqual(result["category_group"].tolist(), ["DENIM", "DENIM", None])
        self.assertEqual(result["subcategory"].tolist(), ["MENS", "MENS", None])
        self.assertEqual(result["current_stock"].sum(), 22)


if __name__ == "__main__":
    unittest.main()
