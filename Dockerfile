# syntax=docker/dockerfile:1
#
# Single-image build for the Retail Analytics Command Center.
#
# The FastAPI backend serves the built React SPA from the SAME origin
# (app/main.py mounts frontend/dist), which is required because the frontend
# calls a relative "/api" and the session cookie is SameSite=Lax.
#
# Build (locally):
#   docker build -t retailynx .
#
# Run (locally) - see .env.example for every variable:
#   docker run --rm -p 8080:8080 \
#     -e SESSION_SECRET_KEY=dev-secret-key-replace-in-prod \
#     -e ADMIN_USERNAME=admin -e ADMIN_PASSWORD=change-me-please \
#     -e ENVIRONMENT=development retailynx
#
# On Cloud Run these values come from Secret Manager / service env vars.
# See DEPLOY_GCP.md.

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
FROM python:3.11-slim AS runtime

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

# Cloud Run injects PORT (8080 by default); the fallback keeps a plain
# `docker run` working too. A single worker keeps the one DuckDB connection
# (and its 1 GB memory cap) predictable - Cloud Run scales by *instance*.
EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1 --proxy-headers --forwarded-allow-ips=\"*\""]