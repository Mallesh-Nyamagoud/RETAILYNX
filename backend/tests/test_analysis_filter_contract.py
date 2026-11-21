"""SQL-backed filter contract checks across secondary/tertiary analysis paths."""
import unittest
from contextlib import ExitStack
from unittest.mock import patch
import duckdb
from app.services import analysis as a, secondary_summary as ss, tertiary_summary as ts
from app.api.routes import secondary, tertiary
from app.models.schemas import MonthwiseRequest

FIELDS = {"store":"retailer_name", "department":"department", "store_status":"store_status", "store_type":"store_type", "brand":"brand", "state":"state", "group":"group"}
VALUES = {"store":"Retailer 1", "department":"Mens", "store_status":"Active", "store_type":"COCO", "brand":"Alpha", "state":"KA", "group":"G1"}

class AnalysisFilterContractTests(unittest.TestCase):
    def setUp(self):
        self.con = duckdb.connect()
        self.con.execute("CREATE SCHEMA store_master; CREATE SCHEMA tertiary_data; CREATE SCHEMA secondary_data")
        self.con.execute('CREATE TABLE store_master.store_details(adonis_store_code VARCHAR, brand_code VARCHAR, retailer_name VARCHAR, department VARCHAR, store_status VARCHAR, store_type VARCHAR, brand VARCHAR, state VARCHAR, "group" VARCHAR)')
        master = [('S1','B1','Retailer 1','Mens','Active','COCO','Alpha','KA','G1'),('S1','B2','Retailer 1','Kids','Active','COCO','Beta','KA','G1'),('S2','B1','Retailer 2','Mens','Inactive','FOFO','Alpha','MH','G2'),('S2','B2','Retailer 2','Kids','Inactive','FOFO','Beta','MH','G2')]
        self.con.executemany('INSERT INTO store_master.store_details VALUES (?,?,?,?,?,?,?,?,?)', master)
        self.con.execute('CREATE TABLE tertiary_data.data(adonis_store_code VARCHAR, brand_code VARCHAR, date DATE, qty DOUBLE, mrp_value DOUBLE, discount DOUBLE, bill_val DOUBLE)')
        self.con.execute('CREATE TABLE secondary_data.data(adonis_store_code VARCHAR, brand_code VARCHAR, bill_date DATE, qty DOUBLE, taxable_value DOUBLE)')
        for year in [2025, 2026]:
            for month in [5, 6]:
                for index, row in enumerate(master):
                    qty = (index+1)*(year-2024)*(month-4)
                    self.con.execute('INSERT INTO tertiary_data.data VALUES (?,?,?,?,?,?,?)', [row[0],row[1],f'{year}-{month:02d}-15',qty,qty*125,qty*25,qty*100])
                    self.con.execute('INSERT INTO secondary_data.data VALUES (?,?,?,?,?)', [row[0],row[1],f'{year}-{month:02d}-15',qty,qty*100])
        self.stack = ExitStack()
        def execute(sql, params=None): return self.con.execute(sql, params or []).fetchall()
        def frame(sql, params=None): return self.con.execute(sql, params or []).df()
        def exists(schema,table,column): return column in [r[0] for r in self.con.execute(f'DESCRIBE {schema}.{table}').fetchall()]
        self.stack.enter_context(patch.object(a,'execute',side_effect=execute))
        self.stack.enter_context(patch.object(a,'execute_df',side_effect=frame))
        self.stack.enter_context(patch.object(a,'column_exists',side_effect=exists))
        self.stack.enter_context(patch.object(a,'get_dimension_catalog',return_value=[{'column':c,'label':c} for c in FIELDS.values()]))
        for service in [ss,ts]:
            self.stack.enter_context(patch.object(service,'execute',side_effect=execute))
            self.stack.enter_context(patch.object(service,'execute_df',side_effect=frame))
            self.stack.enter_context(patch.object(service,'_fields',return_value=FIELDS))
        self.clear_caches()

    def clear_caches(self):
        for fn in [a._global_max_date_cached,a._global_min_date_cached,a._monthwise_cached,a._monthwise_rows_cached,a._pivot_cached,a._apm_month_map_cached,ss._config_cached,ts._config_cached,ss._report_cached,ts._report_cached]: fn.cache_clear()

    def tearDown(self):
        self.stack.close(); self.clear_caches(); self.con.close()

    def test_all_ui_filters_match_physical_columns_in_both_monthwise_routes(self):
        for route in [secondary,tertiary]:
            for key,value in VALUES.items():
                with self.subTest(route=route.__name__,filter=key):
                    alias=route.monthwise(MonthwiseRequest(filters={key:[value]}))
                    canonical=route.monthwise(MonthwiseRequest(filters={FIELDS[key]:[value]}))
                    self.assertEqual(alias,canonical)
                    self.assertTrue(alias['rows'])

    def test_combined_filters_and_reset_work_for_both_routes(self):
        for route in [secondary,tertiary]:
            filters={key:[value] for key,value in VALUES.items()}
            result=route.monthwise(MonthwiseRequest(filters=filters))
            self.assertTrue(result['rows'])
            empty=route.monthwise(MonthwiseRequest(filters={'store':['Retailer 1'],'state':['MH']}))
            self.assertEqual(empty['rows'],[])
            self.assertNotEqual(result['rows'],route.monthwise(MonthwiseRequest(filters={}))['rows'])
            self.assertEqual(result,route.monthwise(MonthwiseRequest(filters=filters)))

    def test_selected_month_and_fy_in_both_routes_keep_existing_comparison_math(self):
        for route in [secondary,tertiary]:
            result=route.monthwise(MonthwiseRequest(filters={'store':['Retailer 1'],'month':['5'],'fy':['2025']}))
            self.assertEqual(result['fy_context']['current_fy_label'],'FY2025-26')
            self.assertEqual(len(result['months']),1)
            row=result['rows'][0]
            if route is tertiary:
                self.assertEqual(row['qty'],3)
                self.assertEqual(row['bill_val'],300)
                self.assertEqual(row['discount_pct'],20)
            else:
                self.assertEqual(next(value for key,value in row.items() if key.endswith('__cfy_qty')),3)
                self.assertEqual(next(value for key,value in row.items() if key.endswith('__cfy_val')),300)

    def test_current_monthwise_totals_growth_and_ratios_match_source(self):
        result=tertiary.monthwise(MonthwiseRequest(filters={'store':['Retailer 1'],'month':['5']}))
        row=result['rows'][0]
        self.assertEqual(row['qty'],6)
        self.assertEqual(row['qty_ly'],3)
        self.assertEqual(row['qty_growth_pct'],100)
        self.assertEqual(row['bill_val'],600)
        self.assertEqual(row['bill_val_growth_pct'],100)
        self.assertEqual(row['discount_pct'],20)
        self.assertEqual(row['ms_cum_pct'],100)

    def test_pivot_filter_aliases_preserve_every_existing_metric(self):
        for route in [secondary,tertiary]:
            for key,value in VALUES.items():
                with self.subTest(route=route.__name__,filter=key):
                    self.assertEqual(a.run_pivot(route.FACT,['brand'],{key:[value]}),a.run_pivot(route.FACT,['brand'],{FIELDS[key]:[value]}))

    def test_summary_and_dependent_options_respect_every_filter(self):
        for service in [ss,ts]:
            for key,value in VALUES.items():
                with self.subTest(service=service.__name__,filter=key):
                    result=service.report('brand',{key:[value]})
                    self.assertTrue(result['rows'])
                    field=FIELDS[key]
                    expected=self.con.execute(f'SELECT SUM(f.qty) FROM {service.FACT} f {service.JOIN} WHERE dim."{field}"=? AND year(f.'+('date' if service is ts else 'bill_date')+')=2026',[value]).fetchone()[0]
                    self.assertEqual(result['totals']['2026']['qty'],expected)
            config=service.config({'store':['Retailer 1'],'brand':['Alpha']})
            self.assertEqual(config['options']['state'],['KA'])
            self.assertEqual(config['options']['brand'],['Alpha','Beta'])
            self.assertEqual(service.report('brand',{'store':['Retailer 1'],'state':['MH']})['rows'],[])

    def test_multi_select_filters_use_union_within_field_and_intersection_across_fields(self):
        for route in [secondary,tertiary]:
            result=route.monthwise(MonthwiseRequest(filters={'store':['Retailer 1','Retailer 2'],'brand':['Alpha'],'month':['5','6']}))
            self.assertEqual(len(result['months']),2)
            if route is tertiary:
                total=sum(row['qty'] or 0 for row in result['rows'])
            else:
                total=sum(value or 0 for row in result['rows'] for key,value in row.items() if key.endswith('__cfy_qty'))
            self.assertEqual(total,24)

    def test_filter_aliases_follow_available_schema_fallbacks(self):
        available={'adonis_store_code','brand_code','state_name','store_group'}
        with patch.object(a,'column_exists',side_effect=lambda schema,table,col:col in available):
            sql,params=a._build_filter_sql({'store':['S1'],'brand':['B1'],'state':['KA'],'group':['G1']})
        for column in available:self.assertIn('dim."'+column+'" IN (?)',sql)
        self.assertEqual(params,['S1','B1','KA','G1'])

    def test_empty_unknown_and_quoted_filter_values(self):
        self.assertEqual(a._build_filter_sql({'store':[]}),('',[]))
        with self.assertRaises(ValueError):a._build_filter_sql({'not_a_column':['x']})
        for route in [secondary,tertiary]:
            self.assertEqual(route.monthwise(MonthwiseRequest(filters={'store':["x' OR 1=1 --"]}))['rows'],[])

class CategoryBrandFilterContractTests(unittest.TestCase):
    def test_month_fy_and_brand_filters_reach_category_brand_aggregates(self):
        import pandas as pd
        from datetime import date
        from app.services import category_analysis as ca
        from app.services.fy import build_fy_context
        frame = pd.DataFrame({
            "tx_date": pd.to_datetime(['2025-05-15','2025-06-15','2026-05-15','2026-06-15','2026-05-15']),
            ca.CATEGORY_COL: ['TOP']*5, "brand": ['Alpha']*4+['Beta'],
            "qty_val": [2,3,4,6,99], "val_val": [200,300,400,600,9900],
            "mrp_val": [250,375,500,750,12375],
        })
        ca._cached_category_brand_payload.cache_clear()
        try:
            with patch.object(ca,'get_category_meta',return_value={"categories":["TOP"]}), patch.object(ca,'_fy_context',return_value=build_fy_context(date(2026,6,15))), patch.object(ca,'_load_facts',return_value=frame):
                filtered=ca.run_category_brand_analysis({'brand':['Alpha'],'month':['5']})
                self.assertEqual(len(filtered['rows']),1)
                self.assertEqual(filtered['rows'][0]['tfy_qty'],4)
                self.assertEqual(filtered['rows'][0]['lfy_qty'],2)
                historical=ca.run_category_brand_analysis({'brand':['Alpha'],'month':['5'],'fy':['2025']})
                self.assertEqual(historical['fy_context']['current_fy_label'],'FY2025-26')
                self.assertEqual(historical['rows'][0]['tfy_qty'],2)
                empty=ca.run_category_brand_analysis({'brand':['Alpha'],'fy':['2023']})
                self.assertEqual(empty['rows'],[])
                unfiltered=ca.run_category_brand_analysis({'brand':['Alpha']})
                self.assertEqual(unfiltered['rows'][0]['tfy_qty'],10)
        finally:
            ca._cached_category_brand_payload.cache_clear()


if __name__=='__main__':unittest.main()
