import unittest

from app.services import store_master


class StoreMasterStatusTests(unittest.TestCase):
    def test_status_classification_uses_opening_month_and_brand_close_rule(self):
        fy_start = "2025-04-01"
        last_fy_start = "2024-04-01"
        brand_max_date = "2025-12-15"

        self.assertEqual(
            store_master.determine_store_status("2024-04-01", "2025-12-15", brand_max_date, fy_start, last_fy_start),
            "L2L",
        )
        self.assertEqual(
            store_master.determine_store_status("2024-08-12", "2025-12-15", brand_max_date, fy_start, last_fy_start),
            "Annualized",
        )
        self.assertEqual(
            store_master.determine_store_status("2025-06-10", "2025-12-15", brand_max_date, fy_start, last_fy_start),
            "New",
        )
        self.assertEqual(
            store_master.determine_store_status("2024-05-01", "2025-08-30", brand_max_date, fy_start, last_fy_start),
            "Closed",
        )

    def test_no_tertiary_data_is_na(self):
        # NON-SIS: no tertiary data at all -> 'NA' (not 'Unknown').
        self.assertEqual(store_master.determine_store_status(None, None, "2025-12-15", "2025-04-01", "2024-04-01"), "NA")

    def test_unique_adonis_door_counts_are_used_for_kpis(self):
        rows = [
            {"adonis_store_code": "A1", "brand_code": "B1", "store_type": "SIS", "store_status": "L2L"},
            {"adonis_store_code": "A1", "brand_code": "B2", "store_type": "SIS", "store_status": "New"},
            {"adonis_store_code": "A2", "brand_code": "B1", "store_type": "SIS", "store_status": "L2L"},
            {"adonis_store_code": "A3", "brand_code": "B1", "store_type": "SIS", "store_status": "Closed"},
        ]
        counts = store_master._counts_by_status(rows)
        self.assertEqual(counts["L2L"], 2)
        self.assertEqual(counts["New"], 1)
        self.assertEqual(counts["Closed"], 1)
        self.assertEqual(counts["total_active_doors"], 2)
        self.assertEqual(counts["sis_doors"], 2)
        self.assertEqual(counts["non_sis_doors"], 0)


class ActiveDoorsTests(unittest.TestCase):
    """TOTAL ACTIVE DOORS: counted on ADONIS STORE CODE - a store with
    MULTIPLE brands counts as ONE active door if ANY ONE brand is L2L /
    Annualized / New, irrespective of how many brands exist."""

    def _rows(self):
        return [
            # A1: one active brand + one Closed brand -> still ONE active door.
            {"adonis_store_code": "A1", "brand": "Levis Mens", "store_type": "SIS", "store_status": "L2L"},
            {"adonis_store_code": "A1", "brand": "Killer", "store_type": "SIS", "store_status": "Closed"},
            # A2: every brand Closed -> NOT active.
            {"adonis_store_code": "A2", "brand": "Levis Mens", "store_type": "SIS", "store_status": "Closed"},
            {"adonis_store_code": "A2", "brand": "Killer", "store_type": "SIS", "store_status": "Closed"},
            # A3: non-SIS -> NOT active.
            {"adonis_store_code": "A3", "brand": "Killer", "store_type": "NON - SIS", "store_status": "NA"},
            # A4: active via New.
            {"adonis_store_code": "A4", "brand": "Levis Womens", "store_type": "SIS", "store_status": "New"},
            # A5: active status but classified Non-SIS by store_type.
            {"adonis_store_code": "A5", "brand": "Other", "store_type": "NON - SIS", "store_status": "Annualized"},
        ]

    def test_active_doors_counted_once_per_store_code(self):
        self.assertEqual(store_master._active_door_count(self._rows()), 3)

    def test_active_door_counts_use_store_type_and_exclude_closed_only_doors(self):
        sis, non_sis = store_master._active_doors_by_store_type(self._rows())
        self.assertEqual((sis, non_sis), (2, 1))
        self.assertEqual(sis + non_sis, store_master._active_door_count(self._rows()))

    def test_brand_summary_groups_by_brand_name_not_code(self):
        summary = store_master._brand_summary_rows(self._rows())
        by_brand = {r["brand"]: r for r in summary}
        self.assertEqual(set(by_brand), {"Levis Mens", "Killer", "Levis Womens", "Other"})
        # Levis Mens: A1 active (L2L); A2 Closed -> not active.
        self.assertEqual(by_brand["Levis Mens"]["total_active_doors"], 1)
        self.assertEqual(by_brand["Levis Mens"]["l2l"], 1)
        self.assertEqual(by_brand["Levis Mens"]["non_sis"], 0)
        # Killer: A1 Closed, A2 Closed, A3 NA -> 0 active, 1 non-SIS door.
        self.assertEqual(by_brand["Killer"]["total_active_doors"], 0)
        self.assertEqual(by_brand["Killer"]["non_sis"], 1)
        # Levis Womens: A4 New.
        self.assertEqual(by_brand["Levis Womens"]["new"], 1)
        self.assertEqual(by_brand["Levis Womens"]["total_active_doors"], 1)
        # Sorted by active doors desc.
        self.assertEqual(summary[0]["brand"], "Levis Mens")


if __name__ == "__main__":
    unittest.main()
