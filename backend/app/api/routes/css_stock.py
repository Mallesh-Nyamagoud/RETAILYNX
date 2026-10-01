from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import StreamingResponse

from app.api.routes.auth import get_current_user
from app.models.schemas import CssSummaryRequest
from app.services import css_stock
from app.services.excel_export import build_workbook

router = APIRouter(prefix="/css-stock", tags=["css-stock-tracking"], dependencies=[Depends(get_current_user)])

# Friendly headers for the special hierarchy keys (they map onto the standard
# Summary columns rather than appearing twice in the export).
_DIM_HEADERS = {"subcategory": "Sub Category", "product_style": "Product/Style"}


def _parse_filters(filters: str | None) -> dict:
    parsed = json.loads(filters) if filters else {}
    if not isinstance(parsed, dict):
        raise ValueError("filters must be a JSON object of {column: [values]}")  # noqa: TRY004
    return parsed


@router.get("/dimensions")
def dimensions():
    return {"dimensions": css_stock.get_available_dimensions()}


@router.get("/seasons")
def seasons():
    return {"seasons": css_stock.get_seasons()}


@router.get("/slicer-options")
def slicer_options(filters: str | None = Query(default=None)):
    """Cross-filter aware slicer values: each column's options respect every
    OTHER applied filter (its own selections are ignored so multi-selects
    remain stable while narrowing the rest)."""
    try:
        parsed = _parse_filters(filters)
        return {"slicers": css_stock.get_slicer_options(parsed)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/kpis")
def kpis(season: str | None = None, filters: str | None = Query(default=None)):
    try:
        return css_stock.get_kpis(season, _parse_filters(filters))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/summary")
def summary(req: CssSummaryRequest):
    try:
        return css_stock.get_summary(req.season, req.dimensions, req.filters, req.statuses)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/export")
def export(req: CssSummaryRequest):
    """Filtered Excel download: contains ONLY the records currently represented
    by the dashboard (same season + dimensions + filters + status selection),
    so exported numbers always match the on-screen numbers exactly."""
    import pandas as pd

    try:
        result = css_stock.get_summary(req.season, req.dimensions, req.filters, req.statuses)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    rows = result["rows"]
    dims = result["dimensions"]
    want_style = "product_style" in dims

    # Store-master dims become prefixed columns; the special keys feed the
    # standard Sub Category / Product-Style columns (no duplicates).
    prefix_dims = [d for d in dims if d not in _DIM_HEADERS]
    prefix_cols = [d.upper() for d in prefix_dims]
    columns = prefix_cols + [
        "Brand",
        "Season",
        "Sub Category",
        "Product/Style",
    ]
    if want_style:
        columns.append("MRP")
    columns += [
        "Ordered Qty",
        "Dispatched Qty",
        "Pending Qty",
        "Dispatch %",
        "Status",
    ]

    data = []
    for r in rows:
        row: dict = {c: r.get(d) for d, c in zip(prefix_dims, prefix_cols)}
        row.update(
            {
                "Brand": r.get("brand"),
                "Season": r.get("season"),
                "Sub Category": r.get("subcategory"),
                "Product/Style": r.get("product_style"),
            }
        )
        if want_style:
            row["MRP"] = r.get("mrp")
        row.update(
            {
                "Ordered Qty": r.get("ordered_qty"),
                "Dispatched Qty": r.get("dispatched_qty"),
                "Pending Qty": r.get("pending_qty"),
                "Dispatch %": r.get("dispatch_pct"),
                "Status": r.get("status"),
            }
        )
        data.append(row)
    df = pd.DataFrame(data, columns=columns)

    buffer = build_workbook(
        {"CSS Stock Tracking": df},
        {
            "Season": req.season or "(all order-form seasons)",
            "Dimensions selected": req.dimensions,
            "Filters applied": req.filters,
            "Status filter": [css_stock.STATUS_LABELS.get(s, s) for s in (req.statuses or [])]
            or "(all)",
        },
        title="CSS Stock Tracking Export",
    )
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="css_stock_tracking.xlsx"'},
    )