"""FY-wise bill-count distribution analysis for tertiary KPI tracking."""
from __future__ import annotations

from functools import lru_cache

import pandas as pd

from app.core.database import cache_token, filter_key
from app.services import bill_analysis as _ba, tertiary_summary
from app.services.analysis import FactSpec

QTY_BUCKETS = ["1 Qty Bill", "2 Qty Bills", "3 Qty Bills", "4 Qty Bills", ">4 Qty Bills"]
REVENUE_BUCKETS = ["≤ ₹2,000", "₹2,001–5,000", "₹5,001–8,000", "₹8,001–11,000", "> ₹11,000"]


def quantity_bucket(value) -> str:
    """Classify a bill's aggregated quantity using the existing bill analysis rule."""
    if value is None or pd.isna(value):
        return QTY_BUCKETS[-1]
    value = float(value)
    if value < 2:
        return QTY_BUCKETS[0]
    if value < 3:
        return QTY_BUCKETS[1]
    if value < 4:
        return QTY_BUCKETS[2]
    if value < 5:
        return QTY_BUCKETS[3]
    return QTY_BUCKETS[4]


def revenue_bucket(value) -> str:
    """Classify bill value using the screenshot's five inclusive upper bands."""
    if value is None or pd.isna(value):
        value = 0
    value = float(value)
    if value <= 2000:
        return REVENUE_BUCKETS[0]
    if value <= 5000:
        return REVENUE_BUCKETS[1]
    if value <= 8000:
        return REVENUE_BUCKETS[2]
    if value <= 11000:
        return REVENUE_BUCKETS[3]
    return REVENUE_BUCKETS[4]


def _fiscal_year(dates: pd.Series) -> pd.Series:
    dates = pd.to_datetime(dates, errors="coerce")
    return dates.dt.year - (dates.dt.month < 4).astype("int64")


def _safe_growth(current: float, prior: float) -> float | None:
    return None if not prior else (current - prior) / abs(prior) * 100.0


def _fiscal_month_rank(month: int) -> int:
    return (int(month) - 4) % 12


def _period_frames(ds: pd.DataFrame, filters: dict[str, list[str]]):
    """Return prior full FY, matching period, current FY, and period labels."""
    if ds.empty:
        return None, None, None, {}

    ds = ds.copy()
    ds["bill_date"] = pd.to_datetime(ds["bill_date"], errors="coerce")
    ds["_fy_start"] = _fiscal_year(ds["bill_date"])
    ds["month_num"] = pd.to_numeric(ds["month_num"], errors="coerce")
    years = ds["_fy_start"].dropna().astype(int)
    if years.empty:
        return None, None, None, {}

    selected_years = [int(value) for value in (filters.get("fy") or []) if str(value).isdigit()]
    anchor = max(selected_years) if selected_years else int(years.max())
    full = ds[ds["_fy_start"] == anchor - 1].copy()
    prior = ds[ds["_fy_start"] == anchor - 1].copy()
    current_year = ds[ds["_fy_start"] == anchor].copy()

    selected_months = [int(value) for value in (filters.get("month") or []) if str(value).isdigit()]
    if selected_months:
        current = current_year[current_year["month_num"].isin(selected_months)].copy()
        matching = prior[prior["month_num"].isin(selected_months)].copy()
        comparison_label = "SELECTED MONTHS"
    else:
        latest_date = current_year["bill_date"].max()
        if pd.isna(latest_date):
            current = current_year.iloc[0:0].copy()
            matching = prior.iloc[0:0].copy()
        else:
            current = current_year[current_year["bill_date"] <= latest_date].copy()
            fiscal_cutoff = _fiscal_month_rank(latest_date.month)
            matching = prior[prior["month_num"].map(_fiscal_month_rank) <= fiscal_cutoff].copy()
            try:
                prior_cutoff = latest_date.replace(year=latest_date.year - 1)
            except ValueError:
                prior_cutoff = latest_date.replace(year=latest_date.year - 1, day=28)
            matching = matching[matching["bill_date"] <= prior_cutoff].copy()
        comparison_label = "LFYTD"

    previous_fy = f"FY{anchor - 1}-{str(anchor)[-2:]}"
    current_fy = f"FY{anchor}-{str(anchor + 1)[-2:]}"
    periods = {
        "prior_full": previous_fy + " FULL YEAR",
        "matching": previous_fy + " " + comparison_label,
        "current": current_fy,
        "growth": "GROWTH VS " + comparison_label,
        "anchor": anchor,
    }
    return full, matching, current, periods


def _bucket_map(frame: pd.DataFrame, dim: str, bucket_col: str) -> dict:
    if frame.empty:
        return {}
    grouped = frame.groupby([dim, bucket_col], dropna=False, sort=False).size()
    totals = frame.groupby(dim, dropna=False, sort=False).size()
    result = {}
    for (raw_name, bucket), count in grouped.items():
        name = "(blank)" if pd.isna(raw_name) else str(raw_name)
        row_total = float(totals.get(raw_name, 0))
        result.setdefault(name, {})[str(bucket)] = {
            "count": float(count),
            "share_pct": float(count) / row_total * 100.0 if row_total else 0.0,
        }
    return result


def _rows(full: pd.DataFrame, matching: pd.DataFrame, current: pd.DataFrame, dim: str, bucket_col: str, bucket_order: list[str]) -> list[dict]:
    period_maps = {
        "prior_full": _bucket_map(full, dim, bucket_col),
        "matching": _bucket_map(matching, dim, bucket_col),
        "current": _bucket_map(current, dim, bucket_col),
    }
    names = set().union(*(set(mapping) for mapping in period_maps.values()))
    ordered_names = sorted(
        names,
        key=lambda name: -sum(
            period_maps["current"].get(name, {}).get(bucket, {}).get("count", 0)
            for bucket in bucket_order
        ),
    )

    result = []
    for name in ordered_names:
        periods = {}
        for period, mapping in period_maps.items():
            buckets = mapping.get(name, {})
            periods[period] = {
                bucket: buckets.get(bucket, {"count": 0.0, "share_pct": 0.0})
                for bucket in bucket_order
            }
        periods["growth"] = {}
        for bucket in bucket_order:
            base = periods["matching"][bucket]
            now = periods["current"][bucket]
            periods["growth"][bucket] = {
                "count_growth_pct": _safe_growth(now["count"], base["count"]),
                "share_pp": now["share_pct"] - base["share_pct"],
            }
        result.append({"label": name, "periods": periods})

    total = {"label": "Grand Total", "is_total": True, "periods": {}}
    for period, frame in (("prior_full", full), ("matching", matching), ("current", current)):
        counts = frame.groupby(bucket_col, dropna=False).size().to_dict() if not frame.empty else {}
        denominator = float(len(frame))
        total["periods"][period] = {
            bucket: {
                "count": float(counts.get(bucket, 0)),
                "share_pct": float(counts.get(bucket, 0)) / denominator * 100.0 if denominator else 0.0,
            }
            for bucket in bucket_order
        }
    total["periods"]["growth"] = {}
    for bucket in bucket_order:
        base = total["periods"]["matching"][bucket]
        now = total["periods"]["current"][bucket]
        total["periods"]["growth"][bucket] = {
            "count_growth_pct": _safe_growth(now["count"], base["count"]),
            "share_pp": now["share_pct"] - base["share_pct"],
        }
    result.append(total)
    return result


def run_kpi_tracking(fact: FactSpec, filters: dict[str, list[str]] | None, dimension: str) -> dict:
    if dimension not in ("store", "brand"):
        raise ValueError("KPI Tracking supports only 'store' and 'brand' dimensions")
    return _kpi_tracking_cached(fact, filter_key(filters), dimension, cache_token())


@lru_cache(maxsize=32)
def _kpi_tracking_cached(fact: FactSpec, filters_key: tuple, dimension: str, _token: tuple) -> dict:
    filters = {key: list(values) for key, values in filters_key}
    ds = _ba._load_bill_dataset(fact)
    if ds.empty:
        return {
            "dimension": dimension, "dimension_column": None, "periods": {},
            "buckets": {"quantity": QTY_BUCKETS, "revenue": REVENUE_BUCKETS},
            "quantity_rows": [], "revenue_rows": [], "meta": {"bill_count": 0},
        }

    fields = tertiary_summary._fields()
    dim_col = fields.get(dimension)
    if dim_col not in ds.columns:
        dim_col = {"store": "adonis_store_code", "brand": "brand"}[dimension]
    if dim_col not in ds.columns:
        dim_col = "brand_code" if dimension == "brand" else "adonis_store_code"
    if dim_col not in ds.columns:
        raise ValueError(f"{dimension.title()} is unavailable in the bill-level dataset")

    subset = ds
    # FY and month control the comparison windows; all other global slicers
    # narrow the bills before both bucket tables are calculated.
    for key, values in filters.items():
        if not values or key in ("fy", "month"):
            continue
        column = fields.get(key, key)
        if column not in subset.columns:
            column = {"store": "adonis_store_code", "brand": "brand_code"}.get(key, column)
        if column not in subset.columns:
            raise ValueError(f"Filter field '{key}' is unavailable in the bill-level dataset")
        wanted = {str(value) for value in values}
        subset = subset[subset[column].map(lambda value: "" if pd.isna(value) else str(value)).isin(wanted)]
    if "month_num" not in subset.columns or "bill_date" not in subset.columns:
        raise ValueError("Bill data is missing fiscal date fields")

    full, matching, current, periods = _period_frames(subset, filters)
    if full is None:
        full = matching = current = subset.iloc[0:0].copy()
        periods = {}
    full, matching, current = (frame.copy() for frame in (full, matching, current))
    for frame in (full, matching, current):
        if not frame.empty:
            frame["_qty_bucket"] = frame["qty"].map(quantity_bucket)
            frame["_revenue_bucket"] = frame["bill_val"].map(revenue_bucket)

    return {
        "dimension": dimension,
        "dimension_column": dim_col,
        "periods": periods,
        "buckets": {"quantity": QTY_BUCKETS, "revenue": REVENUE_BUCKETS},
        "quantity_rows": _rows(full, matching, current, dim_col, "_qty_bucket", QTY_BUCKETS),
        "revenue_rows": _rows(full, matching, current, dim_col, "_revenue_bucket", REVENUE_BUCKETS),
        "meta": {"bill_count": int(len(current)), "anchor_fy": periods.get("anchor")},
    }
