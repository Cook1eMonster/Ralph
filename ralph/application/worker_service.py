"""Worker application service.

Orchestrates parallel worker management by combining domain functions.
All functions are pure - no I/O, no side effects.
"""

from typing import Literal

from pydantic import BaseModel, Field

from ralph.domain.shared import Err, Ok, Result
from ralph.domain.shared.events import DomainEvent
from ralph.domain.task import TaskWithPath, Tree, find_n_pending


class Worker(BaseModel):
    """A parallel worker assignment.

    Represents a task assigned to a specific worker for
    parallel execution, typically on a feature branch.
    """

    id: int
    branch: str
    task: str
    path: list[str]
    status: Literal["assigned", "in-progress", "done"] = "assigned"


class WorkerPool(BaseModel):
    """Collection of worker assignments.

    Manages a set of workers executing tasks in parallel.
    """

    workers: list[Worker] = Field(default_factory=list)

    def get_worker(self, worker_id: int) -> Worker | None:
        """Find a worker by ID."""
        for worker in self.workers:
            if worker.id == worker_id:
                return worker
        return None

    def active_count(self) -> int:
        """Count workers that are assigned or in-progress."""
        return sum(1 for w in self.workers if w.status != "done")


class WorkerCompleted(DomainEvent):
    """Event raised when a worker completes their task.

    Indicates that a parallel worker has finished their assigned
    task and the branch is ready for merge.
    """

    worker_id: int
    task_path: list[str]
    task_name: str
    branch: str


def assign_workers(tree: Tree, n: int) -> Result[WorkerPool, str]:
    """Assign N workers to pending tasks.

    Finds up to N pending leaf tasks and creates worker
    assignments for parallel execution.

    Args:
        tree: The task tree to search for pending tasks.
        n: Maximum number of workers to assign.

    Returns:
        Ok(WorkerPool) with worker assignments, or
        Err(str) if no pending tasks are available.
    """
    if n <= 0:
        return Err("Worker count must be positive")

    # Find pending tasks
    pending_tasks: list[TaskWithPath] = find_n_pending(tree, n)

    if not pending_tasks:
        return Err("No pending tasks available for assignment")

    # Create worker assignments
    workers: list[Worker] = []
    for i, task_with_path in enumerate(pending_tasks, start=1):
        # Generate branch name from task path
        branch_suffix = "-".join(
            part.lower().replace(" ", "-")[:20]
            for part in task_with_path.path[-2:]  # Last 2 path segments
        )
        branch = f"worker-{i}-{branch_suffix}"

        worker = Worker(
            id=i,
            branch=branch,
            task=task_with_path.task.name,
            path=task_with_path.path,
            status="assigned",
        )
        workers.append(worker)

    return Ok(WorkerPool(workers=workers))


def complete_worker(
    pool: WorkerPool,
    worker_id: int,
) -> Result[tuple[WorkerPool, WorkerCompleted], str]:
    """Complete a worker's task.

    Marks the worker as done and emits a WorkerCompleted event.
    Does not modify the task tree - that should be done separately
    using task_service.complete_task.

    Args:
        pool: The worker pool to update.
        worker_id: ID of the worker to complete.

    Returns:
        Ok((updated_pool, WorkerCompleted)) on success, or
        Err(str) if the worker is not found or already done.
    """
    worker = pool.get_worker(worker_id)
    if worker is None:
        return Err(f"Worker {worker_id} not found")

    if worker.status == "done":
        return Err(f"Worker {worker_id} is already done")

    # Create updated worker
    updated_worker = worker.model_copy(update={"status": "done"})

    # Create updated pool with the worker replaced
    updated_workers = [
        updated_worker if w.id == worker_id else w
        for w in pool.workers
    ]
    updated_pool = WorkerPool(workers=updated_workers)

    # Create the domain event
    event = WorkerCompleted(
        worker_id=worker_id,
        task_path=worker.path,
        task_name=worker.task,
        branch=worker.branch,
    )

    return Ok((updated_pool, event))
