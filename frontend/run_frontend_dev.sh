#!/usr/bin/env bash
# Installs dependencies (first run only) and starts the Vite dev server with
# hot-reload. The dev server proxies /api to http://localhost:8000, so start
# the backend first (see ../backend/run_backend.sh).
# Usage:  ./run_frontend_dev.sh
set -e
cd "$(dirname "$0")"

if [ ! -d "node_modules" ]; then
  echo "Installing frontend dependencies..."
  npm install
fi

echo ""
echo "Starting dev server on http://localhost:5173 (proxying /api to :8000)"
echo ""
npm run dev
