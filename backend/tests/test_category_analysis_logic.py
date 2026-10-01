"""Unit tests for the Category Performance (Tertiary Sales) formula logic.

These tests are INDEPENDENT of the UI and of the database: they exercise the
pure helpers in app/services/category_analysis.py

    - _norm / _key         NaN-safe dimension keying
    - _sum_index           one vectorised groupby -> {(keys...): (qty, val, mrp)}
    - _rollup              summing measure tuples across key positions
    - _cell                ASP / AVG.MRP / growth / row-relative CONT.%
    - _union_values        CFY-volume order + LFY-only values appended
    - _level1_data         Contribution % against the ROW's own category total
    - _level2_data         Contribution % against the PARENT category total
    - _apply_filters       global slicers as one boolean mask
    - _resolve_row_dims    Row Hierarchy level 1 / level 2 resolution
    - _filter_and_order_categories   PROMO exclusion + fixed display order

Run from C:\\webapp\\backend:
    python -m unittest tests.test_category_analysis_logic -v
"""
import unittest
from unittest.mock import patch

import pandas as pd

from app.services import category_analysis as ca


def _fact(rows):
    """Tiny fact table shaped like `_load_facts()` output."""
    df = pd.DataFrame(rows)
    if "tx_date" in df.columns:
        df["tx_date"] = pd.to_datetime(df["tx_date"])
    for col in ("qty_val", "val_val", "mrp_val"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return df


class KeyingTests(unittest.TestCase):
    def test_nan_and_none_normalise_to_none(self):
        self.assertIsNone(ca._norm(float("nan")))
        self.assertIsNone(ca._norm(None))

    def test_real_values_pass_through(self):
        self.assertEqual(ca._norm("DENIM"), "DENIM")
        self.assertEqual(ca._norm(0), 0)

    def test_key_wraps_scalars_and_tuple_keys_alike(self):
        self.assertEqual(ca._key("BRAND A"), ("BRAND A",))
        self.assertEqual(ca._key(("BRAND A", "SHIRTS")), ("BRAND A", "SHIRTS"))
        self.assertEqual(ca._key((float("nan"), "SHIRTS")), (None, "SHIRTS"))


class SumIndexTests(unittest.TestCase):
    def _df(self):
        return _fact([
            {"brand": "B1", "category": "SHIRTS", "sub_category": "S1", "qty_val": 2, "val_val": 200.0, "mrp_val": 400.0},
            {"brand": "B1", "category": "SHIRTS", "sub_category": "S1", "qty_val": 3, "val_val": 300.0, "mrp_val": 600.0},
            {"brand": "B1", "category": "DENIM", "sub_category": None, "qty_val": 5, "val_val": 500.0, "mrp_val": 1000.0},
        ])

    def test_sums_every_measure_per_key(self):
        idx = ca._sum_index(self._df(), ["brand", "category"])
        self.assertEqual(idx[("B1", "SHIRTS")], (5.0, 500.0, 1000.0))
        self.assertEqual(idx[("B1", "DENIM")], (5.0, 500.0, 1000.0))

    def test_missing_dimension_is_keyed_as_none_not_nan(self):
        idx = ca._sum_index(self._df(), ["brand", "category", "sub_category"])
        self.assertEqual(idx[("B1", "DENIM", None)], (5.0, 500.0, 1000.0))

    def test_empty_frame_returns_empty_map(self):
        empty = pd.DataFrame(columns=["brand", "qty_val", "val_val", "mrp_val"])
        self.assertEqual(ca._sum_index(empty, ["brand"]), {})

    def test_single_key_groupby_produces_one_element_keys(self):
        idx = ca._sum_index(self._df(), ["brand"])
        self.assertEqual(idx[("B1",)], (10.0, 1000.0, 2000.0))


class RollupTests(unittest.TestCase):
    def test_sums_across_the_selected_key_positions(self):
        src = {
            ("B1", "SHIRTS"): (5.0, 500.0, 1000.0),
            ("B1", "DENIM"): (5.0, 500.0, 1000.0),
            ("B2", "SHIRTS"): (1.0, 100.0, 200.0),
        }
        by_cat = ca._rollup(src, (1,))
        by_dim = ca._rollup(src, (0,))
        self.assertEqual(by_cat[("SHIRTS",)], (6.0, 600.0, 1200.0))
        self.assertEqual(by_dim[("B1",)], (10.0, 1000.0, 2000.0))
        self.assertEqual(by_dim[("B2",)], (1.0, 100.0, 200.0))

    def test_empty_source_returns_empty_map(self):
        self.assertEqual(ca._rollup({}, (0,)), {})


class CellTests(unittest.TestCase):
    def test_asp_avg_mrp_and_growth(self):
        cell = ca._cell((10.0, 1000.0, 2000.0), (8.0, 400.0, 800.0), (0.0, 0.0, 0.0), 100.0, 80.0, 0.0)
        self.assertAlmostEqual(cell["asp_cfy"], 100.0)
        self.assertAlmostEqual(cell["asp_lfy"], 50.0)
        self.assertAlmostEqual(cell["asp_growth_pct"], 100.0)
        # AVG.MRP CFY = 2000 / 10 = 200, LFY = 800 / 8 = 100 -> +100%
        self.assertAlmostEqual(cell["avg_mrp_cfy"], 200.0)
        self.assertAlmostEqual(cell["avg_mrp_lfy"], 100.0)
        self.assertAlmostEqual(cell["avg_mrp_growth_pct"], 100.0)

    def test_cont_pct_is_relative_to_the_passed_row_total(self):
        cell = ca._cell((10.0, 0.0, 0.0), (5.0, 0.0, 0.0), (2.5, 0.0, 0.0), 40.0, 20.0, 10.0)
        self.assertAlmostEqual(cell["cont_pct_cfy"], 25.0)
        self.assertAlmostEqual(cell["cont_pct_lfy"], 25.0)
        self.assertAlmostEqual(cell["cont_pct_lfytd"], 25.0)
        self.assertAlmostEqual(cell["change_in_cont"], 0.0)

    def test_change_in_cont_is_cfy_minus_lfy_share(self):
        cell = ca._cell((30.0, 0.0, 0.0), (0.0, 0.0, 0.0), (10.0, 0.0, 0.0), 100.0, 0.0, 100.0)
        self.assertAlmostEqual(cell["change_in_cont"], 20.0)

    def test_change_in_cont_compares_cfytd_with_lfytd_not_full_lfy(self):
        # CFYTD share 30% vs LFYTD share 10% -> +20 pp.  The full LFY share (50%)
        # must NOT be the baseline (that would produce -20 pp) - the delta is a
        # like-for-like year-to-date comparison.
        cell = ca._cell((30.0, 0.0, 0.0), (50.0, 0.0, 0.0), (10.0, 0.0, 0.0), 100.0, 100.0, 100.0)
        self.assertAlmostEqual(cell["change_in_cont"], 20.0)

    def test_lfytd_twins_for_qty_asp_and_avg_mrp(self):
        # CFYTD 12 @ Rs.120 = Rs.1440, LFYTD 8 @ Rs.80 = Rs.640, full LFY 40 @ Rs.60.
        cell = ca._cell(
            (12.0, 1440.0, 2400.0), (40.0, 2400.0, 8000.0), (8.0, 640.0, 1600.0), 12.0, 40.0, 8.0
        )
        self.assertAlmostEqual(cell["asp_lfytd"], 80.0)
        self.assertAlmostEqual(cell["avg_mrp_lfytd"], 200.0)
        self.assertAlmostEqual(cell["qty_growth_lfytd_pct"], 50.0)
        self.assertAlmostEqual(cell["asp_growth_lfytd_pct"], 50.0)
        # AVG.MRP is flat (200 -> 200) even though LFY-to-CFY "growth" is not.
        self.assertAlmostEqual(cell["avg_mrp_growth_lfytd_pct"], 0.0)
        self.assertAlmostEqual(cell["asp_growth_pct"], 100.0)

    def test_lfytd_growth_fields_guard_zero_division(self):
        cell = ca._cell((10.0, 100.0, 200.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 10.0, 0.0, 0.0)
        self.assertEqual(cell["asp_lfytd"], 0.0)
        self.assertEqual(cell["avg_mrp_lfytd"], 0.0)
        self.assertEqual(cell["qty_growth_lfytd_pct"], 0.0)
        self.assertEqual(cell["asp_growth_lfytd_pct"], 0.0)
        self.assertEqual(cell["avg_mrp_growth_lfytd_pct"], 0.0)

    def test_zero_row_total_never_divides_by_zero(self):
        cell = ca._cell((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 0.0, 0.0, 0.0)
        self.assertEqual(cell["cont_pct_cfy"], 0.0)
        self.assertEqual(cell["cont_pct_lfy"], 0.0)
        self.assertEqual(cell["cont_pct_lfytd"], 0.0)
        self.assertEqual(cell["change_in_cont"], 0.0)
        self.assertEqual(cell["asp_growth_pct"], 0.0)
        self.assertEqual(cell["avg_mrp_growth_pct"], 0.0)

    def test_sale_measures_are_the_qty_measures(self):
        cell = ca._cell((7.0, 70.0, 7.0), (3.0, 30.0, 3.0), (3.0, 30.0, 3.0), 7.0, 3.0, 3.0)
        self.assertEqual(cell["sale_cfy"], cell["qty_cfy"])
        self.assertEqual(cell["sale_lfy"], cell["qty_lfy"])
        self.assertEqual(cell["sale_lfytd"], cell["qty_lfytd"])


class UnionValuesTests(unittest.TestCase):
    def test_cfy_volume_order_first_then_lfy_only_values(self):
        cfy = {("B2",): (5.0, 0.0, 0.0), ("B1",): (10.0, 0.0, 0.0)}
        lfy = {("B1",): (1.0, 0.0, 0.0), ("B3",): (9.0, 0.0, 0.0)}
        self.assertEqual(ca._union_values(cfy, lfy), ["B1", "B2", "B3"])

    def test_lfy_only_values_are_ordered_by_lfy_volume(self):
        cfy = {("B1",): (1.0, 0.0, 0.0)}
        lfy = {("B4",): (2.0, 0.0, 0.0), ("B3",): (9.0, 0.0, 0.0)}
        self.assertEqual(ca._union_values(cfy, lfy), ["B1", "B3", "B4"])

    def test_empty_maps_return_no_values(self):
        self.assertEqual(ca._union_values({}, {}), [])

    def test_blank_dimension_value_is_kept_as_a_row(self):
        self.assertEqual(ca._fmt_dim(None), "(blank)")
        self.assertEqual(ca._union_values({(None,): (3.0, 0.0, 0.0)}, {}), [None])


class Level1DataTests(unittest.TestCase):
    """Level 1 = one row (any row-hierarchy value) x Category."""

    def _maps(self):
        cfy = {
            ("B1", "SHIRTS"): (10.0, 1000.0, 2000.0),
            ("B1", "DENIM"): (30.0, 3000.0, 6000.0),
            ("B2", "SHIRTS"): (5.0, 500.0, 1000.0),
        }
        lfy = {
            ("B1", "SHIRTS"): (8.0, 800.0, 1600.0),
            ("B1", "DENIM"): (12.0, 1200.0, 2400.0),
        }
        return cfy, lfy

    def test_contribution_is_relative_to_the_rows_own_category_total(self):
        cfy, lfy = self._maps()
        data = ca._level1_data(("B1",), cfy, lfy, lfy, ["SHIRTS", "DENIM"])
        # B1 CFY total = 10 + 30 = 40 -> SHIRTS = 25%, DENIM = 75%
        self.assertAlmostEqual(data["SHIRTS"]["cont_pct_cfy"], 25.0)
        self.assertAlmostEqual(data["DENIM"]["cont_pct_cfy"], 75.0)
        # B1 LFY total = 8 + 12 = 20 -> 40% / 60%
        self.assertAlmostEqual(data["SHIRTS"]["cont_pct_lfy"], 40.0)
        self.assertAlmostEqual(data["DENIM"]["cont_pct_lfy"], 60.0)

    def test_grand_total_uses_the_whole_filtered_context(self):
        # The grand-total row has no row-hierarchy prefix, so its index is keyed
        # by CATEGORY only (that is what `_sum_index` produces for dims = []).
        cfy = {("SHIRTS",): (15.0, 1500.0, 0.0), ("DENIM",): (30.0, 3000.0, 0.0)}
        lfy = {("SHIRTS",): (9.0, 900.0, 0.0), ("DENIM",): (6.0, 600.0, 0.0)}
        data = ca._level1_data((), cfy, lfy, lfy, ["SHIRTS", "DENIM"])
        # CFY total = 15 + 30 = 45 -> SHIRTS = 15/45
        self.assertAlmostEqual(data["SHIRTS"]["cont_pct_cfy"], 100.0 * 15 / 45)
        self.assertAlmostEqual(data["DENIM"]["cont_pct_cfy"], 100.0 * 30 / 45)

    def test_missing_category_cell_is_all_zeros(self):
        cfy, lfy = self._maps()
        data = ca._level1_data(("B2",), cfy, lfy, lfy, ["SHIRTS", "DENIM"])
        self.assertEqual(data["DENIM"]["sale_cfy"], 0.0)
        self.assertEqual(data["DENIM"]["cont_pct_cfy"], 0.0)

    def test_every_category_key_is_present(self):
        cfy, lfy = self._maps()
        data = ca._level1_data(("B1",), cfy, lfy, lfy, ["SHIRTS", "DENIM", "TROUSERS"])
        self.assertEqual(set(data), {"SHIRTS", "DENIM", "TROUSERS"})


class Level2DataTests(unittest.TestCase):
    """Level 2 = one row x Category x Sub-Category, contribution vs the PARENT
    category total (never against the whole row)."""

    def _maps(self):
        cfy = {
            ("B1", "SHIRTS", "S1"): (6.0, 600.0, 1200.0),
            ("B1", "SHIRTS", "S2"): (4.0, 400.0, 800.0),
            ("B1", "DENIM", "D1"): (90.0, 900.0, 1800.0),
        }
        lfy = {
            ("B1", "SHIRTS", "S1"): (3.0, 300.0, 600.0),
            ("B1", "SHIRTS", "S2"): (1.0, 100.0, 200.0),
        }
        return cfy, lfy

    def test_sub_contribution_is_relative_to_its_parent_category(self):
        cfy, lfy = self._maps()
        subs = {"SHIRTS": ["S1", "S2"], "DENIM": ["D1"]}
        data = ca._level2_data(("B1",), cfy, lfy, lfy, ["SHIRTS", "DENIM"], subs)
        # SHIRTS CFY total = 10 -> S1 = 60%, S2 = 40% (NOT 6/100)
        self.assertAlmostEqual(data["SHIRTS"]["S1"]["cont_pct_cfy"], 60.0)
        self.assertAlmostEqual(data["SHIRTS"]["S2"]["cont_pct_cfy"], 40.0)
        # DENIM is its own parent -> 100%
        self.assertAlmostEqual(data["DENIM"]["D1"]["cont_pct_cfy"], 100.0)

    def test_category_without_sub_categories_is_an_empty_map(self):
        cfy, lfy = self._maps()
        data = ca._level2_data(("B1",), cfy, lfy, lfy, ["SHIRTS", "TROUSERS"], {"SHIRTS": ["S1"]})
        self.assertEqual(data["TROUSERS"], {})

    def test_missing_sub_category_cell_is_all_zeros(self):
        cfy, lfy = self._maps()
        data = ca._level2_data(("B1",), cfy, lfy, lfy, ["SHIRTS"], {"SHIRTS": ["S1", "S9"]})
        self.assertEqual(data["SHIRTS"]["S9"]["sale_cfy"], 0.0)


class ApplyFiltersTests(unittest.TestCase):
    def _df(self):
        return _fact([
            {"brand": "B1", "state": "KA", "category": "SHIRTS", "qty_val": 1, "val_val": 1.0, "mrp_val": 1.0},
            {"brand": "B1", "state": "TN", "category": "SHIRTS", "qty_val": 2, "val_val": 2.0, "mrp_val": 2.0},
            {"brand": "B2", "state": "KA", "category": "SHIRTS", "qty_val": 3, "val_val": 3.0, "mrp_val": 3.0},
        ])

    def test_no_filters_returns_every_row(self):
        self.assertEqual(len(ca._apply_filters(self._df(), {})), 3)

    def test_single_slicer(self):
        out = ca._apply_filters(self._df(), {"state": ["KA"]})
        self.assertEqual(sorted(out["qty_val"].tolist()), [1, 3])

    def test_multiple_slicers_are_ANDed(self):
        out = ca._apply_filters(self._df(), {"state": ["KA"], "brand": ["B2"]})
        self.assertEqual(out["qty_val"].tolist(), [3])

    def test_empty_value_list_is_ignored(self):
        self.assertEqual(len(ca._apply_filters(self._df(), {"state": []})), 3)

    def test_unknown_column_is_ignored_not_fatal(self):
        out = ca._apply_filters(self._df(), {"nonexistent_col": ["X"], "state": ["KA"]})
        self.assertEqual(sorted(out["qty_val"].tolist()), [1, 3])


class RowDimResolutionTests(unittest.TestCase):
    AVAILABLE = frozenset({"brand", "retailer_name", "state", "department", "store_type"})

    def _resolve(self, hierarchy):
        with patch.object(ca, "_available_dim_columns", lambda: self.AVAILABLE):
            return ca._resolve_row_dims(hierarchy)

    def test_explicit_hierarchy_level1_and_level2_are_kept_in_order(self):
        self.assertEqual(self._resolve(["department", "brand"]), ("department", "brand"))

    def test_single_level_is_supported(self):
        self.assertEqual(self._resolve(["state"]), ("state",))

    def test_capped_at_two_levels(self):
        self.assertEqual(self._resolve(["state", "department", "brand"]), ("state", "department"))

    def test_unknown_columns_are_dropped(self):
        self.assertEqual(self._resolve(["not_a_dim", "state"]), ("state",))

    def test_empty_hierarchy_falls_back_to_brand(self):
        self.assertEqual(self._resolve([]), ("brand",))
        self.assertEqual(self._resolve(None), ("brand",))

    def test_empty_hierarchy_without_brand_falls_back_to_grand_total_only(self):
        with patch.object(ca, "_available_dim_columns", lambda: frozenset({"state"})):
            self.assertEqual(ca._resolve_row_dims([]), ())


class CategoryOrderingTests(unittest.TestCase):
    def test_promo_categories_are_excluded(self):
        out = ca._filter_and_order_categories(["SHIRTS", "PROMO SHIRTS", "DENIM"])
        self.assertEqual(out, ["SHIRTS", "DENIM"])

    def test_fixed_display_order_then_alphabetical_rest(self):
        out = ca._filter_and_order_categories(["ZZZ", "DENIM", "SHIRTS", "AAA"])
        self.assertEqual(out, ["SHIRTS", "DENIM", "AAA", "ZZZ"])

    def test_lowercase_values_still_honour_the_fixed_order(self):
        out = ca._filter_and_order_categories(["denim", "shirts"])
        self.assertEqual(out, ["shirts", "denim"])


if __name__ == "__main__":
    unittest.main()
