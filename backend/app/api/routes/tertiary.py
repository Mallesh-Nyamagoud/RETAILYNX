from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse

from app.api.routes.auth import get_current_user
from app.models.schemas import (
    BillAnalysisRequest,
    CategoryBrandAnalysisRequest,

    CategoryAnalysisRequest,
    ExportRequest,
    MonthwiseRequest,
    PivotRequest,
)
from app.services import analysis, bill_analysis, tertiary_summary
from app.services.excel_export import build_workbook

router = APIRouter(prefix="/tertiary", tags=["tertiary-sales-analysis"], dependencies=[Depends(get_current_user)])

FACT = analysis.FactSpec(
    schema="tertiary_data",
    table="data",
    date_column="date",
    qty_expr="qty",
    val_expr="bill_val",
)

_MONTHWISE_MEASURES = [
    {"key": "qty", "expr": "qty"},
    {"key": "mrp_value", "expr": "mrp_value"},
    {"key": "discount", "expr": "discount"},
    {"key": "bill_val", "expr": "bill_val"},
]
_MONTHWISE_RATIOS = [
    {"key": "discount_pct", "numerator": "discount", "denominator": "mrp_value"}
]
_MONTHWISE_GROWTH_KEYS = ["bill_val", "qty"]


@router.get("/summary/config")
def summary_config():
    return tertiary_summary.config()

@router.post("/summary/config")
def summary_config_filtered(req: dict):
    return tertiary_summary.config(req.get("filters", {}))
@router.post("/summary")
def summary(req: dict):
    try:
        return tertiary_summary.report(req.get("row_dimension", "brand"), req.get("filters", {}))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
@router.get("/dimensions")
def dimensions():
    return {"dimensions": analysis.get_dimension_catalog()}


@router.get("/slicers")
def slicers():
    return {"slicers": analysis.get_slicer_options()}


@router.post("/pivot")
def pivot(req: PivotRequest):
    try:
        return analysis.run_pivot(FACT, req.dimensions, req.filters)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/monthwise")
def monthwise(req: MonthwiseRequest):
    try:
        return analysis.run_monthwise_rows(
            FACT,
            req.dimensions,
            req.filters,
            measures=_MONTHWISE_MEASURES,
            ratio_measures=_MONTHWISE_RATIOS,
            growth_keys=_MONTHWISE_GROWTH_KEYS,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/bill-analysis")
def bill_analysis_route(req: BillAnalysisRequest):
    """Bill No. Based Analysis - everything computed on the bill-level
    dataset (INTERNAL_BILL_ID = ADONIS_CODE-FY{yy}-{MM}-BILL_NO, invalid
    'NA'/blank bill numbers excluded)."""
    try:
        return bill_analysis.run_bill_analysis(
            FACT,
            req.filters,
            hierarchy=req.hierarchy,
            qty_dim=req.qty_dim,
            value_dim=req.value_dim,
            top_n=req.top_n,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/category-analysis")
def category_analysis_route(req: CategoryAnalysisRequest):
    """Category Performance Analysis - Category x Sub-Category pivot whose ROWS
    are the page-level Row Hierarchy (level 1 / level 2) and whose numbers
    respect the page-level global slicers."""
    try:
        from app.services import category_analysis as ca
        return ca.run_category_analysis(req.filters, req.hierarchy)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
@router.post("/category-brand-analysis")
def category_brand_analysis_route(req: CategoryBrandAnalysisRequest):
    try:
        from app.services import category_analysis as ca
        return ca.run_category_brand_analysis(req.filters)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))





@router.post("/export")
def export(req: ExportRequest):
    import pandas as pd

    sheets: dict[str, pd.DataFrame] = {}
    try:
        if "billing" in req.include:
            pivot_result = analysis.run_pivot(FACT, req.dimensions, req.filters)
            sheets["Tertiary Sales Analysis"] = pd.DataFrame(pivot_result["rows"])
        if "monthwise" in req.include:
            mw = analysis.run_monthwise_rows(
                FACT,
                req.dimensions,
                req.filters,
                measures=_MONTHWISE_MEASURES,
                ratio_measures=_MONTHWISE_RATIOS,
                growth_keys=_MONTHWISE_GROWTH_KEYS,
            )
            sheets["Monthwise Sales"] = pd.DataFrame(mw["rows"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    buffer = build_workbook(
        sheets,
        {"Dimensions selected (in order)": req.dimensions, "Filters applied": req.filters},
        title="Tertiary Sales Analysis",
    )
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="tertiary_sales_analysis.xlsx"'},
    )
