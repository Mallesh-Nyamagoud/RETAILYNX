from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse

from app.api.routes.auth import get_current_user
from app.models.schemas import ExportRequest, MonthwiseRequest, PivotRequest
from app.services import analysis, secondary_summary
from app.services.excel_export import build_workbook

router = APIRouter(prefix="/secondary", tags=["secondary-sales-analysis"], dependencies=[Depends(get_current_user)])

FACT = analysis.FactSpec(
    schema="secondary_data",
    table="data",
    date_column="bill_date",
    qty_expr="qty",
    val_expr="value - tax",
)


@router.get("/summary/config")
def summary_config():
    return secondary_summary.config()


@router.post("/summary/config")
def summary_config_filtered(req: dict):
    return secondary_summary.config(req.get("filters", {}))


@router.post("/summary")
def summary(req: dict):
    try:
        return secondary_summary.report(req.get("row_dimension", "brand"), req.get("filters", {}))
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
        return analysis.run_monthwise(
            FACT,
            req.dimensions,
            req.filters,
            measures=[{"key": "qty", "expr": "qty"}, {"key": "val", "expr": "value - tax"}],
            growth_keys=["qty", "val"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/export")
def export(req: ExportRequest):
    import pandas as pd

    sheets: dict[str, pd.DataFrame] = {}
    try:
        if "billing" in req.include:
            pivot_result = analysis.run_pivot(FACT, req.dimensions, req.filters)
            sheets["Secondary Billing Analysis"] = pd.DataFrame(pivot_result["rows"])
        if "monthwise" in req.include:
            mw = analysis.run_monthwise(
                FACT,
                req.dimensions,
                req.filters,
                measures=[{"key": "qty", "expr": "qty"}, {"key": "val", "expr": "value - tax"}],
                growth_keys=["qty", "val"],
            )
            sheets["Monthwise Sales"] = pd.DataFrame(mw["rows"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    buffer = build_workbook(
        sheets,
        {"Dimensions selected (in order)": req.dimensions, "Filters applied": req.filters},
        title="Secondary Sales Analysis",
    )
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="secondary_sales_analysis.xlsx"'},
    )
