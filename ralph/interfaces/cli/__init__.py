"""CLI interface for Ralph using Typer.

This module provides the command-line interface for Ralph,
a task management system for autonomous AI coding agents.

Usage:
    ralph init              # Initialize a new project
    ralph status            # Show tree progress
    ralph next              # Get next task
    ralph done              # Mark current task done

The CLI is structured as:
- app: Main Typer application
- commands/: Individual command groups (task, worker, context, etc.)
- common.py: Shared utilities for CLI commands
- main.py: Entry point that runs the app
"""

from typing import Optional

import typer

from ralph import __version__

# Import command groups
from ralph.interfaces.cli.commands import context, project, task, worker

# Create the main Typer application
app = typer.Typer(
    name="ralph",
    help="Task management for autonomous AI coding agents",
    add_completion=False,
    no_args_is_help=True,
)


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        typer.echo(f"ralph version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        help="Show version and exit",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """Ralph - Task management for autonomous AI coding agents.

    Break down large software projects into ~60k token tasks
    that AI agents can execute in parallel.
    """
    pass


# =============================================================================
# Register Command Groups
# =============================================================================

app.add_typer(task.app, name="task")
app.add_typer(project.app, name="project")
app.add_typer(worker.app, name="worker")
app.add_typer(context.app, name="context")


# =============================================================================
# Top-Level Shortcuts for Common Commands
# =============================================================================


@app.command("next")
def next_task(
    project: Optional[str] = typer.Option(
        None,
        "--project",
        "-p",
        help="Project ID (or set RALPH_PROJECT env var)",
        envvar="RALPH_PROJECT",
    ),
    ai: bool = typer.Option(False, "--ai", help="Use AI-enriched context"),
) -> None:
    """Show next task (shortcut for 'task next')."""
    task.next_task(project=project, ai=ai)


@app.command("done")
def done(
    project: Optional[str] = typer.Option(
        None,
        "--project",
        "-p",
        help="Project ID (or set RALPH_PROJECT env var)",
        envvar="RALPH_PROJECT",
    ),
) -> None:
    """Mark task done (shortcut for 'task done')."""
    task.done(project=project)


@app.command("status")
def status(
    project: Optional[str] = typer.Option(
        None,
        "--project",
        "-p",
        help="Project ID (or set RALPH_PROJECT env var)",
        envvar="RALPH_PROJECT",
    ),
) -> None:
    """Show status (shortcut for 'task status')."""
    task.status(project)


@app.command("validate")
def validate(
    project: Optional[str] = typer.Option(
        None,
        "--project",
        "-p",
        help="Project ID (or set RALPH_PROJECT env var)",
        envvar="RALPH_PROJECT",
    ),
) -> None:
    """Run acceptance checks (shortcut for 'task validate')."""
    task.validate(project=project)


@app.command("estimate")
def estimate(
    project: Optional[str] = typer.Option(
        None,
        "--project",
        "-p",
        help="Project ID (or set RALPH_PROJECT env var)",
        envvar="RALPH_PROJECT",
    ),
) -> None:
    """Show token estimates (shortcut for 'task estimate')."""
    task.estimate(project=project)


@app.command("init")
def init(
    name: str = typer.Option("Project", "--name", "-n", help="Project name"),
    target_tokens: int = typer.Option(
        60000, "--target-tokens", "-t", help="Target token budget per task"
    ),
    path: Optional[str] = typer.Option(
        None, "--path", help="Path to codebase (default: current directory)"
    ),
) -> None:
    """Initialize project (shortcut for 'project init')."""
    project.init(name=name, target_tokens=target_tokens, path=path)


@app.command("assign")
def assign(
    n: int = typer.Argument(4, help="Number of workers"),
    project: Optional[str] = typer.Option(
        None,
        "--project",
        "-p",
        help="Project ID (or set RALPH_PROJECT env var)",
        envvar="RALPH_PROJECT",
    ),
) -> None:
    """Assign workers (shortcut for 'worker assign')."""
    worker.assign(n, project=project)


@app.command("workers")
def workers(
    project: Optional[str] = typer.Option(
        None,
        "--project",
        "-p",
        help="Project ID (or set RALPH_PROJECT env var)",
        envvar="RALPH_PROJECT",
    ),
) -> None:
    """Show workers (shortcut for 'worker list')."""
    worker.list_workers(project=project)


@app.command("merge")
def merge(
    project: Optional[str] = typer.Option(
        None,
        "--project",
        "-p",
        help="Project ID (or set RALPH_PROJECT env var)",
        envvar="RALPH_PROJECT",
    ),
) -> None:
    """Show merge instructions (shortcut for 'worker merge')."""
    worker.merge(project=project)


@app.command("done-all")
def done_all(
    project: Optional[str] = typer.Option(
        None,
        "--project",
        "-p",
        help="Project ID (or set RALPH_PROJECT env var)",
        envvar="RALPH_PROJECT",
    ),
) -> None:
    """Mark all worker tasks done (shortcut for 'worker done-all')."""
    worker.done_all(project=project)


@app.command("enrich")
def enrich() -> None:
    """Auto-suggest read_first (shortcut for 'context enrich')."""
    context.enrich()


@app.command("sync")
def sync() -> None:
    """Sync codebase index (shortcut for 'context sync')."""
    context.sync()


__all__ = ["app"]
