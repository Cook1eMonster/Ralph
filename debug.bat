@echo off
REM Ralph Debug - Run with error output visible

cd /d "%~dp0"

echo ============================================================
echo Ralph Debug Mode
echo ============================================================
echo.

echo Running setup check...
python check_setup.py
echo.

echo ============================================================
echo Starting Ralph TUI (debug mode)...
echo ============================================================
echo.

python ralph_tui.py

echo.
echo ============================================================
echo Exit code: %ERRORLEVEL%
echo ============================================================
pause
