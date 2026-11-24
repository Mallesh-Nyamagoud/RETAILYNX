import unittest
from unittest.mock import patch
from app.services import tertiary_summary as summary

class StoreBrandRankTests(unittest.TestCase):
    def result(self, partial=True):
        return {"anchor":2026,"current_fy":2026,"current_fy_partial":partial,
                "totals":{"2026":{"val":500},"2025":{"val":800,"lfytd_val":250}},
                "rows":[{"label":name,"years":{"2026":{"val":value},"2025":{"val":200,"lfytd_val":100}}}
                        for name,value in [("A",200),("B",200),("C",100)]]}

    @patch.object(summary, "report")
    @patch.object(summary, "config")
    def test_bill_value_ties_and_selected_brand(self, config, report):
        config.return_value={"fields":{"store":"store","brand":"brand"},"options":{"brand":["X","Y"]}}
        report.return_value=self.result()
        result=summary.store_brand_rank({"brand":["X"],"state":["KA"]})
        self.assertEqual(result["brands"],["X"])
        self.assertEqual([r["cells"]["X"]["rank"] for r in result["rows"]],[1,1,3])
        self.assertEqual(result["totals"]["X"]["previous"],250)
        self.assertEqual(result["rows"][0]["cells"]["X"]["previous"],100)
        report.assert_called_once_with("store",{"brand":["X"],"state":["KA"]})

    @patch.object(summary, "report")
    @patch.object(summary, "config")
    def test_complete_year_uses_full_previous_value(self, config, report):
        config.return_value={"fields":{"store":"store","brand":"brand"},"options":{"brand":["X"]}}
        report.return_value=self.result(False)
        result=summary.store_brand_rank({})
        self.assertFalse(result["partial"])
        self.assertEqual(result["totals"]["X"]["previous"],800)
        self.assertEqual(result["rows"][0]["cells"]["X"]["previous"],200)

    @patch.object(summary, "config")
    def test_empty_brand_selection(self, config):
        config.return_value={"fields":{"store":"store","brand":"brand"},"options":{"brand":[]}}
        self.assertEqual(summary.store_brand_rank({})["rows"],[])
