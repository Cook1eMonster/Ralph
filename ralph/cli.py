"""Ralph CLI - Task management for autonomous AI coding agents.

This module re-exports the CLI from ralph.interfaces.cli for backward compatibility.
The main CLI implementation is now in ralph/interfaces/cli/.
"""

from ralph.interfaces.cli import app
from ralph.interfaces.cli.main import main

__all__ = ["app", "main"]

if __name__ == "__main__":
    main()
