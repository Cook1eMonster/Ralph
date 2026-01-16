"""Project domain events.

Domain events represent significant occurrences within the project domain.
They are immutable records of state changes that can be used for
event sourcing, audit logging, or triggering side effects.

All events are pure data structures - no I/O, no side effects.
"""

from ralph.domain.task.events import DomainEvent


class ProjectCreated(DomainEvent):
    """Event raised when a new project is created.

    Indicates that a new project has been registered with Ralph
    and is ready for task tree initialization.
    """

    project_id: str
    name: str
    path: str


class ProjectLaunched(DomainEvent):
    """Event raised when a project is launched (opened for work).

    Indicates that a project has been activated, with git commits
    pulled and codebase files indexed for context retrieval.
    """

    project_id: str
    commits_pulled: int = 0
    files_indexed: int = 0
