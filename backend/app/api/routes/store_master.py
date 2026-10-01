from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import StreamingResponse

from app.api.routes.auth import get_current_user
from app.models.schemas import StoreCreateRequest, StoreUpdateRequest
from app.services import store_master
from app.services.excel_export import build_workbook

router = APIRouter(prefix="/store-master", tags=["store-master"], dependencies=[Depends(get_current_user)])


@router.get("/columns")
def columns():
    return {"columns": store_master.get_all_columns()}


@router.get("/slicers")
def slicers():
    return {"slicers": store_master.get_slicer_options()}


@router.get("/kpis")
def kpis(filters: str | None = Query(default=None)):
    parsed = json.loads(filters) if filters else {}
    return store_master.get_kpis(parsed)


@router.get("/table")
def table(
    filters: str | None = Query(default=None),
    search: str | None = None,
    sort_by: str | None = None,
    sort_dir: str = "asc",
    page: int = 1,
    page_size: int = 50,
):
    parsed = json.loads(filters) if filters else {}
    try:
        return store_master.get_table(parsed, search, sort_by, sort_dir, page, page_size)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{adonis_store_code}/{brand_code}")
def update(adonis_store_code: str, brand_code: str, req: StoreUpdateRequest):
    try:
        return store_master.update_store(adonis_store_code, brand_code, req.updates, req.password)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("")
def create(req: StoreCreateRequest):
    try:
        return store_master.create_store(req.adonis_store_code, req.brand_code, req.values, req.password)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{adonis_store_code}/{brand_code}")
def delete(adonis_store_code: str, brand_code: str, password: str | None = None):
    try:
        store_master.delete_store(adonis_store_code, brand_code, password)
        return {"status": "ok"}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get("/export")
def export(filters: str | None = Query(default=None), search: str | None = None):
    import pandas as pd

    parsed = json.loads(filters) if filters else {}
    result = store_master.get_table(parsed, search, None, "asc", page=1, page_size=1_000_000)
    df = pd.DataFrame(result["rows"])
    buffer = build_workbook(
        {"Store Master": df}, {"Filters applied": parsed, "Search": search or "(none)"},
        title="Store Master Export",
    )
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="store_master.xlsx"'},
    )
