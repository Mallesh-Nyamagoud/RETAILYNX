"""Unit tests for the shared GROWTH % formula logic.

These tests are INDEPENDENT of the UI and of the database: they exercise the
pure growth helpers reused by every analysis module.

The rule under test (docs section 5): growth divides by the ABSOLUTE value of
the base -

    growth % = (current - base) / |base| * 100

- so the sign of the result always means "better / worse".  A signed
denominator flips the sign whenever the prior period is negative, which used to
report a big recovery (LFY -1,93,047 -> CFY +6,48,187) as -435.8% instead of
+435.8%.

Run from C:\\webapp\\backend:
    python -m unittest tests.test_growth_logic -v
"""
import math
import unittest

from app.services import bill_analysis as ba
from app.services import bill_kpi as bk
from app.services.fy import safe_growth, safe_pct


class SafeGrowthTests(unittest.TestCase):
    """app.services.fy.safe_growth - the one growth helper every module uses."""

    def test_positive_base_growth_and_decline_are_unchanged(self):
        self.assertAlmostEqual(safe_growth(150, 100), 50.0)
        self.assertAlmostEqual(safe_growth(75, 100), -25.0)
        self.assertAlmostEqual(safe_growth(100, 100), 0.0)

    def test_negative_base_turning_positive_is_POSITIVE_growth(self):
        """The reported bug: LFY -1,93,047 -> CFY +6,48,187 must read +435.8%."""
        growth = safe_growth(648187, -193047)
        self.assertAlmostEqual(growth, (648187 + 193047) / 193047 * 100, places=6)
        self.assertGreater(growth, 0.0)
        # ...and the OLD signed-denominator form is exactly the sign-flipped bug.
        self.assertLess((648187 - (-193047)) / -193047 * 100, 0.0)

    def test_negative_base_improving_reads_positive(self):
        # A smaller loss than last year is an improvement.
        self.assertAlmostEqual(safe_growth(-50, -100), 50.0)

    def test_negative_base_worsening_reads_negative(self):
        # A bigger loss than last year is a decline.
        self.assertAlmostEqual(safe_growth(-200, -100), -100.0)

    def test_magnitude_is_identical_to_the_signed_form(self):
        for current, base in [(-200, -100), (-50, -100), (648187, -193047)]:
            self.assertAlmostEqual(
                abs(safe_growth(current, base)),
                abs((current - base) / base * 100.0),
                places=9,
            )

    def test_zero_or_missing_base_is_zero_never_nan(self):
        for args in [(50, 0), (50, 0.0), (None, 10), (10, None), (None, None)]:
            result = safe_growth(*args)
            self.assertEqual(result, 0.0)
            self.assertFalse(math.isnan(result) or math.isinf(result))

    def test_always_finite(self):
        for args in [(-5, -3), (3, 7), (-1e12, -1.0), (1e12, -1.0)]:
            self.assertTrue(math.isfinite(safe_growth(*args)))


class SafePctAbsoluteDenominatorTests(unittest.TestCase):
    """Contract (updated with the sign-bug fix): safe_pct divides by
    |denominator|, so a negative base period can never flip the sign - the
    numerator's sign carries the direction."""

    def test_denominator_magnitude_with_zero_guard(self):
        self.assertAlmostEqual(safe_pct(-50, 100), -50.0)   # numerator sign kept
        self.assertAlmostEqual(safe_pct(50, -100), 50.0)    # LFY=-100, CFY=-50 -> +50%
        self.assertEqual(safe_pct(50, 0), 0.0)              # zero base stays 0.0


class BillGrowthHelpersUseAbsoluteBaseTests(unittest.TestCase):
    """The Bill No. / Bill KPI modules own copies of the same formula."""

    def test_bill_analysis_growth_sign(self):
        self.assertAlmostEqual(ba._growth(150, 100), 50.0)
        self.assertAlmostEqual(ba._growth(75, 100), -25.0)
        self.assertAlmostEqual(ba._growth(648187, -193047), 435.7664, places=3)
        self.assertIsNone(ba._growth(50, 0))

    def test_bill_kpi_growth_sign(self):
        self.assertAlmostEqual(bk._growth(150, 100), 50.0)
        self.assertAlmostEqual(bk._growth(75, 100), -25.0)
        self.assertAlmostEqual(bk._growth(648187, -193047), 435.7664, places=3)
        self.assertIsNone(bk._growth(50, 0))


if __name__ == "__main__":
    unittest.main()
