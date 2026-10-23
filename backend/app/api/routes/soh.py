import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, StreamingResponse
from app.api.routes.auth import get_current_user
from app.services import soh_analysis
from app.services.excel_export import build_workbook

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/soh", tags=["soh-analysis"], dependencies=[Depends(get_current_user)]
)


@router.get("/dates")
def dates():
    return {"dates": soh_analysis.get_dates()}


@router.get("/filters")
def filters():
    return {"filters": soh_analysis.get_filter_options()}


@router.get("/summary")
def summary(
    opening: str = Query(...),
    ending: str = Query(...),
    threshold: float = Query(1.0),
    store: str | None = None,
    brand: str | None = None,
    category: str | None = None,
    style: str | None = None,
    season: str | None = None,
):
    _validate_period(opening, ending, threshold)
    selected = {k: v for k, v in {
        "store": store, "brand": brand, "category": category,
        "style": style, "season": season,
    }.items() if v}
    try:
        result = soh_analysis.get_summary(opening, ending, threshold, selected)
        # Encode while still in this handler so unsupported/null values become
        # a logged fallback response instead of an opaque ASGI serialization 500.
        return JSONResponse(content=jsonable_encoder(result))
    except Exception:
        log.exception("SOH summary request failed")
        try:
            available_dates = soh_analysis.get_dates()
        except Exception:
            log.exception("Could not load SOH dates for summary fallback")
            available_dates = []
        return JSONResponse(content={
            "rows": [],
            "dates": available_dates,
            "warnings": [],
            "error": "SOH summary could not be calculated. Try again; the failure was recorded in server logs.",
        })



def _validate_period(opening: str, ending: str, threshold: float) -> None:
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", opening) is None or re.fullmatch(r"\d{4}-\d{2}-\d{2}", ending) is None:
        raise HTTPException(status_code=400, detail="Opening and end month must be valid SOH dates.")
    if ending < opening:
        raise HTTPException(status_code=400, detail="End month must be on or after opening month.")
    if not 0 <= threshold <= 1:
        raise HTTPException(status_code=400, detail="ST% threshold must be between 0 and 1.")


@router.get("/export")
def export(
    opening: str = Query(...),
    ending: str = Query(...),
    threshold: float = Query(1.0),
    store: str | None = None,
    brand: str | None = None,
    category: str | None = None,
    style: str | None = None,
    season: str | None = None,
):
    """Export the exact SOH rows currently shown for the selected period and filters."""
    import pandas as pd

    _validate_period(opening, ending, threshold)
    selected = {k: v for k, v in {
        "store": store, "brand": brand, "category": category,
        "style": style, "season": season,
    }.items() if v}
    result = soh_analysis.get_summary(opening, ending, threshold, selected)
    rows = result["rows"]
    columns = {
        "store": "Store", "brand": "Brand", "category": "Category",
        "style": "Style Code", "season": "Season", "opening_soh": "Start SOH",
        "ending_soh": "End SOH", "end_soh_sizewise": "End SOH Sizewise",
        "tertiary_period_sales": "Period Tertiary Net Sales",
        "tertiary_total_sales": "Total Tertiary Net Sales (All Dates)",
        "secondary_transfer_qty": "Secondary Transfer (+ Qty)",
        "secondary_return_qty": "Secondary Return (- Qty)",
        "st_pct": "ST%", "opening_soh_clearance": "Start SOH Clearance %",
    }
    df = pd.DataFrame(rows, columns=columns).rename(columns=columns)
    buffer = build_workbook(
        {"SOH Analysis": df},
        {
            "Opening month": opening,
            "End month": ending,
            "Filters applied": selected,
            "Data notes": result.get("warnings", []),
        },
        title="SOH Analysis",
    )
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="soh_analysis.xlsx"'},
    )
