from fastapi import APIRouter, Depends, HTTPException

from app.api.routes.auth import get_current_user
from app.models.schemas import BaseStockRequest
from app.services import base_stock_analysis

router = APIRouter(
    prefix="/base-stock",
    tags=["base-stock-analysis"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/dimensions")
def dimensions():
    return {"dimensions": base_stock_analysis.get_dimensions()}


@router.get("/slicers")
def slicers():
    return {"slicers": base_stock_analysis.get_slicers()}


@router.post("/analysis")
def analysis(req: BaseStockRequest):
    try:
        return base_stock_analysis.run_analysis(req.hierarchy, req.filters)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
