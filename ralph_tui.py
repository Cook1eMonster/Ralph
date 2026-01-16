#!/usr/bin/env python3
"""Ralph TUI - Terminal User Interface Entry Point.

Usage:
    python ralph_tui.py                    # Launch with project launcher
    python ralph_tui.py --project myproj   # Launch with specific project
    python ralph_tui.py -p myproj          # Short form
"""

import argparse
import sys
from typing import Optional


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="ralph_tui",
        description="Ralph TUI - Terminal interface for task management",
    )

    parser.add_argument(
        "-p", "--project",
        type=str,
        default=None,
        help="Project ID to load directly (skips launcher)",
        metavar="PROJECT_ID",
    )

    parser.add_argument(
        "--version",
        action="version",
        version="Ralph TUI 0.1.0",
    )

    return parser.parse_args()


def run_tui(project_id: Optional[str] = None) -> int:
    """Launch the Ralph TUI application.

    Args:
        project_id: Optional project ID to load directly.

    Returns:
        Exit code (0 for success, non-zero for errors).
    """
    try:
        from ralph.tui.app import RalphApp

        app = RalphApp(project_id=project_id)
        app.run()
        return 0

    except ImportError as e:
        print(f"Error: Missing dependency - {e}")
        print("Install required packages: pip install textual")
        return 1

    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        return 130

    except Exception as e:
        print(f"Error: {e}")
        return 1


def main() -> int:
    """Main entry point."""
    args = parse_args()
    return run_tui(project_id=args.project)


if __name__ == "__main__":
    sys.exit(main())
