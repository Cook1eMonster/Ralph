"""Parallel worker CLI commands.

Commands for managing parallel task execution across multiple workers,
typically using git branches for isolation.
"""

from pathlib import Path
from typing import Optional

import typer

from ralph.domain.shared import Err
from ralph.domain.task import find_n_pending
from ralph.domain.task.models import TaskStatus, Tree
from ralph.domain.task.traversal import update_at_path
from ralph.domain.worker.models import Worker, WorkerPool
from ralph.infrastructure.storage.repositories import (
    PROJECTS_DIR,
    TreeRepository,
    WorkerRepository,
)
from ralph.interfaces.cli.common import get_project_id, print_error, print_success

app = typer.Typer(help="Parallel worker commands")


# =============================================================================
# Branch Name Helper
# =============================================================================


def task_to_branch_name(task_name: str) -> str:
    """Convert task name to git branch name.

    Examples:
        "Add User Login" -> "feat/add-user-login"
        "Fix bug #123" -> "feat/fix-bug-123"
    """
    # Lowercase, replace spaces with hyphens, remove special chars
    branch = task_name.lower()
    branch = branch.replace(" ", "-")
    # Keep only alphanumeric and hyphens
    branch = "".join(c for c in branch if c.isalnum() or c == "-")
    # Remove multiple hyphens
    while "--" in branch:
        branch = branch.replace("--", "-")
    # Trim to reasonable length
    branch = branch[:40].strip("-")
    return f"feat/{branch}"


# =============================================================================
# Output Formatting Helpers
# =============================================================================


def print_separator(char: str = "=", width: int = 60) -> None:
    """Print a separator line."""
    typer.echo(char * width)


def format_worker_prompt(
    worker: Worker,
    task_name: str,
    context: str,
    read_first: list[str],
    spec: str | None,
    files: list[str],
    acceptance: list[str],
) -> str:
    """Format a worker assignment prompt."""
    lines = []

    lines.append(f"""
You are Worker {worker.id}. Your job is to complete ONE task on a dedicated branch.

## Setup
```bash
git checkout main
git pull origin main
git checkout -b {worker.branch}
```

## Your Task
{task_name}""")

    if read_first:
        lines.append("\n## Read First (MANDATORY)")
        lines.append("Before coding, read these files:")
        for f in read_first:
            lines.append(f"- {f}")

    if spec:
        lines.append(f"\n## Spec\n{spec}")

    lines.append(f"""
## Files to modify
{', '.join(files) if files else 'Determine based on task'}

## Acceptance criteria
{chr(10).join(f'- {a}' for a in acceptance) if acceptance else '- Code works and passes type checks'}

## Context
{context}

## Before Marking Done (REQUIRED)
1. Run acceptance checks: {', '.join(acceptance) if acceptance else 'tests pass'}
2. Run code-simplifier:
   "Use code-simplifier to review and simplify the code I just wrote"
3. Commit and push:
```bash
git add -A
git commit -m "{task_name}"
git push -u origin {worker.branch}
```

Then say: "Worker {worker.id} complete. Pushed to {worker.branch}"
""")

    return "".join(lines)


# =============================================================================
# Context Building
# =============================================================================


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


# =============================================================================
# Commands
# =============================================================================


@app.command("assign")
def assign(
    n: int = typer.Argument(4, help="Number of workers to assign"),
    project: str | None = typer.Option(
        None,
        "--project",
        "-p",
        help="Project ID (or set RALPH_PROJECT env var)",
        envvar="RALPH_PROJECT",
    ),
) -> None:
    """Assign N tasks to parallel workers.

    Finds up to N pending tasks and generates worker prompts that can be
    copied into separate Claude instances for parallel execution.

    Each worker gets:
    - A unique branch name
    - Task details and context
    - Setup and commit instructions

    Example:
        ralph worker assign 4
        ralph worker assign 2 -p my-project
    """
    # Get project ID
    project_id = get_project_id(project)

    # Load tree via TreeRepository
    tree_repo = TreeRepository()
    tree_result = tree_repo.load(project_id)

    if isinstance(tree_result, Err):
        print_error(tree_result.error)
        raise typer.Exit(1)

    tree = tree_result.value

    # Find N pending tasks
    tasks = find_n_pending(tree, n)

    if not tasks:
        typer.echo("No pending tasks to assign.")
        return

    # Get project directory for context
    project_dir = PROJECTS_DIR / project_id

    # Create worker pool
    workers: list[Worker] = []

    print_separator("=", 70)
    typer.echo(f"ORCHESTRATOR: Assigning {len(tasks)} tasks to workers")
    print_separator("=", 70)
    typer.echo()

    for i, task_with_path in enumerate(tasks, start=1):
        task = task_with_path.task
        path = task_with_path.path

        # Generate branch name
        branch = task_to_branch_name(task.name)

        # Build context from ancestors
        context = build_context(tree, path, project_dir)

        # Create worker entry
        worker = Worker(
            id=i,
            branch=branch,
            task=task.name,
            path=".".join(path),
            status="assigned",
        )
        workers.append(worker)

        # Print worker prompt header
        print_separator("=", 70)
        typer.echo(f"WORKER {i} - Copy everything below this line to Terminal {i + 1}:")
        print_separator("=", 70)

        # Format and print worker prompt
        prompt = format_worker_prompt(
            worker=worker,
            task_name=task.name,
            context=context,
            read_first=task.read_first,
            spec=task.spec,
            files=task.files,
            acceptance=task.acceptance,
        )
        typer.echo(prompt)
        typer.echo()

    # Save workers via WorkerRepository
    worker_repo = WorkerRepository()
    pool = WorkerPool(workers=workers)
    save_result = worker_repo.save(project_id, pool)

    if isinstance(save_result, Err):
        print_error(f"Failed to save workers: {save_result.error}")
        raise typer.Exit(1)

    # Print orchestrator notes at end
    print_separator("=", 70)
    typer.echo("ORCHESTRATOR NOTES:")
    print_separator("=", 70)
    typer.echo(f"""
Workers assigned: {len(tasks)}
Branches: {', '.join(w.branch for w in workers)}

When all workers report complete, run:
  ralph worker merge

To check worker status:
  ralph worker list
""")


@app.command("list")
def list_workers(
    project: str | None = typer.Option(
        None,
        "--project",
        "-p",
        help="Project ID (or set RALPH_PROJECT env var)",
        envvar="RALPH_PROJECT",
    ),
) -> None:
    """Show current worker assignments.

    Displays all workers with their assigned tasks, branches, and status.

    Example:
        ralph worker list
        ralph worker list -p my-project
    """
    project_id = get_project_id(project)
    repo = WorkerRepository()
    result = repo.load(project_id)

    if isinstance(result, Err):
        typer.echo(f"Error: {result.error}")
        raise typer.Exit(1)

    pool = result.value

    if not pool.workers:
        typer.echo("No workers currently assigned.")
        typer.echo("Run: ralph worker assign <N>")
        return

    print_separator()
    typer.echo("CURRENT WORKER ASSIGNMENTS")
    print_separator()

    for worker in pool.workers:
        typer.echo(f"  Worker {worker.id}: [{worker.status:10}] {worker.branch}")
        # Truncate task name to 50 characters to match original behavior
        task_display = worker.task[:50] if len(worker.task) > 50 else worker.task
        typer.echo(f"           Task: {task_display}")
        typer.echo()


@app.command("merge")
def merge(
    project: str | None = typer.Option(
        None,
        "--project",
        "-p",
        help="Project ID (or set RALPH_PROJECT env var)",
        envvar="RALPH_PROJECT",
    ),
) -> None:
    """Generate merge instructions.

    Outputs git commands to merge all worker branches back to main
    after workers have completed their tasks.

    Example:
        ralph worker merge
        ralph worker merge -p my-project
    """
    # Get project ID
    project_id = get_project_id(project)

    # Load workers
    repo = WorkerRepository()
    result = repo.load(project_id)

    if isinstance(result, Err):
        print_error(result.error)
        raise typer.Exit(1)

    pool = result.value

    if not pool.workers:
        typer.echo("No workers currently assigned.")
        return

    print_separator()
    typer.echo("MERGE INSTRUCTIONS")
    print_separator()
    typer.echo()
    typer.echo("Run these commands to merge all worker branches:")
    typer.echo()
    typer.echo("```bash")
    typer.echo("git checkout main")
    typer.echo("git pull origin main")

    for worker in pool.workers:
        typer.echo(f"git merge {worker.branch}")

    typer.echo("git push origin main")
    typer.echo("```")
    typer.echo()
    typer.echo("After merging, mark all tasks done:")
    typer.echo("  ralph worker done-all")


@app.command("done-all")
def done_all(
    project: str | None = typer.Option(
        None,
        "--project",
        "-p",
        help="Project ID (or set RALPH_PROJECT env var)",
        envvar="RALPH_PROJECT",
    ),
) -> None:
    """Mark all assigned tasks done.

    After merging all worker branches, marks each assigned task as
    complete in the tree and clears the worker assignments.

    Example:
        ralph worker done-all
        ralph worker done-all -p my-project
    """
    # Get project ID
    project_id = get_project_id(project)

    # Load tree and workers
    tree_repo = TreeRepository()
    worker_repo = WorkerRepository()

    tree_result = tree_repo.load(project_id)
    if isinstance(tree_result, Err):
        print_error(tree_result.error)
        raise typer.Exit(1)

    workers_result = worker_repo.load(project_id)
    if isinstance(workers_result, Err):
        print_error(workers_result.error)
        raise typer.Exit(1)

    tree = tree_result.value
    pool = workers_result.value

    if not pool.workers:
        typer.echo("No workers to complete.")
        return

    # Mark each worker's task as done
    count = 0
    for worker in pool.workers:
        # Worker path is stored as dot-separated string
        path = worker.path.split(".")
        tree = update_at_path(
            tree,
            path,
            lambda t: t.model_copy(update={"status": TaskStatus.DONE}),
        )
        count += 1
        # Truncate task name to 50 characters to match original behavior
        task_display = worker.task[:50] if len(worker.task) > 50 else worker.task
        typer.echo(f"  Marked done: {task_display}")

    # Save updated tree
    save_result = tree_repo.save(project_id, tree)
    if isinstance(save_result, Err):
        print_error(save_result.error)
        raise typer.Exit(1)

    # Clear workers (save empty pool)
    empty_pool = WorkerPool(workers=[])
    clear_result = worker_repo.save(project_id, empty_pool)
    if isinstance(clear_result, Err):
        print_error(clear_result.error)
        raise typer.Exit(1)

    print_success(f"\nCompleted {count} tasks. Workers cleared.")


@app.command("assign-one")
def assign_one(
    worker_id: Optional[int] = typer.Option(
        None,
        "--id",
        "-i",
        help="Worker ID (auto-assigned if not provided)",
    ),
) -> None:
    """Assign ONE task to a worker.

    Enables rolling pipeline workflow - assign new tasks as workers
    complete without waiting for all to finish.

    Example:
        ralph worker assign-one          # Auto-assigns next ID
        ralph worker assign-one --id 2   # Assigns as Worker 2
    """
    typer.echo("Not implemented yet: worker assign-one")
    typer.echo("")
    typer.echo("This command will:")
    typer.echo(f"  1. Determine worker ID: {worker_id or 'auto-increment'}")
    typer.echo("  2. Find next pending task")
    typer.echo("  3. Generate worker prompt")
    typer.echo("  4. Add to workers.json")
    typer.echo("  5. Output prompt to copy")


@app.command("done-one")
def done_one(
    worker_id: int = typer.Argument(..., help="Worker ID to complete"),
    project: str | None = typer.Option(
        None,
        "--project",
        "-p",
        help="Project ID (or set RALPH_PROJECT env var)",
        envvar="RALPH_PROJECT",
    ),
) -> None:
    """Complete ONE worker's task.

    Marks the specified worker's task as done and removes them from
    the active workers list. Outputs merge instructions for that branch.

    Example:
        ralph worker done-one 2
        ralph worker done-one 2 -p my-project
    """
    # Get project ID
    project_id = get_project_id(project)

    # Load tree and workers
    tree_repo = TreeRepository()
    worker_repo = WorkerRepository()

    tree_result = tree_repo.load(project_id)
    if isinstance(tree_result, Err):
        print_error(tree_result.error)
        raise typer.Exit(1)

    workers_result = worker_repo.load(project_id)
    if isinstance(workers_result, Err):
        print_error(workers_result.error)
        raise typer.Exit(1)

    tree = tree_result.value
    pool = workers_result.value

    if not pool.workers:
        typer.echo("No workers currently assigned.")
        return

    # Find the worker by ID
    worker = pool.get_by_id(worker_id)
    if worker is None:
        typer.echo(f"Worker {worker_id} not found.")
        typer.echo(f"Active workers: {[w.id for w in pool.workers]}")
        return

    # Mark task as done in tree
    path = worker.path.split(".")
    tree = update_at_path(
        tree,
        path,
        lambda t: t.model_copy(update={"status": TaskStatus.DONE}),
    )

    # Save updated tree
    save_result = tree_repo.save(project_id, tree)
    if isinstance(save_result, Err):
        print_error(save_result.error)
        raise typer.Exit(1)

    # Truncate task name for display
    task_display = worker.task[:50] if len(worker.task) > 50 else worker.task
    print_success(f"Marked done: {task_display}")

    # Remove worker from pool
    updated_workers = [w for w in pool.workers if w.id != worker_id]
    updated_pool = WorkerPool(workers=updated_workers)

    # Save updated workers
    pool_result = worker_repo.save(project_id, updated_pool)
    if isinstance(pool_result, Err):
        print_error(pool_result.error)
        raise typer.Exit(1)

    # Print merge instructions
    typer.echo(f"""
Merge this branch:
```bash
git checkout main
git pull origin main
git merge {worker.branch}
git push origin main
git branch -d {worker.branch}
```

Worker {worker_id} cleared. Remaining workers: {len(updated_workers)}
""")

    if updated_workers:
        typer.echo(f"Active workers: {[w.id for w in updated_workers]}")
    else:
        typer.echo("All workers complete!")
