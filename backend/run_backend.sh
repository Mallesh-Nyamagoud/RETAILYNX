#!/usr/bin/env bash
# Sets up a virtual environment (first run only) and starts the API server.
# Usage:  ./run_backend.sh
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo ""
echo "Starting Retail Analytics Command Center API on http://localhost:8000"
echo "If frontend/dist exists, the full app is also served from this URL."
echo ""
uvicorn app.main:app --host 0.0.0.0 --port 8000
