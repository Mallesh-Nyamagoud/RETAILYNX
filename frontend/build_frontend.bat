@echo off
REM Builds the frontend for production. After this, just run the backend
REM (backend\run_backend.bat) and it will serve the whole app on :8000.
REM Usage: double-click this file, or type build_frontend.bat in Anaconda Prompt.
cd /d "%~dp0"

if not exist "node_modules" (
    echo Installing frontend dependencies...
    call npm install
)

call npm run build

echo.
echo Build complete -> frontend\dist
echo Start the backend to serve the full app: cd ..\backend  then run_backend.bat
echo.
pause
