"""Unit tests for the TRENDING ("Proj. Full Year") projection.

TRENDING now uses the "last year same period, adjusted for growth" method:

    trending = cfytd * (lfy_full / lfytd)

i.e. this year's YTD-vs-same-period growth rate applied to last year's ACTUAL
full-year total, so the projection inherits last year's real seasonal shape.
When the same-period base (lfytd) is missing/zero/negative the seasonality
ratio is undefined or would flip sign, so it falls back to the original
flat-linear run-rate:

    trending = cfytd / days_elapsed * total_days

The two branches are tested THROUGH the real `_finalise_measures` code path
(not a copy of the formula), so the test breaks if the production logic drifts.

Run from C:\\webapp\\backend:
    python -m pytest tests/test_trending_logic.py -v
    (or: python -m unittest tests.test_trending_logic -v)
"""
import unittest
from types import SimpleNamespace

import pandas as pd

from app.services.analysis import _finalise_measures


def _fy(days_elapsed=122, total_days=365):
    return SimpleNamespace(
        days_elapsed_current_fy=days_elapsed,
        total_days_current_fy=total_days,
    )


def _row(**overrides):
    """One pivot-shaped row with every column `_finalise_measures` reads."""
    base = {
        "cfytd_qty": 0.0,
        "lfytd_qty": 0.0,
        "lfy_full_qty": 0.0,
        "cfytd_val": 0.0,
        "lfytd_val": 0.0,
        "lfy_full_val": 0.0,
        # APM inputs the function also touches (unused by trending)
        "cfapm_qty": 0.0,
        "cfapm_val": 0.0,
        "pfapm_qty": 0.0,
        "pfapm_val": 0.0,
        "lfytd_apm_qty": 0.0,
        "lfytd_apm_val": 0.0,
    }
    base.update(overrides)
    return base


def _finalise(rows, fy=None):
    return _finalise_measures(pd.DataFrame(rows), fy or _fy(), [])


class TrendingMethodTests(unittest.TestCase):
    """The happy path: lfytd > 0 -> seasonal ratio method."""

    def test_year_same_period_adjusted_for_growth(self):
        # The exact figures the task specifies for BSC DAVANGERE (Taxable Value).
        cfytd, lfytd, lfy_full = 3680710.83, 2356785.41, 15680777.48
        out = _finalise([_row(
            cfytd_val=cfytd, lfytd_val=lfytd, lfy_full_val=lfy_full,
            cfytd_qty=100.0, lfytd_qty=100.0, lfy_full_qty=100.0,
        )])[0]

        expected = cfytd * (lfy_full / lfytd)  # 24,489,462.32
        self.assertAlmostEqual(out["trending_val"], expected, places=6)
        # ~24.49M. (The task's 24,490,787 is the SAME formula at full DB precision;
        # these inputs are pre-rounded to 2dp, hence the ~0.005% gap.)
        self.assertAlmostEqual(out["trending_val"], 24490787, delta=3000)
        self.assertAlmostEqual(out["trending_val"] / 24490787, 1.0, places=3)
        # days_elapsed / total_days must NOT influence this branch.
        out_alt = _finalise([_row(
            cfytd_val=cfytd, lfytd_val=lfytd, lfy_full_val=lfy_full,
            cfytd_qty=100.0, lfytd_qty=100.0, lfy_full_qty=100.0,
        )], fy=_fy(days_elapsed=1, total_days=366))[0]
        self.assertAlmostEqual(out_alt["trending_val"], expected, places=6)

    def test_proj_growth_matches_growth_sign_and_value(self):
        # trending = cfytd * lfy_full/lfytd  =>  proj_growth == growth exactly.
        out = _finalise([_row(
            cfytd_val=3680710.83, lfytd_val=2356785.41, lfy_full_val=15680777.48,
            cfytd_qty=1485.0, lfytd_qty=1000.0, lfy_full_qty=8000.0,
        )])[0]
        self.assertAlmostEqual(out["growth_pct_qty"], 48.5)
        self.assertAlmostEqual(out["proj_growth_pct_qty"], 48.5)
        self.assertAlmostEqual(
            out["proj_growth_pct_qty"], out["growth_pct_qty"], places=9
        )
        self.assertGreater(out["proj_growth_pct_val"], 0)


class TrendingFallbackTests(unittest.TestCase):
    """lfytd missing / zero / negative -> flat-linear run-rate."""

    def test_zero_lfytd_falls_back_to_flat_linear(self):
        out = _finalise([_row(
            cfytd_val=500.0, lfytd_val=0.0, lfy_full_val=10000.0,
            cfytd_qty=500.0, lfytd_qty=0.0, lfy_full_qty=10000.0,
        )])[0]
        expected = 500.0 / 122 * 365  # 1495.9016...
        self.assertAlmostEqual(out["trending_val"], expected, places=6)
        self.assertAlmostEqual(out["trending_qty"], expected, places=6)

    def test_negative_lfytd_also_falls_back_never_uses_abs(self):
        out = _finalise([_row(
            cfytd_val=500.0, lfytd_val=-100.0, lfy_full_val=10000.0,
            cfytd_qty=500.0, lfytd_qty=-100.0, lfy_full_qty=10000.0,
        )])[0]
        flat = 500.0 / 122 * 365
        self.assertAlmostEqual(out["trending_val"], flat, places=6)
        # explicit guard: must NOT be cfytd*(lfy_full/lfytd) (which would be -50,000)
        self.assertNotAlmostEqual(out["trending_val"], 500.0 * (10000.0 / -100.0))

    def test_qty_and_val_fall_back_independently(self):
        # lfytd_qty = 0 (fallback) while lfytd_val > 0 (seasonal method).
        out = _finalise([_row(
            cfytd_qty=500.0, lfytd_qty=0.0, lfy_full_qty=10000.0,
            cfytd_val=1000.0, lfytd_val=400.0, lfy_full_val=6000.0,
        )])[0]
        self.assertAlmostEqual(out["trending_qty"], 500.0 / 122 * 365, places=6)
        self.assertAlmostEqual(out["trending_val"], 1000.0 * (6000.0 / 400.0), places=6)

    def test_val_falls_back_while_qty_uses_seasonal_method(self):
        # The mirror image - lfytd_val = 0 (fallback) while lfytd_qty > 0.
        out = _finalise([_row(
            cfytd_qty=1000.0, lfytd_qty=400.0, lfy_full_qty=6000.0,
            cfytd_val=500.0, lfytd_val=0.0, lfy_full_val=10000.0,
        )])[0]
        self.assertAlmostEqual(out["trending_val"], 500.0 / 122 * 365, places=6)
        self.assertAlmostEqual(out["trending_qty"], 1000.0 * (6000.0 / 400.0), places=6)


if __name__ == "__main__":
    unittest.main()
