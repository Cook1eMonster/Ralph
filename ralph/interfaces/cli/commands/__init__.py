"""CLI command groups for Ralph.

This package contains individual command groups that are registered
with the main Typer app. Each module provides a set of related commands.

Command groups:
- task: Task tree management (next, done, status, etc.)
- worker: Parallel worker management (assign, workers, merge, etc.)
- context: AI context commands (enrich, sync)
- project: Project management (init)

Each command group is a Typer app that gets registered
with the main app using app.add_typer().
"""

from ralph.interfaces.cli.commands import context, project, task, worker

__all__ = ["task", "project", "worker", "context"]
