import unittest
from unittest.mock import patch

import pandas as pd

from app.services import tertiary_kpi_tracking as tracking
from app.services.analysis import FactSpec


class TertiaryKpiTrackingTests(unittest.TestCase):
    def test_quantity_bucket_edges(self):
        self.assertEqual(tracking.quantity_bucket(1), tracking.QTY_BUCKETS[0])
        self.assertEqual(tracking.quantity_bucket(2), tracking.QTY_BUCKETS[1])
        self.assertEqual(tracking.quantity_bucket(3), tracking.QTY_BUCKETS[2])
        self.assertEqual(tracking.quantity_bucket(4), tracking.QTY_BUCKETS[3])
        self.assertEqual(tracking.quantity_bucket(5), tracking.QTY_BUCKETS[4])

    def test_revenue_bucket_edges(self):
        self.assertEqual(tracking.revenue_bucket(2000), tracking.REVENUE_BUCKETS[0])
        self.assertEqual(tracking.revenue_bucket(2000.01), tracking.REVENUE_BUCKETS[1])
        self.assertEqual(tracking.revenue_bucket(5000), tracking.REVENUE_BUCKETS[1])
        self.assertEqual(tracking.revenue_bucket(5000.01), tracking.REVENUE_BUCKETS[2])
        self.assertEqual(tracking.revenue_bucket(8000), tracking.REVENUE_BUCKETS[2])
        self.assertEqual(tracking.revenue_bucket(8000.01), tracking.REVENUE_BUCKETS[3])
        self.assertEqual(tracking.revenue_bucket(11000), tracking.REVENUE_BUCKETS[3])
        self.assertEqual(tracking.revenue_bucket(11000.01), tracking.REVENUE_BUCKETS[4])

    def setUp(self):
        self.bills = pd.DataFrame({
            "bill_date": pd.to_datetime([
                "2024-04-01", "2024-09-30", "2025-03-31",
                "2025-04-01", "2025-09-30", "2026-03-31",
                "2026-04-01", "2026-09-30",
            ]),
            "month_num": [4, 9, 3, 4, 9, 3, 4, 9],
            "store": ["A"] * 8,
            "qty": [1] * 8,
            "bill_val": [1000] * 8,
        })

    def test_default_periods_include_prior_full_year_and_matching_ytd(self):
        full, matching, current, labels = tracking._period_frames(self.bills, {})
        self.assertEqual(len(full), 3)
        self.assertEqual(len(matching), 2)
        self.assertEqual(len(current), 2)
        self.assertEqual(labels["anchor"], 2026)
        self.assertEqual(labels["matching"], "FY2025-26 LFYTD")
        self.assertEqual(labels["current"], "FY2026-27")

    def test_month_filter_keeps_prior_full_year_and_compares_same_months(self):
        full, matching, current, labels = tracking._period_frames(self.bills, {"month": ["9"]})
        self.assertEqual(len(full), 3)
        self.assertEqual(len(matching), 1)
        self.assertEqual(len(current), 1)
        self.assertEqual(labels["matching"], "FY2025-26 SELECTED MONTHS")

    def test_fy_filter_reanchors_periods(self):
        full, matching, current, labels = tracking._period_frames(self.bills, {"fy": ["2025"]})
        self.assertEqual(labels["anchor"], 2025)
        self.assertEqual(len(full), 3)
        self.assertEqual(len(current), 3)
        self.assertEqual(len(matching), 3)

    def test_grand_total_share_and_growth(self):
        full = pd.DataFrame({"store": ["A", "A"], "_bucket": ["small", "large"]})
        matching = pd.DataFrame({"store": ["A", "A"], "_bucket": ["small", "small"]})
        current = pd.DataFrame({"store": ["A", "A", "A"], "_bucket": ["small", "large", "large"]})
        rows = tracking._rows(full, matching, current, "store", "_bucket", ["small", "large"])
        total = rows[-1]
        self.assertEqual(total["periods"]["prior_full"]["small"]["share_pct"], 50)
        self.assertEqual(total["periods"]["matching"]["small"]["share_pct"], 100)
        self.assertAlmostEqual(total["periods"]["current"]["large"]["share_pct"], 2 / 3 * 100)
        self.assertEqual(total["periods"]["growth"]["small"]["count_growth_pct"], -50)
        self.assertAlmostEqual(total["periods"]["growth"]["small"]["share_pp"], -200 / 3)

    def test_dimension_filter_is_applied_to_bucket_reports(self):
        bills = pd.DataFrame({
            "bill_date": pd.to_datetime([
                "2024-04-01", "2024-09-30", "2025-03-31",
                "2025-04-01", "2025-09-30", "2026-03-31",
                "2026-04-01", "2026-09-30",
            ]),
            "month_num": [4, 9, 3, 4, 9, 3, 4, 9],
            "store": ["A", "A", "B", "A", "B", "B", "A", "B"],
            "brand": ["X", "X", "X", "X", "Y", "Y", "Y", "Y"],
            "qty": [1] * 8,
            "bill_val": [1000] * 8,
        })
        fact = FactSpec(schema="tertiary_data", table="data", date_column="date", qty_expr="qty", val_expr="bill_val")
        with patch.object(tracking._ba, "_load_bill_dataset", return_value=bills), \
             patch.object(tracking.tertiary_summary, "_fields", return_value={"store": "store", "brand": "brand"}), \
             patch.object(tracking, "cache_token", return_value=("unit-test",)):
            result = tracking.run_kpi_tracking(fact, {"brand": ["Y"]}, "store")

        self.assertEqual(result["meta"]["bill_count"], 2)
        total = result["quantity_rows"][-1]
        current_count = sum(cell["count"] for cell in total["periods"]["current"].values())
        self.assertEqual(current_count, 2)
        self.assertEqual({row["label"] for row in result["quantity_rows"][:-1]}, {"A", "B"})


if __name__ == "__main__":
    unittest.main()
