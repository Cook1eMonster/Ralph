"""Base domain event infrastructure.

Domain events represent significant occurrences within the domain that other
parts of the system may need to react to. They are immutable records of
something that happened, captured at the moment it occurred.

Example usage:
    >>> from dataclasses import dataclass
    >>> from ralph.domain.shared.events import DomainEvent
    >>>
    >>> @dataclass(frozen=True)
    ... class TaskCompleted(DomainEvent):
    ...     task_id: str
    ...     completed_by: str
    ...
    >>> event = TaskCompleted(task_id="task-123", completed_by="worker-1")
    >>> print(f"Event {event.event_id} occurred at {event.occurred_at}")
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4


@dataclass(frozen=True)
class DomainEvent:
    """Base class for all domain events.

    Domain events are immutable records of something that happened in the domain.
    Each event has a unique identifier and a timestamp of when it occurred.

    Subclasses should be frozen dataclasses that add domain-specific fields.

    Attributes:
        event_id: Unique identifier for this event instance.
        occurred_at: UTC timestamp when the event occurred.
    """

    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
