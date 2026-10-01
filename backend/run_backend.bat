@echo off
REM Sets up a virtual environment (first run only) and starts the API server.
REM Usage: double-click this file, or type run_backend.bat in Anaconda Prompt.
cd /d "%~dp0"

if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo.
echo Starting Retail Analytics Command Center API on http://localhost:8000
echo If frontend\dist exists, the full app is also served from this URL.
echo.
uvicorn app.main:app --host 0.0.0.0 --port 8000

pause
