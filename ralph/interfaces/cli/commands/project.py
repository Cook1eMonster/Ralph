"""Project management CLI commands.

Commands for project initialization and configuration.
"""

import json
from pathlib import Path

import typer

# Domain and application imports
from ralph.application.project_service import create_project
from ralph.domain.shared import Err, Ok
from ralph.domain.task import TaskNode, TaskStatus, Tree
from ralph.infrastructure.storage.repositories import (
    PROJECTS_DIR,
    ProjectRepository,
    TreeRepository,
)
from ralph.interfaces.cli.common import (
    get_project_id,
    print_error,
    print_success,
)

app = typer.Typer(help="Project management commands")


# =============================================================================
# Commands
# =============================================================================


def _make_project_id(name: str) -> str:
    """Generate project ID from name.

    Converts name to lowercase, replaces spaces with hyphens,
    keeps only alphanumeric and hyphens.
    """
    project_id = name.lower()
    project_id = project_id.replace(" ", "-")
    project_id = "".join(c for c in project_id if c.isalnum() or c == "-")
    while "--" in project_id:
        project_id = project_id.replace("--", "-")
    return project_id.strip("-")[:40]


@app.command("init")
def init(
    name: str = typer.Option("Project", "--name", "-n", help="Project name"),
    target_tokens: int = typer.Option(
        60000,
        "--target-tokens",
        "-t",
        help="Target token budget per task",
    ),
    path: str | None = typer.Option(
        None,
        "--path",
        help="Path to codebase (default: current directory)",
    ),
) -> None:
    """Initialize a new project with tree.json.

    Creates the default project structure including:
    - tree.json: Task tree with example structure
    - requirements.md: Project requirements template
    - config.json: Project configuration

    Example:
        ralph project init --name "My Project"
    """
    # Generate project ID from name
    project_id = _make_project_id(name)

    # Use current directory if no path specified
    codebase_path = path or str(Path.cwd())

    # Create project via service
    result = create_project(
        project_id=project_id,
        name=name,
        path=codebase_path,
        target_tokens=target_tokens,
    )

    if isinstance(result, Err):
        print_error(result.error)
        raise typer.Exit(1)

    project, _event = result.value

    # Save project config
    project_repo = ProjectRepository()
    save_result = project_repo.save(project)
    if isinstance(save_result, Err):
        print_error(f"Failed to save project: {save_result.error}")
        raise typer.Exit(1)

    # Create default tree
    default_tree = Tree(
        name=name,
        context="Describe your project here",
        children=[
            TaskNode(
                name="Feature 1",
                context="Context for this feature",
                children=[
                    TaskNode(
                        name="First task description",
                        files=["src/example.py"],
                        acceptance=["pytest passes"],
                        status=TaskStatus.PENDING,
                    )
                ],
            )
        ],
    )

    # Save tree
    tree_repo = TreeRepository()
    tree_result = tree_repo.save(project_id, default_tree)
    if isinstance(tree_result, Err):
        print_error(f"Failed to save tree: {tree_result.error}")
        raise typer.Exit(1)

    # Create requirements.md
    project_dir = PROJECTS_DIR / project_id
    requirements_file = project_dir / "requirements.md"
    requirements_content = """# Requirements

## Scale
- Define your scale targets here

## Priorities
- What matters most?

## Skip
- What to avoid / prune
"""
    requirements_file.write_text(requirements_content, encoding="utf-8")

    print_success(f"Created project: {project_id}")
    typer.echo(f"  Directory: {project_dir}")
    typer.echo("  Files created:")
    typer.echo("    - config.json (project settings)")
    typer.echo("    - tree.json (task tree)")
    typer.echo("    - requirements.md (project requirements)")
    typer.echo("")
    typer.echo("Next steps:")
    typer.echo(f"  ralph -p {project_id} status  # View task tree")
    typer.echo(f"  ralph -p {project_id} next    # Get first task")


@app.command("add")
def add(
    path: str = typer.Argument(..., help="Dot-path to parent (e.g., 'Project.Feature1')"),
    task_json: str = typer.Argument(..., help="Task JSON to add"),
    project: str | None = typer.Option(
        None,
        "--project",
        "-p",
        help="Project ID (or set RALPH_PROJECT env var)",
        envvar="RALPH_PROJECT",
    ),
) -> None:
    """Add a task to the tree at a specific path.

    The path uses dot notation to specify where to add the task.
    The task is provided as a JSON string.

    Example:
        ralph project add "Project.Feature1" '{"name": "New task", "status": "pending"}'
    """
    project_id = get_project_id(project)

    # Parse the task JSON
    try:
        task_data = json.loads(task_json)
    except json.JSONDecodeError as e:
        print_error(f"Invalid JSON: {e}")
        raise typer.Exit(1)

    # Load tree
    tree_repo = TreeRepository()
    result = tree_repo.load(project_id)
    if isinstance(result, Err):
        print_error(result.error)
        raise typer.Exit(1)

    tree = result.value

    # Parse path
    path_parts = path.split(".")
    if not path_parts:
        print_error("Path cannot be empty")
        raise typer.Exit(1)

    # Navigate to parent
    if path_parts[0] != tree.name:
        print_error(f"Path must start with root name '{tree.name}'")
        raise typer.Exit(1)

    # Find parent node
    current = tree
    for i, part in enumerate(path_parts[1:], 1):
        found = False
        for child in current.children:
            if child.name == part:
                current = child
                found = True
                break
        if not found:
            print_error(f"Path not found: {'.'.join(path_parts[:i+1])}")
            raise typer.Exit(1)

    # Create new task node
    try:
        new_task = TaskNode(**task_data)
    except Exception as e:
        print_error(f"Invalid task data: {e}")
        raise typer.Exit(1)

    # Add to parent's children
    current.children.append(new_task)

    # Save tree
    save_result = tree_repo.save(project_id, tree)
    if isinstance(save_result, Err):
        print_error(f"Failed to save: {save_result.error}")
        raise typer.Exit(1)

    print_success(f"Added task: {new_task.name}")


@app.command("prune")
def prune(
    path: str = typer.Argument(..., help="Dot-path to node to remove"),
    project: str | None = typer.Option(
        None,
        "--project",
        "-p",
        help="Project ID (or set RALPH_PROJECT env var)",
        envvar="RALPH_PROJECT",
    ),
) -> None:
    """Remove a task from the tree by path.

    Example:
        ralph project prune "Project.Feature1.OldTask"
    """
    project_id = get_project_id(project)

    # Load tree
    tree_repo = TreeRepository()
    result = tree_repo.load(project_id)
    if isinstance(result, Err):
        print_error(result.error)
        raise typer.Exit(1)

    tree = result.value

    # Parse path
    path_parts = path.split(".")
    if len(path_parts) < 2:
        print_error("Cannot prune root node")
        raise typer.Exit(1)

    if path_parts[0] != tree.name:
        print_error(f"Path must start with root name '{tree.name}'")
        raise typer.Exit(1)

    # Navigate to parent of target
    current = tree
    for i, part in enumerate(path_parts[1:-1], 1):
        found = False
        for child in current.children:
            if child.name == part:
                current = child
                found = True
                break
        if not found:
            print_error(f"Path not found: {'.'.join(path_parts[:i+1])}")
            raise typer.Exit(1)

    # Find and remove target
    target_name = path_parts[-1]
    original_count = len(current.children)
    current.children = [c for c in current.children if c.name != target_name]

    if len(current.children) == original_count:
        print_error(f"Node not found: {target_name}")
        raise typer.Exit(1)

    # Save tree
    save_result = tree_repo.save(project_id, tree)
    if isinstance(save_result, Err):
        print_error(f"Failed to save: {save_result.error}")
        raise typer.Exit(1)

    print_success(f"Pruned: {target_name}")


@app.command("govern")
def govern(
    project: str | None = typer.Option(
        None,
        "--project",
        "-p",
        help="Project ID (or set RALPH_PROJECT env var)",
        envvar="RALPH_PROJECT",
    ),
) -> None:
    """Output governance prompt for tree review.

    Generates a prompt for Claude to review and adjust the task tree:
    - Mark appropriate tasks as done
    - Prune tasks that shouldn't be done
    - Split oversized tasks

    Example:
        ralph project govern | pbcopy  # Copy to clipboard
    """
    from ralph.domain.task import count_by_status

    project_id = get_project_id(project)
    project_dir = PROJECTS_DIR / project_id

    # Load tree
    tree_repo = TreeRepository()
    result = tree_repo.load(project_id)
    if isinstance(result, Err):
        print_error(result.error)
        raise typer.Exit(1)

    tree = result.value

    # Load requirements
    requirements_file = project_dir / "requirements.md"
    requirements = ""
    if requirements_file.exists():
        requirements = requirements_file.read_text(encoding="utf-8")

    # Count tasks
    counts = count_by_status(tree)
    total = sum(counts.values())
    done = counts.get(TaskStatus.DONE, 0)
    pending = counts.get(TaskStatus.PENDING, 0)

    # Generate governance prompt
    prompt = f"""
You are a senior software architect reviewing a task tree.

## Project Requirements
{requirements if requirements else "(No requirements.md found)"}

## Current Status
- Total tasks: {total}
- Done: {done}
- Pending: {pending}

## Task Tree (JSON)
```json
{json.dumps(tree.model_dump(), indent=2)}
```

## Your Job
Review the tree and suggest:

1. **Mark Done**: Which tasks are actually complete based on the codebase?
   - Run `ralph -p {project_id} done` for each

2. **Prune**: Which tasks should NOT be done?
   - Against requirements
   - Out of scope
   - Duplicates
   - Run `ralph project prune -p {project_id} "Path.To.Task"`

3. **Split**: Which tasks are too large (~60k token budget)?
   - Tasks with many files
   - Tasks with broad scope
   - Add subtasks via `ralph project add`

4. **Missing**: What's missing from the tree?
   - Based on requirements
   - Based on codebase analysis

Output specific commands I can run.
"""
    typer.echo(prompt)


@app.command("list")
def list_projects() -> None:
    """List all projects.

    Shows all projects with their paths and progress.

    Example:
        ralph project list
    """
    if not PROJECTS_DIR.exists():
        typer.echo("No projects found.")
        typer.echo("Run: ralph project init --name 'My Project'")
        return

    project_dirs = [d for d in PROJECTS_DIR.iterdir() if d.is_dir()]

    if not project_dirs:
        typer.echo("No projects found.")
        typer.echo("Run: ralph project init --name 'My Project'")
        return

    typer.echo("Projects:")
    typer.echo("-" * 60)

    project_repo = ProjectRepository()
    tree_repo = TreeRepository()

    for project_dir in sorted(project_dirs):
        project_id = project_dir.name

        # Try to load project config
        project_result = project_repo.get(project_id)
        if isinstance(project_result, Err):
            typer.echo(f"  {project_id}: [error loading config]")
            continue

        project = project_result.value

        # Try to load tree for progress info
        progress_str = ""
        tree_result = tree_repo.load(project_id)
        if isinstance(tree_result, Ok):
            from ralph.domain.task import count_by_status

            counts = count_by_status(tree_result.value)
            total = sum(counts.values())
            done = counts.get(TaskStatus.DONE, 0)
            if total > 0:
                pct = round(done / total * 100)
                progress_str = f" ({done}/{total} = {pct}%)"

        typer.echo(f"  [{project_id}] {project.name}{progress_str}")
        typer.echo(f"    Path: {project.path}")
        typer.echo()
