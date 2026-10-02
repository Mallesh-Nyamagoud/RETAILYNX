"""FastAPI application entry point.

One process serves both the JSON API (`/api/*`) and the compiled React SPA, so
the session cookie is always same-origin. Login is username + password (see
`app.api.routes.auth`); there is no third-party identity provider.

Cloud Run starts this module with:
    uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} \
        --workers 1 --proxy-headers --forwarded-allow-ips="*"
"""
from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import (
    auth,
    bill_kpi,
    css_stock,
    meta,
    secondary,
    sql,
    store_master,
    tertiary,
)
from app.core.config import (
    API_PREFIX,
    APP_NAME,
    CORS_ORIGINS,
    FRONTEND_DIST_DIR,
    validate_startup_config,
)
from app.core.database import init_db
from app.services.auth import init_db as init_auth_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail fast and loudly on missing/invalid configuration BEFORE serving
    # anything: a misconfigured revision stops with an actionable message
    # instead of running with no session secret or an unusable user database.
    validate_startup_config()
    init_db()
    init_auth_db()
    yield
    from app.core.database import checkpoint_and_close

    checkpoint_and_close()


app = FastAPI(title=APP_NAME, version="1.0.0", lifespan=lifespan)

# Same-origin single-image deployment, so CORS is only a safety net for the
# separate-port local dev setup (vite proxies /api, so it does not need it).
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(meta.router, prefix=API_PREFIX)
app.include_router(sql.router, prefix=API_PREFIX)
app.include_router(secondary.router, prefix=API_PREFIX)
app.include_router(tertiary.router, prefix=API_PREFIX)
app.include_router(store_master.router, prefix=API_PREFIX)
app.include_router(css_stock.router, prefix=API_PREFIX)
app.include_router(bill_kpi.router, prefix=API_PREFIX)


@app.get("/health")
def health() -> dict:
    """Cloud Run liveness/readiness probe - unauthenticated on purpose."""
    return {"status": "ok", "app": APP_NAME}


# ---------------------------------------------------------------------------
# Serve the built frontend (npm run build -> frontend/dist) when it exists, so
# the whole application runs from this single FastAPI process. In dev mode
# (npm run dev / vite) the frontend runs on its own port and this block is
# simply skipped.
# ---------------------------------------------------------------------------
if FRONTEND_DIST_DIR.exists():
    assets_dir = FRONTEND_DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str):
        """Serve static files and SPA deep links.

        Static files (the logo, favicon, ...) are returned as-is; every other
        path falls through to index.html so client-side routing works on a
        hard refresh. The SPA itself enforces the login redirect (see
        frontend/src/App.jsx) - the data is what is protected server-side.
        """
        candidate = FRONTEND_DIST_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST_DIR / "index.html")