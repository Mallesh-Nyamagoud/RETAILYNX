from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.routes.auth import get_current_user
from app.core.database import (
    get_enrichment_status,
    get_full_schema_tree,
    list_columns,
    list_databases,
    list_tables,
    recompute_store_master_enrichment,
    reset_to_seed_data,
)
from app.services.sql_platform import SQL_KEYWORDS, list_sql_functions

router = APIRouter(prefix="/meta", tags=["meta"], dependencies=[Depends(get_current_user)])


@router.get("/schema-tree")
def schema_tree():
    """Full database -> table -> column tree. Powers the SQL Platform's
    Database Explorer panel and drives its autocomplete engine."""
    return {"databases": get_full_schema_tree()}


@router.get("/databases")
def databases():
    return {"databases": list_databases()}


@router.get("/tables")
def tables(database: str | None = None):
    return {"tables": list_tables(database)}


@router.get("/columns")
def columns(database: str | None = None, table: str | None = None):
    return {"columns": list_columns(database, table)}


@router.get("/sql-functions")
def sql_functions():
    return {"functions": list_sql_functions(), "keywords": SQL_KEYWORDS}


@router.get("/enrichment-status")
def enrichment_status():
    """State of the background TER.MIN/TER.MAX/STORE STATUS recompute that
    kicks off automatically on startup: idle / running / done / error."""
    return get_enrichment_status()


@router.post("/recompute-store-status")
def recompute_store_status():
    """Manually re-run the TER.MIN/TER.MAX/STORE STATUS enrichment against
    the latest tertiary data (also runs automatically at startup)."""
    result = recompute_store_master_enrichment()
    return {"status": "ok", **result}


@router.post("/reset-to-seed")
def reset_to_seed():
    """Factory-reset all working databases back to the originally uploaded
    files, discarding any edits made in Store Master."""
    reset_to_seed_data()
    return {"status": "ok"}
