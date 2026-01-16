"""Task management CLI commands.

Commands for the task lifecycle: viewing next task, marking done,
validating acceptance criteria, and showing progress.
"""

import subprocess
from pathlib import Path

import typer

# Domain and application imports
from ralph.domain.shared import Err
from ralph.domain.task import TaskStatus, TaskWithPath, Tree, find_next_pending
from ralph.domain.task.estimation import (
    TokenCount,
    estimate_complexity,
    estimate_tokens,
)
from ralph.domain.task.traversal import get_all_pending
from ralph.infrastructure.storage import TreeRepository
from ralph.infrastructure.storage.repositories import PROJECTS_DIR
from ralph.interfaces.cli.common import (
    get_project_id,
    print_error,
    print_info,
    print_separator,
    print_success,
    project_option,
)

app = typer.Typer(help="Task management commands")


# =============================================================================
# Output Formatting Helpers
# =============================================================================


def format_task_output(
    task_with_path: TaskWithPath,
    context: str,
    estimate: TokenCount | None = None,
) -> str:
    """Format a task for display, matching ralph_tree.py output format."""
    task = task_with_path.task
    lines = []

    lines.append("=" * 60)
    lines.append("TASK")
    lines.append("=" * 60)
    lines.append(f"\n## Task: {task.name}\n")

    # Read First - mandatory files to read before starting
    if task.read_first:
        lines.append("## Read First (MANDATORY)")
        lines.append("Before coding, read these files to understand existing patterns:\n")
        for f in task.read_first:
            lines.append(f"- {f}")
        lines.append("")

    # Spec - locked intent for the task
    if task.spec:
        lines.append("## Spec")
        lines.append(task.spec)
        lines.append("")

    if task.files:
        lines.append(f"**Files to modify:** {', '.join(task.files)}")

    if task.acceptance:
        lines.append(f"**Acceptance criteria:** {', '.join(task.acceptance)}")

    if estimate:
        status = "OK" if estimate.fits else "OVERSIZED"
        lines.append(
            f"\n**Estimate:** ~{estimate.total:,} tokens "
            f"({estimate.utilization}% of {estimate.target:,}) [{status}]"
        )
        lines.append(f"**Complexity:** {estimate.complexity}")

    if context:
        lines.append(f"\n## Context\n{context}")

    # Code Simplifier requirement
    lines.append("""
## Before Marking Done (REQUIRED)
1. Run acceptance checks (validate)
2. Run code-simplifier on modified files:
   "Use code-simplifier to review and simplify the code I just wrote"
3. Only then mark the task as done
""")

    lines.append("=" * 60)
    return "\n".join(lines)


def print_tree_recursive(
    children: list,
    indent: int = 0,
) -> None:
    """Recursively print tree structure."""
    prefix = "  " * indent
    for node in children:
        status_str = ""
        if node.is_leaf():
            if node.status == TaskStatus.DONE:
                status_str = " [x]"
            elif node.status == TaskStatus.PENDING:
                status_str = " [ ]"
            else:
                status_str = f" [{node.status.value}]"

        typer.echo(f"{prefix}- {node.name}{status_str}")
        if node.children:
            print_tree_recursive(node.children, indent + 1)


# =============================================================================
# Stub Data Loaders (to be replaced with repository layer)
# =============================================================================


def _load_tree() -> Tree | None:
    """Load tree from storage. Returns None if not available.

    NOTE: This is a temporary stub. In the full implementation,
    this should use ralph.infrastructure.storage.repositories.
    """
    typer.echo("Not implemented yet: tree loading from repository")
    return None


def _save_tree(tree: Tree) -> bool:
    """Save tree to storage. Returns True on success.

    NOTE: This is a temporary stub. In the full implementation,
    this should use ralph.infrastructure.storage.repositories.
    """
    typer.echo("Not implemented yet: tree saving to repository")
    return False


def _load_requirements(project_dir: Path) -> str:
    """Load project requirements from requirements.md.

    Args:
        project_dir: Path to the project directory.

    Returns:
        Contents of requirements.md if it exists, empty string otherwise.
    """
    requirements_file = project_dir / "requirements.md"
    if not requirements_file.exists():
        return ""
    try:
        return requirements_file.read_text(encoding="utf-8")
    except OSError:
        return ""


def build_context(tree: Tree, path: list[str], project_dir: Path | None = None) -> str:
    """Build context string from root to task, including requirements.

    Walks from the tree root to the specified path, accumulating context
    strings from each ancestor node. Optionally includes project requirements
    if a project directory is provided.

    Args:
        tree: The task tree to traverse.
        path: List of node names from root to target task.
        project_dir: Optional path to project directory for loading requirements.

    Returns:
        Concatenated context string from all ancestors, separated by double newlines.
    """
    context_parts: list[str] = []

    # Load and include project requirements if project_dir provided
    if project_dir:
        requirements = _load_requirements(project_dir)
        if requirements:
            context_parts.append(f"# Project Requirements\n{requirements}")

    # Walk path and collect context from each ancestor
    if not path:
        return "\n\n".join(context_parts)

    # First element in path should match tree name (root)
    for i, name in enumerate(path):
        if i == 0:
            # Root node - check tree's context
            if name == tree.name and tree.context:
                context_parts.append(f"# {name}\n{tree.context}")
            continue

        # Find the node at this level
        # We need to traverse from root to find the node
        current_children = tree.children
        for j in range(1, i):
            # Navigate to the parent of current node
            for child in current_children:
                if child.name == path[j]:
                    current_children = child.children
                    break

        # Now find the node at path[i] in current_children
        for child in current_children:
            if child.name == name:
                if child.context:
                    context_parts.append(f"# {name}\n{child.context}")
                break

    return "\n\n".join(context_parts)


def _build_context(tree: Tree, path: list[str]) -> str:
    """Build context string from root to task (wrapper for compatibility).

    NOTE: This is a compatibility wrapper. Use build_context() directly
    when project_dir is available for requirements loading.
    """
    return build_context(tree, path)


# =============================================================================
# Commands
# =============================================================================


@app.command("next")
def next_task(
    project: str | None = typer.Option(
        None,
        "--project",
        "-p",
        help="Project ID (or set RALPH_PROJECT env var)",
        envvar="RALPH_PROJECT",
    ),
    ai: bool = typer.Option(False, "--ai", help="Use AI-enriched context"),
) -> None:
    """Show next task to execute.

    Finds the first pending leaf task in depth-first order and displays
    it with context, files to read, and token estimates.

    Use --ai flag to include AI-suggested context from the codebase index.
    """
    # Get project ID
    project_id = get_project_id(project)

    # Load tree via TreeRepository
    repo = TreeRepository()
    result = repo.load(project_id)

    if isinstance(result, Err):
        print_error(result.error)
        raise typer.Exit(1)

    tree = result.value

    # Find next pending task
    task_with_path = find_next_pending(tree)

    if not task_with_path:
        print_success("All tasks complete!")
        return

    # Get project directory for loading requirements
    project_dir = PROJECTS_DIR / project_id

    # Build context from ancestors
    context = build_context(tree, task_with_path.path, project_dir)

    # Estimate tokens
    token_estimate = estimate_tokens(task_with_path.task, context)

    # Handle --ai flag
    if ai:
        print_info("Note: AI context integration is not yet implemented.")
        print_info("Run without --ai flag or use ralph_context.py directly.")
        typer.echo("")

    # Format and display task
    output = format_task_output(task_with_path, context, token_estimate)
    typer.echo(output)


@app.command("done")
def done(
    project: str | None = typer.Option(
        None,
        "--project",
        "-p",
        help="Project ID (or set RALPH_PROJECT env var)",
        envvar="RALPH_PROJECT",
    ),
) -> None:
    """Mark current task as done.

    Finds the current in-progress or next pending task and marks it
    as completed. Use 'validate' first to verify acceptance criteria.
    """
    from ralph.domain.task.traversal import find_next_pending, update_at_path
    from ralph.infrastructure.storage.repositories import TreeRepository
    from ralph.interfaces.cli.common import get_project_id, print_error, print_success

    # Get project ID
    project_id = get_project_id(project)

    # Load tree
    repo = TreeRepository()
    result = repo.load(project_id)
    if isinstance(result, Err):
        print_error(result.error)
        raise typer.Exit(1)

    tree = result.value

    # Find next pending task
    task_with_path = find_next_pending(tree)
    if not task_with_path:
        typer.echo("No pending tasks.")
        return

    # Mark task as done
    new_tree = update_at_path(
        tree,
        task_with_path.path,
        lambda t: t.model_copy(update={"status": TaskStatus.DONE}),
    )

    # Save tree
    save_result = repo.save(project_id, new_tree)
    if isinstance(save_result, Err):
        print_error(save_result.error)
        raise typer.Exit(1)

    print_success(f"Marked done: {task_with_path.task.name}")


@app.command("validate")
def validate(
    project: str | None = typer.Option(
        None,
        "--project",
        "-p",
        help="Project ID (or set RALPH_PROJECT env var)",
        envvar="RALPH_PROJECT",
    ),
) -> None:
    """Run acceptance criteria for current task.

    Executes each command in the task's 'acceptance' field and reports
    pass/fail status. All checks must pass before marking the task done.
    """
    # Get project ID
    project_id = get_project_id(project)

    # Load tree
    repo = TreeRepository()
    result = repo.load(project_id)
    if isinstance(result, Err):
        print_error(result.error)
        raise typer.Exit(1)

    tree = result.value

    # Find next pending task
    task_with_path = find_next_pending(tree)
    if not task_with_path:
        typer.echo("No pending tasks to validate.")
        return

    task = task_with_path.task
    acceptance = task.acceptance

    # Check if there are acceptance criteria
    if not acceptance:
        typer.echo(f"Task: {task.name}")
        typer.echo("No acceptance criteria defined. Add 'acceptance' field to task.")
        typer.echo("")
        typer.echo('Example: "acceptance": ["pytest", "pyright", "ruff check"]')
        return

    # Print header
    print_separator()
    typer.echo(f"VALIDATING: {task.name[:50]}")
    print_separator()

    # Run each acceptance command
    all_passed = True
    results: list[tuple[str, bool]] = []

    for cmd in acceptance:
        typer.echo(f"\n$ {cmd}")
        run_result = subprocess.run(cmd, shell=True)
        if run_result.returncode != 0:
            typer.echo(f"  X FAILED (exit code {run_result.returncode})")
            results.append((cmd, False))
            all_passed = False
        else:
            typer.echo("  [check] PASSED")
            results.append((cmd, True))

    # Print summary
    typer.echo("")
    print_separator()
    if all_passed:
        print_success("[check] ALL CHECKS PASSED")
        typer.echo("")
        typer.echo("Now run code-simplifier before marking done:")
        typer.echo('  "Use code-simplifier to review and simplify the code I just wrote"')
        typer.echo("")
        typer.echo("Then mark done:")
        typer.echo("  ralph task done")
    else:
        print_error("X SOME CHECKS FAILED")
        typer.echo("")
        typer.echo("Fix the issues and run validate again:")
        typer.echo("  ralph task validate")
        typer.echo("")
        typer.echo("Failed checks:")
        for cmd, passed in results:
            if not passed:
                typer.echo(f"  - {cmd}")
    print_separator()


@app.command("status")
def status(
    project: str | None = typer.Option(
        None,
        "--project",
        "-p",
        help="Project ID (or set RALPH_PROJECT env var)",
        envvar="RALPH_PROJECT",
    ),
) -> None:
    """Show tree progress.

    Displays the task tree structure with completion status for each
    leaf task and overall progress statistics.
    """
    from ralph.domain.task.traversal import count_by_status
    from ralph.infrastructure.storage.repositories import TreeRepository
    from ralph.interfaces.cli.common import get_project_id

    project_id = get_project_id(project)
    repo = TreeRepository()
    result = repo.load(project_id)

    if isinstance(result, Err):
        typer.echo(f"Error: {result.error}")
        raise typer.Exit(1)

    tree = result.value
    counts = count_by_status(tree)

    # Calculate progress
    done = counts[TaskStatus.DONE]
    total = sum(counts.values())

    typer.echo(f"Progress: {done}/{total} tasks complete\n")
    print_tree_recursive(tree.children)


@app.command("estimate")
def estimate(
    project: str | None = typer.Option(
        None,
        "--project",
        "-p",
        help="Project ID (or set RALPH_PROJECT env var)",
        envvar="RALPH_PROJECT",
    ),
) -> None:
    """Show token estimates for all pending tasks.

    Displays estimated token usage for each pending leaf task,
    helping identify tasks that may need to be split.

    Output format:
        Status  Util% | Cmplx  | Task
        ----------------------------------------------------------------------
        [OK  ]  45.2% | medium | Implement user authentication
        [OVER] 112.5% | high   | Refactor entire database layer
    """
    # Get project ID
    project_id = get_project_id(project)

    # Load tree via repository
    repo = TreeRepository()
    result = repo.load(project_id)

    if isinstance(result, Err):
        print_error(result.error)
        raise typer.Exit(1)

    tree = result.value

    # Get all pending leaf tasks
    pending_tasks = get_all_pending(tree)

    if not pending_tasks:
        typer.echo("No pending tasks.")
        return

    # Print table header
    typer.echo(f"{'Status':<6} {'Util':>6} | {'Cmplx':6} | Task")
    typer.echo("-" * 70)

    # Process each pending task
    for task_with_path in pending_tasks:
        task = task_with_path.task

        # Build context for estimation
        context = build_context(tree, task_with_path.path)

        # Call estimate_tokens from domain
        token_estimate = estimate_tokens(task, context)

        # Call estimate_complexity from domain
        complexity = estimate_complexity(task)

        # Determine status
        status_str = "OK" if token_estimate.fits else "OVER"

        # Truncate long task names to fit in table (max 50 chars)
        task_name = task.name[:50] if len(task.name) > 50 else task.name

        # Print row
        typer.echo(
            f"[{status_str:4}] {token_estimate.utilization:5.1f}% | {complexity:6} | {task_name}"
        )
