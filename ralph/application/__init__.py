"""Application service layer for Ralph's DDD architecture.

This package contains application services that orchestrate domain operations.
Services are pure functions that combine domain logic without performing I/O.

Services:
    task_service - Task lifecycle operations (start, complete, get next)
    worker_service - Parallel worker management
    project_service - Project-level operations and summaries

Example usage:
    >>> from ralph.application import get_next_task, start_task, complete_task
    >>> from ralph.domain.shared import is_ok
    >>>
    >>> result = get_next_task(tree)
    >>> if is_ok(result):
    ...     task_with_path = result.value
    ...     print(f"Next task: {task_with_path.task.name}")
"""

from ralph.application.project_service import (
    create_project,
    get_project_summary,
)
from ralph.application.task_service import (
    TreeStats,
    complete_task,
    get_next_task,
    get_tree_stats,
    start_task,
)
from ralph.application.worker_service import (
    Worker,
    WorkerCompleted,
    WorkerPool,
    assign_workers,
    complete_worker,
)

__all__ = [
    # Task service
    "get_next_task",
    "start_task",
    "complete_task",
    "get_tree_stats",
    "TreeStats",
    # Worker service
    "assign_workers",
    "complete_worker",
    "Worker",
    "WorkerPool",
    "WorkerCompleted",
    # Project service
    "get_project_summary",
    "create_project",
]
