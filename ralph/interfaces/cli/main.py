"""Entry point for the Ralph CLI.

This module provides the main entry point for the Ralph CLI.
It imports the Typer app and runs it.

Usage:
    python -m ralph.interfaces.cli.main

Or via installed entry point:
    ralph <command>
"""

from ralph.interfaces.cli import app


def main() -> None:
    """Run the Ralph CLI application."""
    app()


if __name__ == "__main__":
    main()
