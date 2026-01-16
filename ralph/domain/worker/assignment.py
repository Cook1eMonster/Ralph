"""Worker assignment functions.

Pure functions for assigning tasks to workers and managing worker creation.
All functions are side-effect free and return new objects.
"""

import re

from ralph.domain.worker.models import Worker, WorkerPool


def task_to_branch_name(task_name: str) -> str:
    """Convert a task name to a valid git branch name.

    Transforms the task name by:
    - Converting to lowercase
    - Replacing spaces and special characters with hyphens
    - Removing consecutive hyphens
    - Stripping leading/trailing hyphens

    Args:
        task_name: Human-readable task name

    Returns:
        A valid git branch name

    Examples:
        >>> task_to_branch_name("Add User Authentication")
        'add-user-authentication'
        >>> task_to_branch_name("Fix bug #123")
        'fix-bug-123'
    """
    # Convert to lowercase
    branch = task_name.lower()

    # Replace non-alphanumeric characters with hyphens
    branch = re.sub(r"[^a-z0-9]+", "-", branch)

    # Remove consecutive hyphens
    branch = re.sub(r"-+", "-", branch)

    # Strip leading/trailing hyphens
    branch = branch.strip("-")

    return branch


def create_worker(task: str, path: str, worker_id: int) -> Worker:
    """Create a new worker assignment for a task.

    Creates a Worker instance with a generated branch name based on
    the worker ID and task name.

    Args:
        task: The task name being assigned
        path: Dot-separated path in the tree (e.g., "Root.Feature.Task")
        worker_id: Unique identifier for this worker

    Returns:
        A new Worker instance with status "assigned"
    """
    branch_suffix = task_to_branch_name(task)
    branch = f"worker-{worker_id}-{branch_suffix}"

    return Worker(
        id=worker_id,
        branch=branch,
        task=task,
        path=path,
        status="assigned",
    )


def assign_tasks(
    tasks: list[tuple[str, str]],
    max_workers: int,
    existing_pool: WorkerPool | None = None,
) -> WorkerPool:
    """Assign tasks to workers, creating a new worker pool.

    Takes a list of tasks (as name/path tuples) and assigns them to
    workers up to the max_workers limit. If an existing pool is provided,
    new workers are added to it with appropriate IDs.

    Args:
        tasks: List of (task_name, task_path) tuples to assign
        max_workers: Maximum number of workers to create
        existing_pool: Optional existing pool to add workers to

    Returns:
        A WorkerPool containing the assigned workers

    Examples:
        >>> tasks = [("Build API", "Root.Backend.API"), ("Add Tests", "Root.Tests")]
        >>> pool = assign_tasks(tasks, max_workers=2)
        >>> pool.count()
        2
    """
    pool = existing_pool or WorkerPool()

    # Limit to max_workers
    tasks_to_assign = tasks[:max_workers]

    for task_name, task_path in tasks_to_assign:
        next_id = pool.next_id()
        worker = create_worker(task=task_name, path=task_path, worker_id=next_id)
        pool = pool.add_worker(worker)

    return pool
