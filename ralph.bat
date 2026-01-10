@echo off
REM Quick launcher for ralph-tree commands
REM Usage: ralph.bat <command> [args]
REM Examples:
REM   ralph.bat status
REM   ralph.bat next --ai
REM   ralph.bat index

REM Activate backend venv
call C:\X\AnesPreOp\apps\backend\api\venv\Scripts\activate.bat 2>nul

REM Navigate to ralph-tree
cd /d C:\X\AnesPreOp\ralph-tree

REM Handle special commands
if "%1"=="index" (
    python ralph_context.py index
    exit /b
)

if "%1"=="search" (
    python ralph_context.py search %2 %3 %4 %5
    exit /b
)

if "%1"=="mcp" (
    python ralph_context_mcp.py
    exit /b
)

REM Default: run ralph_tree.py with all args
python ralph_tree.py %*
