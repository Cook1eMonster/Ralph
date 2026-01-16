#!/usr/bin/env python3
"""Debug script to trace TUI startup issues."""

import sys
import traceback
import asyncio

async def test_startup():
    """Test the TUI startup sequence."""
    print("Testing TUI startup...")

    try:
        from ralph.tui.app import RalphApp
        print("1. RalphApp imported OK")

        app = RalphApp()
        print("2. RalphApp instantiated OK")

        # Test the first screen
        from ralph.tui.screens.ai_config import AIConfigScreen
        print("3. AIConfigScreen imported OK")

        # Test storage
        from ralph.storage import list_projects
        projects = list_projects()
        print(f"4. Found {len(projects)} projects")

        # Test project select screen
        from ralph.tui.screens.project_select import ProjectSelectScreen
        print("5. ProjectSelectScreen imported OK")

        # Run the app with error trapping
        print("\n6. Starting app (will run until closed)...")
        await app.run_async()

    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}")
        traceback.print_exc()
        return 1

    return 0

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(test_startup())
    except KeyboardInterrupt:
        print("\nInterrupted")
        exit_code = 0
    except Exception as e:
        print(f"\nFatal error: {e}")
        traceback.print_exc()
        exit_code = 1

    sys.exit(exit_code)
