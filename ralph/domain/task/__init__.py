"""Task domain - core task tree management.

This module provides the domain layer for Ralph's task management,
following Domain-Driven Design principles. All exports are pure
(no I/O, no side effects).

Key Types:
    TaskStatus - Task state enumeration
    TaskNode - Tree node representing a task or grouping
    Tree - Root of a task tree
    TaskWithPath - Task with its location in the tree
    TokenCount - Token estimation result
    Complexity - Task complexity level

Traversal Functions:
    fold_tree - Fundamental fold operation
    filter_nodes - Filter by predicate
    find_first - Find first matching node
    map_nodes - Transform all nodes
    update_at_path - Update at specific path
    find_next_pending - Get next pending task
    find_n_pending - Get n pending tasks
    count_by_status - Count tasks by status

Estimation Functions:
    estimate_tokens - Estimate token usage
    estimate_complexity - Estimate task complexity

Domain Events:
    TaskStarted - Task work begun
    TaskCompleted - Task finished
    TaskBlocked - Task blocked
    TaskAdded - New task added
    TaskPruned - Task removed
"""

from .estimation import (
    BASE_OVERHEAD,
    TARGET_TOKENS,
    TOKENS_PER_CHAR,
    TOKENS_PER_FILE,
    TOKENS_PER_TOOL_CALL,
    Complexity,
    TokenCount,
    estimate_complexity,
    estimate_tokens,
)
from .events import (
    DomainEvent,
    TaskAdded,
    TaskBlocked,
    TaskCompleted,
    TaskPruned,
    TaskStarted,
)
from .models import TaskNode, TaskStatus, TaskWithPath, Tree
from .traversal import (
    count_by_status,
    filter_nodes,
    find_by_path,
    find_first,
    find_n_pending,
    find_next_pending,
    fold_tree,
    get_all_leaves,
    get_all_pending,
    has_status,
    is_leaf,
    is_pending_leaf,
    map_nodes,
    path_matches,
    update_at_path,
)

__all__ = [
    # Models
    "TaskStatus",
    "TaskNode",
    "Tree",
    "TaskWithPath",
    # Traversal - fundamental
    "fold_tree",
    "filter_nodes",
    "find_first",
    "map_nodes",
    "update_at_path",
    # Traversal - predicates
    "is_leaf",
    "is_pending_leaf",
    "has_status",
    "path_matches",
    # Traversal - high-level
    "find_next_pending",
    "find_n_pending",
    "count_by_status",
    "find_by_path",
    "get_all_leaves",
    "get_all_pending",
    # Estimation
    "TARGET_TOKENS",
    "TOKENS_PER_CHAR",
    "BASE_OVERHEAD",
    "TOKENS_PER_FILE",
    "TOKENS_PER_TOOL_CALL",
    "TokenCount",
    "Complexity",
    "estimate_tokens",
    "estimate_complexity",
    # Events
    "DomainEvent",
    "TaskStarted",
    "TaskCompleted",
    "TaskBlocked",
    "TaskAdded",
    "TaskPruned",
]
