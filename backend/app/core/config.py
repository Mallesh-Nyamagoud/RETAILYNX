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

try:  # local dev convenience: make `backend/.env` visible to direct imports
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - dotenv is in requirements.txt
    pass


def _raw(name: str) -> str | None:
    """Environment value with surrounding whitespace removed (None if unset).

    Blank values are deliberately treated the same as *unset*: a stray space in
    a Cloud Run secret can therefore never silently lock everyone out.
    """
    value = os.environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _text(name: str, default: str = "") -> str:
    return _raw(name) or default


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
# `ENVIRONMENT=production` is what Cloud Run / the Docker image is started with.
# It turns on the stricter startup validation and the `Secure` session cookie.
ENVIRONMENT = _text("ENVIRONMENT", "development").lower()
IS_PRODUCTION = ENVIRONMENT in {"production", "prod"}

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = BACKEND_DIR.parent

# DATA_DIR is where the analytics data (seed DuckDB files and/or Parquet) lives.
# `APP_DATA_DIR` is still honoured as a legacy alias.
DATA_DIR = Path(_text("DATA_DIR") or _text("APP_DATA_DIR") or (BACKEND_DIR / "data"))
if not DATA_DIR.is_absolute():
    DATA_DIR = (REPO_ROOT / DATA_DIR).resolve()
try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
except OSError:  # reported clearly by validate_startup_config() instead
    pass

# ---------------------------------------------------------------------------
# Required secrets (checked by validate_startup_config at startup)
# ---------------------------------------------------------------------------
SESSION_SECRET_KEY = _text("SESSION_SECRET_KEY")
ADMIN_USERNAME = _text("ADMIN_USERNAME")
ADMIN_PASSWORD = _text("ADMIN_PASSWORD")

# The placeholder the old dev config shipped - rejected in production so a real
# deployment can never sign its session cookies with a public string.
_DEV_SECRET_PLACEHOLDER = "dev-secret-key-replace-in-prod"

# ---------------------------------------------------------------------------
# User (auth) database.  Cloud Run's disk is ephemeral, so production points
# this at an external Postgres; plain SQLite under DATA_DIR is the local-dev
# default.  See app/services/auth.py for the URL normalisation.
# ---------------------------------------------------------------------------
DEFAULT_SQLITE_URL = f"sqlite:///{(DATA_DIR / 'retailynx_auth.db').as_posix()}"
DATABASE_URL = _text("DATABASE_URL") or DEFAULT_SQLITE_URL

# ---------------------------------------------------------------------------
# DuckDB tuning.  Cloud Run is configured with 2 GiB, so DuckDB is capped well
# below that: a heavy query spills to disk instead of getting the container
# OOM-killed.
# ---------------------------------------------------------------------------
DUCKDB_MEMORY_LIMIT = _text("DUCKDB_MEMORY_LIMIT", "1GB")
try:
    DUCKDB_THREADS = max(1, int(_text("DUCKDB_THREADS", "2")))
except ValueError:
    DUCKDB_THREADS = 2


def parquet_files_for(dataset: str) -> list[Path]:
    """Parquet file(s) in DATA_DIR that should back `dataset`, if any.

    Accepts either `DATA_DIR/<dataset>.parquet` / `DATA_DIR/<dataset>-*.parquet`
    or a `DATA_DIR/<dataset>/` directory of part files. Nothing is read into
    memory here - the paths go straight to DuckDB's `read_parquet`.
    """
    try:
        candidates = sorted(DATA_DIR.glob(f"{dataset}*.parquet")) + sorted(
            DATA_DIR.glob(f"{dataset}/*.parquet")
        )
    except OSError:
        return []
    seen: set[Path] = set()
    out: list[Path] = []
    for path in candidates:
        if path not in seen:
            seen.add(path)
            out.append(path)
    return out


def missing_required_config() -> list[str]:
    """Names of the env vars that are missing for the current environment.

    SESSION_SECRET_KEY / ADMIN_USERNAME / ADMIN_PASSWORD are ALWAYS required.
    DATABASE_URL and DATA_DIR fall back to their documented local-dev defaults
    (SQLite under DATA_DIR) *unless* ENVIRONMENT=production, where every
    deployment variable must be supplied explicitly by Cloud Run.
    """
    missing: list[str] = []
    if not SESSION_SECRET_KEY:
        missing.append("SESSION_SECRET_KEY")
    if not ADMIN_USERNAME:
        missing.append("ADMIN_USERNAME")
    if not ADMIN_PASSWORD:
        missing.append("ADMIN_PASSWORD")
    if IS_PRODUCTION:
        for name in ("DATABASE_URL", "DATA_DIR"):
            if not _raw(name):
                missing.append(name)
    return missing


def validate_startup_config() -> None:
    """Fail *clearly* and immediately when required configuration is missing.

    Called from the FastAPI lifespan handler, so a misconfigured deployment
    stops with an actionable message instead of booting into a half-working
    state (or accepting logins it cannot persist).
    """
    problems: list[str] = []

    missing = missing_required_config()
    if missing:
        problems.append("missing required environment variable(s): " + ", ".join(missing))

    if SESSION_SECRET_KEY and len(SESSION_SECRET_KEY) < 16:
        problems.append("SESSION_SECRET_KEY must be at least 16 characters long")
    if IS_PRODUCTION and SESSION_SECRET_KEY == _DEV_SECRET_PLACEHOLDER:
        problems.append(
            "SESSION_SECRET_KEY is still the public development placeholder - "
            "generate a real one (e.g. `openssl rand -hex 32`)"
        )
    if ADMIN_PASSWORD and len(ADMIN_PASSWORD) < 8:
        problems.append("ADMIN_PASSWORD must be at least 8 characters long")

    if problems:
        raise RuntimeError(
            "Invalid application configuration:\n  - "
            + "\n  - ".join(problems)
            + "\n\nSee .env.example for the full list of variables. "
            f"(ENVIRONMENT={ENVIRONMENT or 'unset'})"
        )


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
