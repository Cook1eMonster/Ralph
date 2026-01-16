"""Task application service.

Orchestrates task lifecycle operations by combining domain functions.
All functions are pure - no I/O, no side effects.
"""

from pydantic import BaseModel

from ralph.domain.shared import Err, Ok, Result
from ralph.domain.task import (
    TaskCompleted,
    TaskStarted,
    TaskStatus,
    TaskWithPath,
    Tree,
    count_by_status,
    find_by_path,
    find_next_pending,
    update_at_path,
)


class TreeStats(BaseModel):
    """Statistics about a task tree.

    Provides a summary view of task completion status
    for progress tracking and dashboard display.
    """

    total: int
    done: int
    pending: int
    in_progress: int
    blocked: int

    @property
    def progress_percent(self) -> float:
        """Calculate completion percentage."""
        if self.total == 0:
            return 0.0
        return round(self.done / self.total * 100, 1)


def get_next_task(tree: Tree) -> Result[TaskWithPath, str]:
    """Get the next pending task from the tree.

    Finds the first pending leaf task using depth-first traversal.
    Returns an error if no pending tasks remain.

    Args:
        tree: The task tree to search.

    Returns:
        Ok(TaskWithPath) with the next task and its path, or
        Err(str) if no pending tasks exist.
    """
    task_with_path = find_next_pending(tree)
    if task_with_path is None:
        return Err("No pending tasks found")
    return Ok(task_with_path)


def start_task(
    tree: Tree,
    path: list[str],
    project_id: str = "",
) -> Result[tuple[Tree, TaskStarted], str]:
    """Start a task by marking it in-progress.

    Updates the task at the given path to IN_PROGRESS status
    and emits a TaskStarted event.

    Args:
        tree: The task tree to update.
        path: Path to the task to start.
        project_id: Project identifier for the event.

    Returns:
        Ok((updated_tree, TaskStarted)) on success, or
        Err(str) if the task is not found or already started.
    """
    # Verify task exists
    task = find_by_path(tree, path)
    if task is None:
        return Err(f"Task not found at path: {'/'.join(path)}")

    # Verify task is pending
    if task.status != TaskStatus.PENDING:
        return Err(
            f"Task '{task.name}' is not pending "
            f"(current status: {task.status.value})"
        )

    # Verify task is a leaf
    if not task.is_leaf():
        return Err(f"Task '{task.name}' is a grouping node, not an executable task")

    # Update the task status
    def set_in_progress(node: "task.TaskNode") -> "task.TaskNode":
        return node.model_copy(update={"status": TaskStatus.IN_PROGRESS})

    updated_tree = update_at_path(tree, path, set_in_progress)

    # Create the domain event
    event = TaskStarted(
        project_id=project_id,
        task_path=path,
        task_name=task.name,
    )

    return Ok((updated_tree, event))


def complete_task(
    tree: Tree,
    path: list[str],
    project_id: str = "",
) -> Result[tuple[Tree, TaskCompleted], str]:
    """Complete a task by marking it done.

    Updates the task at the given path to DONE status
    and emits a TaskCompleted event.

    Args:
        tree: The task tree to update.
        path: Path to the task to complete.
        project_id: Project identifier for the event.

    Returns:
        Ok((updated_tree, TaskCompleted)) on success, or
        Err(str) if the task is not found or not in progress.
    """
    # Import here to avoid circular import issues with type hints
    from ralph.domain.task import TaskNode

    # Verify task exists
    task = find_by_path(tree, path)
    if task is None:
        return Err(f"Task not found at path: {'/'.join(path)}")

    # Verify task is in-progress (or pending for flexibility)
    if task.status not in (TaskStatus.IN_PROGRESS, TaskStatus.PENDING):
        return Err(
            f"Task '{task.name}' cannot be completed "
            f"(current status: {task.status.value})"
        )

    # Verify task is a leaf
    if not task.is_leaf():
        return Err(f"Task '{task.name}' is a grouping node, not an executable task")

    # Update the task status
    def set_done(node: TaskNode) -> TaskNode:
        return node.model_copy(update={"status": TaskStatus.DONE})

    updated_tree = update_at_path(tree, path, set_done)

    # Create the domain event
    event = TaskCompleted(
        project_id=project_id,
        task_path=path,
        task_name=task.name,
    )

    return Ok((updated_tree, event))


def get_tree_stats(tree: Tree) -> TreeStats:
    """Calculate statistics for a task tree.

    Counts all leaf tasks by status to provide a summary
    view of project progress.

    Args:
        tree: The task tree to analyze.

    Returns:
        TreeStats with counts by status.
    """
    counts = count_by_status(tree)

    return TreeStats(
        total=sum(counts.values()),
        done=counts[TaskStatus.DONE],
        pending=counts[TaskStatus.PENDING],
        in_progress=counts[TaskStatus.IN_PROGRESS],
        blocked=counts[TaskStatus.BLOCKED],
    )
