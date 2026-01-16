"""Task domain events.

Domain events represent significant occurrences within the task domain.
They are immutable records of state changes that can be used for
event sourcing, audit logging, or triggering side effects.

All events are pure data structures - no I/O, no side effects.
"""

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field


class DomainEvent(BaseModel):
    """Base class for all domain events.

    Domain events are immutable records of something that happened.
    Each event has a unique ID and timestamp.
    """

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = {"frozen": True}


class TaskStarted(DomainEvent):
    """Event raised when a task is started (marked in-progress).

    Indicates that work has begun on a task.
    """

    project_id: str
    task_path: list[str]
    task_name: str


class TaskCompleted(DomainEvent):
    """Event raised when a task is completed (marked done).

    Indicates that work on a task has finished successfully.
    """

    project_id: str
    task_path: list[str]
    task_name: str


class TaskBlocked(DomainEvent):
    """Event raised when a task becomes blocked.

    Indicates that work on a task cannot proceed due to
    some impediment that needs resolution.
    """

    project_id: str
    task_path: list[str]
    reason: str | None = None


class TaskAdded(DomainEvent):
    """Event raised when a new task is added to the tree.

    Indicates that the project scope has expanded with a new task.
    """

    project_id: str
    parent_path: list[str]
    task_name: str


class TaskPruned(DomainEvent):
    """Event raised when a task is removed from the tree.

    Indicates that a task has been removed, either because
    it was deemed unnecessary or was completed outside the system.
    """

    project_id: str
    task_path: list[str]
