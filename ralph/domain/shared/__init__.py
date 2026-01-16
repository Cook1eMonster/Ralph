"""Shared domain utilities for Ralph's DDD architecture.

This package provides common building blocks used across domain modules:

- Result monad for explicit error handling
- Base domain event infrastructure

Example usage:
    >>> from ralph.domain.shared import Ok, Err, Result, is_ok, DomainEvent
    >>>
    >>> def find_task(task_id: str) -> Result[dict, str]:
    ...     if task_id == "not-found":
    ...         return Err("Task not found")
    ...     return Ok({"id": task_id, "name": "Example"})
"""

from ralph.domain.shared.events import DomainEvent
from ralph.domain.shared.result import (
    Err,
    Ok,
    Result,
    flat_map,
    is_err,
    is_ok,
    map_result,
    unwrap_or,
)

__all__ = [
    # Result monad
    "Ok",
    "Err",
    "Result",
    "is_ok",
    "is_err",
    "map_result",
    "flat_map",
    "unwrap_or",
    # Domain events
    "DomainEvent",
]
