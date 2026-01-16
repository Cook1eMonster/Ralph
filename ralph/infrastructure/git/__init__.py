"""Git infrastructure for Ralph.

Provides wrappers around git operations with Result-based error handling.
"""

from ralph.infrastructure.git.operations import (
    GitOperations,
    GitStatus,
    PullResult,
)

__all__ = [
    "GitOperations",
    "GitStatus",
    "PullResult",
]
