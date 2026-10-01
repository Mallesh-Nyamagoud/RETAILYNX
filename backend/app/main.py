from __future__ import annotations
from dotenv import load_dotenv
load_dotenv()

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes import (
    bill_kpi,
    css_stock,
    meta,
    secondary,
    sql,
    store_master,
    tertiary,
    auth,
)
from app.core.config import API_PREFIX, APP_NAME, CORS_ORIGINS, FRONTEND_DIST_DIR
from app.core.database import init_db
from app.services.auth import init_db as init_auth_db
import os


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    init_auth_db()
    yield
    from app.core.database import checkpoint_and_close

    checkpoint_and_close()


app = FastAPI(title=APP_NAME, version="1.0.0", lifespan=lifespan)

# Required for Authlib OAuth state storage
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("AUTH_SECRET_KEY", "dev-secret-key-replace-in-prod"),
    session_cookie="retailynx_oauth_state",
    max_age=300
)

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


@app.get(f"{API_PREFIX}/health")
def health():
    return {"status": "ok", "app": APP_NAME}


# ---------------------------------------------------------------------------
# Serve the built frontend (npm run build -> frontend/dist) if it exists, so
# the whole application can be run from this single FastAPI process. In dev
# mode (npm run dev / vite), the frontend runs on its own port instead and
# this block is simply skipped.
# ---------------------------------------------------------------------------
if FRONTEND_DIST_DIR.exists():
    assets_dir = FRONTEND_DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        candidate = FRONTEND_DIST_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST_DIR / "index.html")

