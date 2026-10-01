#!/usr/bin/env bash
# Builds the frontend for production. After this, just run the backend
# (./backend/run_backend.sh) and it will serve the whole app on :8000.
# Usage:  ./build_frontend.sh
set -e
cd "$(dirname "$0")"

if [ ! -d "node_modules" ]; then
  echo "Installing frontend dependencies..."
  npm install
fi

npm run build
echo ""
echo "Build complete -> frontend/dist"
echo "Start the backend to serve the full app: cd ../backend && ./run_backend.sh"
