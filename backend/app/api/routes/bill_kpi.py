"""
Bill_No Based KPI Analysis routes.

New "Module V" subpage API.  Reuses the FactSpec + bill-level dataset from the
tertiary module (single source of truth for the bill grain); adds date-range
mode, SPD/Active_Days KPIs, a pivot-style dimensional summary, distribution
tables and Top-N bills (multiples of 5) with brand-contribution breakdown.

Endpoints:
  GET  /bill-kpi/dimensions            - selectable dimension catalog
  GET  /bill-kpi/slicers               - cross-filter aware slicer options
  POST /bill-kpi/analysis              - the full analysis payload
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Depends

from app.api.routes.auth import get_current_user
from app.models.schemas import BillKpiRequest
from app.services import analysis, bill_kpi

router = APIRouter(prefix="/bill-kpi", tags=["bill-kpi-analysis"], dependencies=[Depends(get_current_user)])

FACT = analysis.FactSpec(
    schema="tertiary_data",
    table="data",
    date_column="date",
    qty_expr="qty",
    val_expr="bill_val",
)


@router.get("/dimensions")
def dimensions():
    return {"dimensions": bill_kpi.bill_dimensions()}


@router.get("/slicers")
def slicers(filters: str | None = Query(default=None)):
    """Cross-filter aware slicer options for the global filter bar.

    Pass the currently applied filters as a JSON string and every column's
    options are narrowed to the values that still exist under the OTHER
    applied filters (a column's own selection is ignored so multi-selects
    stay stable while the list narrows).
    """
    import json

    try:
        parsed = json.loads(filters) if filters else {}
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid filters JSON: {e}")
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="filters must be a JSON object")
    try:
        return {"slicers": bill_kpi.get_slicers(FACT, parsed)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/analysis")
def analysis_route(req: BillKpiRequest):
    """Bill_No Based KPI Analysis (Module V).

    Everything is computed server-side on the cached bill-level dataset:
    INTERNAL_BILL_ID = ADONIS_CODE-FY{yy}-{MM}-BILL_NO, invalid 'NA'/blank bill
    numbers excluded, buckets classified on aggregated bill figures, SPD uses
    the brand-anchored Active_Days window (see meta.active_days_rule).
    """
    try:
        return bill_kpi.run_bill_kpi_analysis(
            FACT,
            req.filters,
            dimension=req.dimension,
            date_range=req.date_range,
            top_n=req.top_n,
            dist_dim=req.dist_dim,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))