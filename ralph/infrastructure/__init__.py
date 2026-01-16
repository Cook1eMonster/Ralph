"""Infrastructure layer for Ralph.

This module provides clean interfaces for I/O operations, wrapping
the existing storage, AI context, and git functionality with Result
monads for explicit error handling.

Exports:
    Storage:
        - JsonStorage: Low-level JSON file I/O
        - TreeRepository: Task tree persistence
        - ProjectRepository: Project configuration persistence
        - WorkerRepository: Worker pool persistence

    AI:
        - OllamaClient: Embeddings and summarization
        - ContextEngineWrapper: Semantic search over codebase

    Git:
        - GitOperations: Git repository operations
        - GitStatus: Status check result
        - PullResult: Pull operation result
"""

from ralph.infrastructure.storage import (
    JsonStorage,
    ProjectRepository,
    TreeRepository,
    WorkerRepository,
)
from ralph.infrastructure.ai import (
    ContextEngineWrapper,
    OllamaClient,
    SearchResult,
)
from ralph.infrastructure.git import (
    GitOperations,
    GitStatus,
    PullResult,
)

__all__ = [
    # Storage
    "JsonStorage",
    "TreeRepository",
    "ProjectRepository",
    "WorkerRepository",
    # AI
    "OllamaClient",
    "ContextEngineWrapper",
    "SearchResult",
    # Git
    "GitOperations",
    "GitStatus",
    "PullResult",
]
