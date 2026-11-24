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
        self.assertEqual([r["cells"]["X"]["rank"] for r in result["rows"]],[1,1,1])
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

    @patch.object(summary, "report")
    @patch.object(summary, "config")
    def test_store_ranks_contributions_and_overall_sort(self, config, report):
        config.return_value = {"fields": {"store":"store", "brand":"brand"}, "options":{"brand":["X","Y","Z"]}}
        def brand_result(dimension, filters):
            result = self.result()
            values = {"X":[100,300,0], "Y":[300,100,0], "Z":[100,300,0]}[filters["brand"][0]]
            result["rows"] = [{"label":name,"years":{"2026":{"val":value},"2025":{"lfytd_val":previous}}}
                              for name,value,previous in zip(["A","B","C"], values, [50,100,0])]
            result["totals"] = {"2026":{"val":sum(values)},"2025":{"lfytd_val":150}}
            return result
        report.side_effect = brand_result
        result = summary.store_brand_rank({})
        self.assertEqual([r["label"] for r in result["rows"]], ["B","A","C"])
        b, a, c = result["rows"]
        self.assertEqual([a["cells"][k]["rank"] for k in ["X","Y","Z"]], [2,1,2])
        self.assertEqual([b["cells"][k]["rank"] for k in ["X","Y","Z"]], [1,3,1])
        self.assertEqual(a["totals"]["current"], 500)
        self.assertEqual(a["cells"]["Y"]["current_cont"], 60)
        self.assertAlmostEqual(a["cells"]["X"]["previous_cont"], 100/3)
        self.assertAlmostEqual(b["contribution"], 700/1200*100)
        self.assertAlmostEqual(sum(r["contribution"] for r in result["rows"]),100)
        self.assertIsNone(c["cells"]["X"]["current_cont"])
