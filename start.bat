@echo off
REM Daily startup script for AnesPreOp development
REM Usage: start.bat [--no-ai]

echo ============================================================
echo AnesPreOp Daily Startup
echo ============================================================

REM Navigate to ralph-tree
cd /d C:\X\AnesPreOp\ralph-tree

REM Activate backend venv
call C:\X\AnesPreOp\apps\backend\api\venv\Scripts\activate.bat 2>nul
if errorlevel 1 (
    echo ERROR: Backend venv not found
    echo Run setup.bat first
    exit /b 1
)

REM Pull latest changes
echo.
echo [1/4] Pulling latest changes...
git pull origin main
if errorlevel 1 (
    echo WARNING: Git pull failed. Continuing anyway...
)

REM Sync index (if Ollama available)
echo.
echo [2/4] Syncing codebase index...
python ralph_tree.py sync 2>nul
if errorlevel 1 (
    echo Note: Index sync skipped (Ollama not running)
)

REM Show progress
echo.
echo [3/4] Current progress:
echo ------------------------------------------------------------
python ralph_tree.py status

REM Show next task
echo.
echo [4/4] Next task:
echo ------------------------------------------------------------
if "%1"=="--no-ai" (
    python ralph_tree.py next
) else (
    python ralph_tree.py next --ai
)

echo.
echo ============================================================
echo Ready to work! Commands:
echo   ralph.bat done       - Mark task complete
echo   ralph.bat validate   - Run acceptance checks
echo   ralph.bat next --ai  - Get next task
echo ============================================================
