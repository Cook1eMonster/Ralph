@echo off
REM Ralph Tree Setup Script for Windows
REM Uses the existing backend venv

echo ============================================================
echo Ralph Tree Setup
echo ============================================================

REM Navigate to backend and activate venv
cd /d C:\X\AnesPreOp\apps\backend\api

if not exist "venv\Scripts\activate.bat" (
    echo ERROR: Backend venv not found at apps\backend\api\venv
    echo Run: python -m venv venv
    exit /b 1
)

echo Activating backend venv...
call venv\Scripts\activate.bat

REM Install ralph-tree dependencies (won't conflict with backend)
echo.
echo Installing ralph-tree dependencies...
pip install chromadb ollama mcp --quiet

REM Restore any backend deps that might have been affected
echo.
echo Ensuring backend dependencies are intact...
pip install -r requirements.txt --quiet

REM Navigate to ralph-tree
cd /d C:\X\AnesPreOp\ralph-tree

REM Check Ollama models
echo.
echo Checking Ollama models...
ollama list

echo.
echo ============================================================
echo Setup complete!
echo ============================================================
echo.
echo Next steps:
echo   1. Make sure Ollama is running (check system tray)
echo   2. If qwen3:8b is missing: ollama pull qwen3:8b
echo   3. Index codebase: python ralph_context.py index
echo   4. Configure MCP in ~/.claude/settings.json
echo.
echo To use ralph-tree, always activate backend venv first:
echo   cd C:\X\AnesPreOp\apps\backend\api
echo   venv\Scripts\activate
echo   cd ..\..\ralph-tree
echo   python ralph_tree.py status
echo.
