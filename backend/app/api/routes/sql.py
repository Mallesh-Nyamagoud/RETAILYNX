from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse

from app.api.routes.auth import get_current_user
from app.models.schemas import SqlExecuteRequest, SqlExportRequest
from app.services import sql_platform

router = APIRouter(prefix="/sql", tags=["sql"], dependencies=[Depends(get_current_user)])


@router.post("/execute")
def execute(req: SqlExecuteRequest):
    try:
        return sql_platform.execute_query(req.sql, req.limit)
    except TimeoutError as e:
        raise HTTPException(status_code=408, detail=str(e))
    except Exception as e:  # noqa: BLE001 - surface DuckDB's own error text
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/export/csv")
def export_csv(req: SqlExportRequest):
    try:
        df = sql_platform.execute_for_export(req.sql)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    filename = f"{req.filename or 'query_results'}.csv"
    return StreamingResponse(
        iter([csv_bytes]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/export/xlsx")
def export_xlsx(req: SqlExportRequest):
    try:
        df = sql_platform.execute_for_export(req.sql)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))
    from app.services.excel_export import build_workbook

    buffer = build_workbook({"Results": df}, {"SQL": req.sql}, title="SQL Query Export")
    filename = f"{req.filename or 'query_results'}.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
