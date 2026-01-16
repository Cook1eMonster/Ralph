"""Worker domain events.

Domain events representing significant occurrences within the worker domain.
These are immutable records of state changes related to worker assignments.

All events are pure data structures - no I/O, no side effects.
"""

from ralph.domain.task.events import DomainEvent


class WorkerAssigned(DomainEvent):
    """Event raised when a worker is assigned to a task.

    Indicates that a new parallel worker has been created and assigned
    to work on a specific task in a dedicated git branch.
    """

    project_id: str
    worker_id: int
    branch_name: str
    task_path: str


class WorkerCompleted(DomainEvent):
    """Event raised when a worker completes its assigned task.

    Indicates that work on the worker's assigned task has finished
    and the branch is ready for integration.
    """

    project_id: str
    worker_id: int
    branch_name: str
