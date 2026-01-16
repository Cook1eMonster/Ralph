"""Worker domain models.

Pydantic models representing workers and worker pools in the Ralph system.
Workers are parallel execution units that process tasks independently.
"""

from typing import Literal

from pydantic import BaseModel, Field


class Worker(BaseModel):
    """A parallel worker assignment.

    Represents an individual worker that has been assigned a task
    and is working on it in a dedicated git branch.
    """

    id: int
    branch: str
    task: str
    path: str  # Dot-separated path in tree, e.g., "Root.Feature.Task"
    status: Literal["assigned", "in-progress", "done"] = "assigned"


class WorkerPool(BaseModel):
    """Collection of worker assignments with pool management methods.

    Represents all active workers in a project, providing methods
    for querying and managing the pool of workers.
    """

    workers: list[Worker] = Field(default_factory=list)

    def get_by_id(self, worker_id: int) -> Worker | None:
        """Get a worker by its ID."""
        for worker in self.workers:
            if worker.id == worker_id:
                return worker
        return None

    def get_by_branch(self, branch: str) -> Worker | None:
        """Get a worker by its branch name."""
        for worker in self.workers:
            if worker.branch == branch:
                return worker
        return None

    def get_active(self) -> list[Worker]:
        """Get all workers that are not done."""
        return [w for w in self.workers if w.status != "done"]

    def get_by_status(self, status: Literal["assigned", "in-progress", "done"]) -> list[Worker]:
        """Get all workers with a specific status."""
        return [w for w in self.workers if w.status == status]

    def count(self) -> int:
        """Get the total number of workers."""
        return len(self.workers)

    def count_active(self) -> int:
        """Get the number of active (non-done) workers."""
        return len(self.get_active())

    def next_id(self) -> int:
        """Get the next available worker ID."""
        if not self.workers:
            return 1
        return max(w.id for w in self.workers) + 1

    def add_worker(self, worker: Worker) -> "WorkerPool":
        """Add a worker to the pool, returning a new pool instance."""
        return WorkerPool(workers=[*self.workers, worker])

    def mark_complete(self, worker_id: int) -> "WorkerPool":
        """Mark a worker as done, returning a new pool instance."""
        updated_workers = [
            Worker(**{**w.model_dump(), "status": "done"}) if w.id == worker_id else w
            for w in self.workers
        ]
        return WorkerPool(workers=updated_workers)

    def clear_done(self) -> "WorkerPool":
        """Remove all done workers, returning a new pool instance."""
        return WorkerPool(workers=self.get_active())
