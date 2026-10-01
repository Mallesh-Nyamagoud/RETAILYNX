"""
Financial Year (April -> March) calculation helpers.

Every "LFY / CFY / APM / TRENDING" formula in the requirements doc hinges on
a handful of boundary dates that are all derived from a single MAX(date)
per dataset. Centralising the math here means the same, tested logic is
reused by Secondary Sales Analysis, Tertiary Sales Analysis and the
Store-Master status enrichment.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

from app.core.config import FY_START_MONTH


def _same_date_prior_year(d: date) -> date:
    """'Same calendar date, one year earlier' - clamps Feb-29 to Feb-28."""
    try:
        return d.replace(year=d.year - 1)
    except ValueError:
        return d.replace(year=d.year - 1, day=28)


@dataclass(frozen=True)
class FYContext:
    max_date: date
    current_fy_start: date
    current_fy_end: date
    last_fy_start: date
    last_fy_end: date
    lfy_ytd_end: date  # "same date" as max_date, one FY earlier
    days_elapsed_current_fy: int
    total_days_current_fy: int

    @property
    def current_fy_label(self) -> str:
        return f"FY{self.current_fy_start.year}-{str(self.current_fy_end.year)[-2:]}"

    @property
    def last_fy_label(self) -> str:
        return f"FY{self.last_fy_start.year}-{str(self.last_fy_end.year)[-2:]}"

    def to_dict(self) -> dict:
        return {
            "max_date": self.max_date.isoformat(),
            "current_fy_start": self.current_fy_start.isoformat(),
            "current_fy_end": self.current_fy_end.isoformat(),
            "last_fy_start": self.last_fy_start.isoformat(),
            "last_fy_end": self.last_fy_end.isoformat(),
            "lfy_ytd_end": self.lfy_ytd_end.isoformat(),
            "days_elapsed_current_fy": self.days_elapsed_current_fy,
            "total_days_current_fy": self.total_days_current_fy,
            "current_fy_label": self.current_fy_label,
            "last_fy_label": self.last_fy_label,
        }


def build_fy_context(max_date: date) -> FYContext:
    if max_date.month >= FY_START_MONTH:
        current_fy_start = date(max_date.year, FY_START_MONTH, 1)
    else:
        current_fy_start = date(max_date.year - 1, FY_START_MONTH, 1)

    next_fy_start = date(current_fy_start.year + 1, FY_START_MONTH, 1)
    current_fy_end = date.fromordinal(next_fy_start.toordinal() - 1)
    last_fy_start = date(current_fy_start.year - 1, FY_START_MONTH, 1)
    last_fy_end = date.fromordinal(current_fy_start.toordinal() - 1)
    lfy_ytd_end = _same_date_prior_year(max_date)

    days_elapsed = (max_date - current_fy_start).days + 1
    total_days = (current_fy_end - current_fy_start).days + 1

    return FYContext(
        max_date=max_date,
        current_fy_start=current_fy_start,
        current_fy_end=current_fy_end,
        last_fy_start=last_fy_start,
        last_fy_end=last_fy_end,
        lfy_ytd_end=lfy_ytd_end,
        days_elapsed_current_fy=days_elapsed,
        total_days_current_fy=total_days,
    )


def fy_month_order(month: int) -> int:
    """April=1 ... March=12, used to sort the Monthwise Sales table in
    fiscal-year order rather than calendar order."""
    return month - FY_START_MONTH + 1 if month >= FY_START_MONTH else month + (12 - FY_START_MONTH) + 1


def month_label(month: int) -> str:
    return calendar.month_abbr[month]


def safe_pct(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return 0.0
    try:
        return (numerator / abs(denominator)) * 100.0
    except ZeroDivisionError:
        return 0.0


# A prior-period base smaller than this is floating-point residue, not a real
# base: money and qty are aggregated as floats, so a row that nets to zero can
# still land on +-1e-12. Without this guard such a row produced absurd
# percentages (e.g. -600479950316066304.0%). Half a paisa / half a unit.
GROWTH_BASE_EPSILON = 0.005


def safe_growth(current: float | None, base: float | None) -> float | None:
    """Sign-correct growth %: ``(current - base) / |base| * 100``.

    Dividing by the ABSOLUTE value of the base is what makes the percentage
    carry the DIRECTION of the change even when the base is negative. A row
    whose LFY was -1,93,047 and is +6,48,187 this year gained 8,41,234, so it
    must read +435.8%; dividing by the signed base would return -435.8% and
    report a massive improvement as a collapse.

    A zero (or floating-point-residue) base means no percentage base exists ->
    0.0, never NaN/Infinity. Use this for every GROWTH figure; keep `safe_pct`
    for ratios (contribution %, discount %, ASP/MRP ratios) where the
    denominator's own sign is part of the meaning.
    """
    if current is None or base is None:
        return 0.0
    try:
        if abs(base) < GROWTH_BASE_EPSILON:
            return 0.0
        return ((current - base) / abs(base)) * 100.0
    except (ZeroDivisionError, TypeError):
        return 0.0


def safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return 0.0
    try:
        return numerator / denominator
    except ZeroDivisionError:
        return 0.0
