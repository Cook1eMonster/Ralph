"""Interfaces layer for Ralph.

This layer contains adapters for external interactions:
- CLI: Command-line interface using Typer
- API: REST API using FastAPI (in ralph/api.py for now)
- TUI: Terminal UI using Textual (in ralph/tui/ for now)

The interfaces layer is responsible for:
- Accepting user input and validating it
- Calling application services
- Formatting output for the user
"""

from ralph.interfaces.cli import app

__all__ = ["app"]
