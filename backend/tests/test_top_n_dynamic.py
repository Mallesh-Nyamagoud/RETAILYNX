"""Execute the production Top N SQL against mixed-brand, multi-year bills."""
import unittest
from unittest.mock import patch
import duckdb
from app.services import top_bills as top, bill_kpi as bk
from app.services.analysis import FactSpec

FACT = FactSpec(schema="tertiary_data", table="data", date_column="date", qty_expr="qty", val_expr="bill_val")

class DynamicTopBillsTests(unittest.TestCase):
    def setUp(self):
        self.con = duckdb.connect()
        self.con.execute("CREATE SCHEMA tertiary_data; CREATE SCHEMA store_master")
        self.con.execute("CREATE TABLE store_master.store_details(adonis_store_code VARCHAR, brand_code VARCHAR, brand VARCHAR, retailer_name VARCHAR, department VARCHAR, state VARCHAR)")
        self.con.execute("INSERT INTO store_master.store_details VALUES ('S','B','BLACKBERRYS','Retailer S','Mens','KA'), ('S','U','USPA','Retailer S','Mens','KA'), ('T','B','BLACKBERRYS','Retailer T','Mens','MH'), ('T','U','USPA','Retailer T','Kids','MH')")
        self.con.execute("CREATE TABLE tertiary_data.data(date DATE, adonis_store_code VARCHAR, brand_code VARCHAR, brand VARCHAR, bill_no VARCHAR, qty DOUBLE, bill_val DOUBLE)")
        self.con.execute("INSERT INTO tertiary_data.data VALUES ('2026-06-20','S','B','B','1',5,500), ('2026-06-20','S','U','U','1',4,800), ('2026-06-21','T','B','B','2',6,600), ('2023-01-02','S','B','B','old',7,2000), ('2025-05-02','T','U','U','other',2,900), ('2026-06-22','S','B','B','NA',99,99999), ('2026-06-22','S','B','B','',99,99999)")
        self.catalog = [{"column": col, "label": col} for col in ['brand','retailer_name','department','state']]
        bk._bill_kpi_cached.cache_clear()
        self.stack = []
        for obj, name, kwargs in [(top, 'execute_df', {"side_effect": lambda sql, params: self.con.execute(sql, params).df()}), (top, 'column_exists', {"return_value": True}), (top, 'get_dimension_catalog', {"return_value": self.catalog})]:
            context = patch.object(obj, name, **kwargs); context.start(); self.stack.append(context)

    def tearDown(self):
        for context in reversed(self.stack): context.stop()
        bk._bill_kpi_cached.cache_clear()
        self.con.close()

    def run_top(self, filters=None, n=25, dates=None):
        return bk.run_bill_kpi_analysis(FACT, filters or {}, ["brand"], dates, n, top_bills_only=True)["top_bills"]["overall"]

    def test_no_filters_includes_all_years_and_brands(self):
        rows = self.run_top()
        self.assertEqual([r['bill_val'] for r in rows], [2000,1300,900,600])
        self.assertEqual(rows[0]['bill_date'], '2023-01-02')
        self.assertEqual(len(rows[1]['brand_contributions']), 2)

    def test_blackberry_recomputes_mixed_bill_and_rank(self):
        rows = self.run_top({'brand':['BLACKBERRYS']})
        self.assertEqual([r['bill_val'] for r in rows], [2000,600,500])
        self.assertEqual(rows[-1]['qty'], 5)
        self.assertTrue(all(p['brand']=='BLACKBERRYS' for r in rows for p in r['brand_contributions']))
        self.assertTrue(all(r['brand_contributions'][0]['contribution_pct']==100 for r in rows))

    def test_non_dominant_brand_still_matches(self):
        rows = self.run_top({'brand':['BLACKBERRYS'], 'adonis_store_code':['S'], 'fy_label':['FY2026-27']})
        self.assertEqual([r['bill_val'] for r in rows], [500])

    def test_brand_store_month_fy_intersection(self):
        rows = self.run_top({'brand':['BLACKBERRYS'], 'state':['KA'], 'month_num':['6'], 'fy_label':['FY2026-27']})
        self.assertEqual([r['bill_val'] for r in rows], [500])
        self.assertEqual(self.run_top({'brand':['BLACKBERRYS'], 'department':['Kids']}), [])

    def test_multiple_fiscal_years_and_brands(self):
        rows = self.run_top({'fy_label':['FY2022-23','FY2025-26'], 'brand':['BLACKBERRYS','USPA']})
        self.assertEqual([r['bill_val'] for r in rows], [2000,900])

    def test_explicit_dates_only_restrict_requested_window(self):
        rows = self.run_top(dates={'start':'2026-06-20','end':'2026-06-20'})
        self.assertEqual([r['bill_val'] for r in rows], [1300])

    def test_reset_and_changing_filters_do_not_reuse_wrong_payload(self):
        self.assertEqual(self.run_top({'brand':['USPA']})[0]['bill_val'], 900)
        self.assertEqual(self.run_top({'brand':['BLACKBERRYS']})[0]['bill_val'], 2000)
        self.assertEqual(len(self.run_top()), 4)
        self.assertEqual(len(self.run_top(n=1)), 1)

    def test_duplicate_master_does_not_multiply_sales(self):
        self.con.execute("INSERT INTO store_master.store_details SELECT * FROM store_master.store_details WHERE brand_code='B'")
        self.assertEqual([r['bill_val'] for r in self.run_top()], [2000,1300,900,600])

    def test_unknown_and_sql_injection_values(self):
        with self.assertRaises(ValueError): self.run_top({'unknown':['x']})
        self.assertEqual(self.run_top({'brand':["BLACKBERRYS' OR 1=1 --"]}), [])

    def test_zero_values_missing_master_and_null_dates(self):
        self.con.execute("INSERT INTO tertiary_data.data VALUES ('2026-06-23','X','X','Unmapped Brand','zero',NULL,NULL), (NULL,'S','B','B','nodate',100,999999)")
        rows = self.run_top({'brand':['Unmapped Brand']})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['bill_val'], 0)
        self.assertEqual(rows[0]['qty'], 0)
        self.assertEqual(rows[0]['brand_contributions'][0]['contribution_pct'], 0)
        self.assertEqual(len(self.run_top()), 5)

    def test_values_and_contributions_reconcile(self):
        for filters in ({}, {'brand':['BLACKBERRYS']}, {'department':['Mens']}, {'state':['MH']}):
            for row in self.run_top(filters):
                self.assertAlmostEqual(sum(p['bill_val'] for p in row['brand_contributions']), row['bill_val'])
                self.assertAlmostEqual(sum(p['contribution_pct'] for p in row['brand_contributions']), 100)

if __name__ == '__main__': unittest.main()
