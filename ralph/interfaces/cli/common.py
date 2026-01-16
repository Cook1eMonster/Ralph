"""Shared utilities for Ralph CLI commands.

This module provides common utilities used across CLI commands:
- Project detection and environment handling
- Formatted output helpers (error, success, info)
- Task formatting for display
- Token estimation display

Follows the output patterns established in ralph_tree.py:
- Separators using '=' characters
- Token estimation with utilization percentage
- Task details with spec, read_first, files, acceptance
"""

import os
from pathlib import Path
from typing import Annotated, Any, Optional

import typer

# Token estimation constants (from domain)
TARGET_TOKENS = 60000

# Reusable project option for CLI commands
# Usage: def my_command(project: str = project_option) -> None:
project_option: Annotated[Optional[str], typer.Option(
    "--project", "-p",
    help="Project ID (or set RALPH_PROJECT env var)",
    envvar="RALPH_PROJECT",
)] = None


def get_project_id(explicit_project: str | None = None) -> str:
    """Get the project ID, raising an error if not found.

    Resolution order:
    1. Explicit project parameter (from -p/--project CLI option)
    2. RALPH_PROJECT environment variable
    3. Current working directory name (if in a projects folder)
    4. Looking for a tree.json in the current directory

    Args:
        explicit_project: Project ID explicitly provided via CLI option.

    Returns:
        Project ID string.

    Raises:
        typer.Exit: If no project can be determined.
    """
    # 1. Check explicit parameter (from CLI -p option)
    if explicit_project:
        return explicit_project

    # 2. Check environment variable
    env_project = os.environ.get("RALPH_PROJECT")
    if env_project:
        return env_project

    # 3. Check if we're in a project directory (has tree.json)
    cwd = Path.cwd()
    if (cwd / "tree.json").exists():
        return cwd.name

    # 4. Check if we're in a projects subdirectory
    if cwd.parent.name == "projects":
        return cwd.name

    # No project found - show helpful error
    print_error("No project specified.")
    typer.echo("")
    typer.echo("Specify a project using one of:")
    typer.echo("  1. Use -p/--project option: ralph status -p my-project")
    typer.echo("  2. Set RALPH_PROJECT env var: export RALPH_PROJECT=my-project")
    typer.echo("  3. Run from project directory: cd projects/my-project")
    typer.echo("")
    typer.echo("List available projects with: ralph project list")
    raise typer.Exit(1)


def require_project(project: str | None) -> str:
    """Get project ID, requiring it to be specified.

    This is a convenience wrapper around get_project_id() for use
    in commands that require a project.

    Args:
        project: Project ID from CLI option (may be None).

    Returns:
        Project ID string.

    Raises:
        typer.Exit: If no project can be determined.
    """
    return get_project_id(project)


def print_error(msg: str) -> None:
    """Print a formatted error message.

    Args:
        msg: Error message to display
    """
    typer.echo(typer.style(f"Error: {msg}", fg=typer.colors.RED), err=True)


def print_success(msg: str) -> None:
    """Print a formatted success message.

    Args:
        msg: Success message to display
    """
    typer.echo(typer.style(msg, fg=typer.colors.GREEN))


def print_info(msg: str) -> None:
    """Print a formatted info message.

    Args:
        msg: Info message to display
    """
    typer.echo(typer.style(msg, fg=typer.colors.BLUE))


def print_warning(msg: str) -> None:
    """Print a formatted warning message.

    Args:
        msg: Warning message to display
    """
    typer.echo(typer.style(f"Warning: {msg}", fg=typer.colors.YELLOW), err=True)


def print_separator(char: str = "=", width: int = 60) -> None:
    """Print a separator line.

    Args:
        char: Character to use for separator
        width: Width of the separator line
    """
    typer.echo(char * width)


def print_header(title: str, width: int = 60) -> None:
    """Print a formatted header with separators.

    Args:
        title: Header title text
        width: Width of the separator lines
    """
    print_separator("=", width)
    typer.echo(title)
    print_separator("=", width)


def format_estimate(
    total: int,
    utilization: float,
    fits: bool,
    complexity: str,
) -> str:
    """Format token estimate for display.

    Args:
        total: Total estimated tokens
        utilization: Percentage of target used
        fits: Whether the task fits within target
        complexity: Complexity level (low/medium/high)

    Returns:
        Formatted estimate string
    """
    status = "OK" if fits else "OVERSIZED"
    return (
        f"**Estimate:** ~{total:,} tokens ({utilization}% of {TARGET_TOKENS:,}) [{status}]\n"
        f"**Complexity:** {complexity}"
    )


def print_task(
    task: dict[str, Any],
    context: str,
    show_estimate: bool = True,
) -> None:
    """Format and print a task for display.

    Follows the established format from ralph_tree.py:
    - Task header with separators
    - Read First files (mandatory pre-reads)
    - Spec (locked intent)
    - Files to modify
    - Acceptance criteria
    - Token estimate
    - Context
    - Before Marking Done requirements

    Args:
        task: Task dictionary with name, spec, read_first, files, acceptance
        context: Context string to display
        show_estimate: Whether to show token estimation
    """
    print_header("TASK")
    typer.echo(f"\n## Task: {task.get('name', 'unnamed')}\n")

    # Read First - mandatory files to read before starting
    if task.get("read_first"):
        typer.echo("## Read First (MANDATORY)")
        typer.echo("Before coding, read these files to understand existing patterns:\n")
        for f in task["read_first"]:
            typer.echo(f"- {f}")
        typer.echo()

    # Spec - locked intent for the task
    if task.get("spec"):
        typer.echo("## Spec")
        typer.echo(task["spec"])
        typer.echo()

    if task.get("files"):
        typer.echo(f"**Files to modify:** {', '.join(task['files'])}")

    if task.get("acceptance"):
        typer.echo(f"**Acceptance criteria:** {', '.join(task['acceptance'])}")

    if show_estimate:
        # Calculate estimate using simple heuristics
        est = _estimate_tokens(task, context)
        complexity = _estimate_complexity(task)
        estimate_str = format_estimate(
            est["total"],
            est["utilization"],
            est["fits"],
            complexity,
        )
        typer.echo(f"\n{estimate_str}")

    if context:
        typer.echo(f"\n## Context\n{context}")

    # Code Simplifier requirement
    typer.echo(
        """
## Before Marking Done (REQUIRED)
1. Run acceptance checks (validate)
2. Run code-simplifier on modified files:
   "Use code-simplifier to review and simplify the code I just wrote"
3. Only then mark the task as done
"""
    )

    print_separator()


def _estimate_tokens(task: dict[str, Any], context: str) -> dict[str, Any]:
    """Estimate tokens for a task (internal helper).

    Args:
        task: Task dictionary
        context: Context string

    Returns:
        Dictionary with token breakdown and totals
    """
    # Token estimation constants
    tokens_per_char = 0.25
    base_overhead = 15000
    tokens_per_file = 2500
    tokens_per_tool_call = 500

    estimates: dict[str, Any] = {
        "base_overhead": base_overhead,
        "context": int(len(context) * tokens_per_char),
        "task_description": int(len(task.get("name", "")) * tokens_per_char),
        "file_reads": len(task.get("files", [])) * tokens_per_file,
        "tool_calls": 15 * tokens_per_tool_call,  # Estimate 15 tool calls
        "response_buffer": 5000,  # Buffer for agent responses
    }
    estimates["total"] = sum(estimates.values())
    estimates["target"] = TARGET_TOKENS
    estimates["fits"] = estimates["total"] <= TARGET_TOKENS
    estimates["utilization"] = round(estimates["total"] / TARGET_TOKENS * 100, 1)
    return estimates


def _estimate_complexity(task: dict[str, Any]) -> str:
    """Estimate task complexity (internal helper).

    Args:
        task: Task dictionary

    Returns:
        Complexity level: "low", "medium", or "high"
    """
    name = task.get("name", "").lower()
    files = task.get("files", [])

    # Complexity signals
    complex_words = [
        "refactor",
        "migrate",
        "redesign",
        "overhaul",
        "complete",
        "full",
        "entire",
        "all",
    ]
    medium_words = ["integrate", "implement", "add", "create", "build"]
    simple_words = ["fix", "update", "rename", "remove", "delete", "change"]

    if any(w in name for w in complex_words) or len(files) > 3:
        return "high"
    elif any(w in name for w in medium_words) or len(files) > 1:
        return "medium"
    elif any(w in name for w in simple_words) or len(files) <= 1:
        return "low"
    return "medium"


__all__ = [
    "get_project_id",
    "project_option",
    "require_project",
    "print_error",
    "print_success",
    "print_info",
    "print_warning",
    "print_separator",
    "print_header",
    "format_estimate",
    "print_task",
    "TARGET_TOKENS",
]
