@echo off
REM Installs dependencies (first run only) and starts the Vite dev server with
REM hot-reload. The dev server proxies /api to http://localhost:8000, so start
REM the backend first (see ..\backend\run_backend.bat).
REM Usage: double-click this file, or type run_frontend_dev.bat in Anaconda Prompt.
cd /d "%~dp0"

if not exist "node_modules" (
    echo Installing frontend dependencies...
    call npm install
)

echo.
echo Starting dev server on http://localhost:5173 (proxying /api to :8000)
echo.
call npm run dev

pause
