@echo off
REM Ralph Factory - TUI Launcher
REM Double-click to start Ralph

echo ============================================================
echo Ralph Factory - Starting...
echo ============================================================
echo.

REM Navigate to script directory
cd /d "%~dp0"

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.11+ and try again
    echo.
    echo Download from: https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Check if dependencies are installed
python -c "import textual" >nul 2>&1
if errorlevel 1 (
    echo.
    echo First time setup - installing dependencies...
    echo This may take a minute...
    echo.
    pip install -e ".[ai]" --quiet
    if errorlevel 1 (
        echo.
        echo ERROR: Failed to install dependencies
        echo Please run manually: pip install -e ".[ai]"
        pause
        exit /b 1
    )
    echo Dependencies installed successfully!
    echo.
)

REM Check if Ollama is available and start if needed
ollama --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo NOTE: Ollama not found. Local AI features will be limited.
    echo Install from: https://ollama.com/download
    echo.
) else (
    REM Check if Ollama is already running by trying to list models
    ollama list >nul 2>&1
    if errorlevel 1 (
        echo Starting Ollama in background...
        start /B ollama serve >nul 2>&1
        REM Give it a moment to start
        timeout /t 2 /nobreak >nul
    )
)

REM Launch the TUI
echo Starting Ralph TUI...
echo.
python ralph_tui.py 2>&1
set EXITCODE=%ERRORLEVEL%

REM Handle exit
if %EXITCODE% neq 0 (
    echo.
    echo ============================================================
    echo Ralph exited with error code: %EXITCODE%
    echo ============================================================
    echo.
    echo Press any key to see error log or close this window...
    pause
)
