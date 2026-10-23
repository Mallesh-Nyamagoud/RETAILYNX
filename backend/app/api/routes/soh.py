import re

from fastapi import APIRouter, Depends, HTTPException, Query
from app.api.routes.auth import get_current_user
from app.services import soh_analysis

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
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", opening) is None or re.fullmatch(r"\d{4}-\d{2}-\d{2}", ending) is None:
        raise HTTPException(status_code=400, detail="Opening and end month must be valid SOH dates.")
    if ending < opening:
        raise HTTPException(status_code=400, detail="End month must be on or after opening month.")
    if not 0 <= threshold <= 1:
        raise HTTPException(status_code=400, detail="ST% threshold must be between 0 and 1.")
    selected = {k: v for k, v in {
        "store": store, "brand": brand, "category": category,
        "style": style, "season": season,
    }.items() if v}
    return soh_analysis.get_summary(opening, ending, threshold, selected)
