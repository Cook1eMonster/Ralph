#!/usr/bin/env python3
"""Check Ralph setup and dependencies."""

import sys

def main():
    print("=" * 50)
    print("Ralph Setup Check")
    print("=" * 50)
    print()

    errors = []

    # Check Python version
    print(f"Python: {sys.version}")
    if sys.version_info < (3, 11):
        errors.append("Python 3.11+ required")
    print()

    # Check required packages
    print("Checking dependencies...")

    packages = [
        ("textual", "TUI framework"),
        ("pydantic", "Data models"),
        ("fastapi", "API server"),
    ]

    for pkg, desc in packages:
        try:
            __import__(pkg)
            print(f"  [OK] {pkg} - {desc}")
        except ImportError as e:
            print(f"  [FAIL] {pkg} - {e}")
            errors.append(f"Missing {pkg}")

    print()

    # Check Ralph modules
    print("Checking Ralph modules...")
    modules = [
        "ralph.models",
        "ralph.storage",
        "ralph.core",
        "ralph.global_config",
        "ralph.ai_executor",
        "ralph.tui.app",
        "ralph.tui.screens",
        "ralph.tui.screens.ai_config",
        "ralph.tui.screens.project_select",
        "ralph.tui.screens.folder_browser",
        "ralph.tui.screens.new_project",
        "ralph.tui.screens.main",
    ]

    for mod in modules:
        try:
            __import__(mod)
            print(f"  [OK] {mod}")
        except ImportError as e:
            print(f"  [FAIL] {mod} - {e}")
            errors.append(f"Import error: {mod}")
        except Exception as e:
            print(f"  [ERROR] {mod} - {type(e).__name__}: {e}")
            errors.append(f"Error in {mod}: {e}")

    print()

    # Check optional AI packages
    print("Checking optional AI packages...")
    ai_packages = [
        ("chromadb", "Vector database"),
        ("ollama", "Local LLM"),
    ]

    for pkg, desc in ai_packages:
        try:
            __import__(pkg)
            print(f"  [OK] {pkg} - {desc}")
        except ImportError:
            print(f"  [SKIP] {pkg} - {desc} (optional)")

    print()
    print("=" * 50)

    if errors:
        print(f"ERRORS FOUND ({len(errors)}):")
        for err in errors:
            print(f"  - {err}")
        print()
        print("Fix errors and try again.")
        return 1
    else:
        print("All checks passed! Ralph is ready to run.")
        return 0


if __name__ == "__main__":
    try:
        exit_code = main()
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        exit_code = 1

    input("\nPress Enter to exit...")
    sys.exit(exit_code)
