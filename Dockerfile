# syntax=docker/dockerfile:1
#
# Single-image build for the Retail Analytics Command Center.
#
# The FastAPI backend serves the built React SPA from the SAME origin
# (app/main.py mounts frontend/dist), which is required because the frontend
# calls a relative "/api" and the OAuth session cookie is SameSite=Lax.
#
# Build:  docker build -t retail-analytics .
# Run:    docker run -p 8000:8000 -e AUTH_SECRET_KEY=... retail-analytics

# ---------------------------------------------------------------------------
# Stage 1 - build the React (Vite) frontend
# ---------------------------------------------------------------------------
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2 - FastAPI backend + the built SPA
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app/backend

# Backend Python deps (cached layer - only rebuilds when requirements change)
COPY backend/requirements.txt ./requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

# Backend source + the seed DuckDB databases (backend/data/*_src.duckdb).
# The app copies these to a writable temp dir at startup, so no volume is
# needed; .dockerignore keeps the local .venv / working copies out.
COPY backend/ /app/backend/

# The SPA, at the exact path app/core/config.py expects:
#   FRONTEND_DIST_DIR = <backend>/../frontend/dist  ->  /app/frontend/dist
COPY --from=frontend-build /app/frontend/dist /app/frontend/dist

EXPOSE 8000

# Render injects $PORT; fall back to 8000 for a plain `docker run`.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
