import unittest
from unittest.mock import patch

import duckdb

from app.services import secondary_summary
from app.api.routes import secondary
from app.models.schemas import MonthwiseRequest


class SecondaryTaxableValueTests(unittest.TestCase):
    def test_summary_uses_supplied_taxable_value_for_full_year_and_ytd(self):
        con = duckdb.connect()
        con.execute("CREATE SCHEMA secondary_data")
        con.execute("CREATE SCHEMA store_master")
        con.execute("CREATE TABLE store_master.store_details (adonis_store_code VARCHAR, brand_code VARCHAR, brand VARCHAR)")
        con.execute("INSERT INTO store_master.store_details VALUES ('A1', 'B1', 'Example')")
        con.execute("CREATE TABLE secondary_data.data (adonis_store_code VARCHAR, brand_code VARCHAR, bill_date DATE, qty INTEGER, value DOUBLE, tax DOUBLE, taxable_value DOUBLE)")
        con.execute("INSERT INTO secondary_data.data VALUES ('A1','B1','2025-05-01',2,120,20,75), ('A1','B1','2026-05-01',3,240,40,150)")
        cfg = {"years": [2025, 2026], "current_fy": 2026, "current_fy_partial": True}
        try:
            with patch.object(secondary_summary, '_fields', return_value={"brand": "brand"}), patch.object(secondary_summary, 'config', return_value=cfg), patch.object(secondary_summary, '_anchor_and_months', return_value=(2026, [], [4, 5])), patch.object(secondary_summary, 'execute_df', side_effect=lambda sql, params: con.execute(sql, params).df()):
                result = secondary_summary._report_cached.__wrapped__('brand', (), None)
            for year, expected in [('2025', 75), ('2026', 150)]:
                self.assertEqual(result['totals'][year]['val'], expected)
                self.assertEqual(result['totals'][year]['lfytd_val'], expected)
                self.assertEqual(result['rows'][0]['years'][year]['val'], expected)
        finally:
            con.close()

    def test_pivot_and_monthwise_use_supplied_taxable_value(self):
        self.assertEqual(secondary.FACT.val_expr, 'taxable_value')
        with patch.object(secondary.analysis, 'run_monthwise', return_value={}) as run:
            secondary.monthwise(MonthwiseRequest(dimensions=[], filters={}))
        self.assertEqual(run.call_args.kwargs['measures'][1]['expr'], 'taxable_value')
