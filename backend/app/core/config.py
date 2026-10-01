"""
Central configuration for the Web Analysis Application backend.

All paths, database names and tunables live here so nothing is hard-coded
deep inside the business logic. Values can be overridden with environment
variables, which keeps the app friendly to different local setups without
any code changes.
"""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = Path(os.environ.get("APP_DATA_DIR", BACKEND_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Seed (read-only, shipped with the repo) databases. These are never
# mutated - they are the "factory reset" source of truth.
SEED_FILES = {
    "store_master": DATA_DIR / "store_master_src.duckdb",
    "order_form": DATA_DIR / "order_form_src.duckdb",
    "secondary_data": DATA_DIR / "secondary_data_src.duckdb",
    "tertiary_data": DATA_DIR / "tertiary_data_src.duckdb",
}

# Working (writable) copies that the running application actually attaches.
# store_master is editable (admin edit screen + auto-computed status columns)
# so it must live on a writable copy; the others are opened read-only for
# safety/perf but are still copied locally so the app never touches the
# user's uploaded originals.
import tempfile

# A unique temporary directory for this process's writable DB copies. This
# is the key to making --reload work without file-locking IOErrors: each new
# dev server process works with a completely separate set of files.
WORKING_DIR = Path(tempfile.gettempdir()) / f"retail_app_{os.getpid()}"

# Logical schema name each working file is ATTACHed under inside the single
# DuckDB catalog connection. These names are what the SQL Platform / schema
# explorer will show as "databases".
ATTACH_SCHEMAS = {
    "store_master": "store_master",
    "order_form": "order_form",
    "secondary_data": "secondary_data",
    "tertiary_data": "tertiary_data",
}

# The primary fact table inside each attached database (discovered dynamically
# at startup too - this is just used as a sensible default/fallback).
DEFAULT_TABLES = {
    "store_master": "store_details",
    "order_form": "order_form",
    "secondary_data": "data",
    "tertiary_data": "data",
}

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
APP_NAME = "Retail Analytics Command Center"
API_PREFIX = "/api"
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*").split(",")

# Financial year starts in April (month=4). This is a business rule from the
# requirements doc (LFY FULL = April-March) - centralised here so it is the
# single place to change if a different fiscal calendar is ever needed.
FY_START_MONTH = 4

# Frontend production build (created by `npm run build` in ../frontend).
# If present, the backend serves it directly so the whole app can be run
# from a single process - genuinely "zero cost, easy to deploy locally".
FRONTEND_DIST_DIR = BACKEND_DIR.parent / "frontend" / "dist"

# Safety limits
MAX_SQL_ROWS_PREVIEW = 5000
MAX_SQL_ROWS_EXPORT = 500_000
QUERY_TIMEOUT_SECONDS = 60
