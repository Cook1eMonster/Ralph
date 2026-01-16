"""Pure functional business logic for Ralph.

All functions in this module are pure - no I/O, no side effects.
They take data in, return data out.
"""

import re
from typing import Literal, Optional

from .models import (
    TaskNode,
    TaskStatus,
    TokenEstimate,
    TaskWithPath,
    Tree,
    TreeStats,
    Worker,
)

# Token estimation constants
TARGET_TOKENS = 60000
TOKENS_PER_CHAR = 0.25  # ~4 chars per token average
BASE_OVERHEAD = 15000  # System prompt, tool definitions, etc.
TOKENS_PER_FILE = 2500  # Average file read
TOKENS_PER_TOOL_CALL = 500  # Average tool call overhead


# =============================================================================
# Tree Traversal
# =============================================================================


def find_next_task(tree: Tree) -> Optional[TaskWithPath]:
    """Find the next pending leaf task using DFS."""

    def dfs(node: TaskNode, path: list[str]) -> Optional[TaskWithPath]:
        current_path = path + [node.name]

        # If this is a leaf node
        if node.is_leaf():
            if node.status == TaskStatus.PENDING:
                return TaskWithPath(task=node, path=current_path)
            return None

        # Recurse into children
        for child in node.children:
            result = dfs(child, current_path)
            if result:
                return result
        return None

    # Search from root's children
    for child in tree.children:
        result = dfs(child, [tree.name])
        if result:
            return result
    return None


def find_n_tasks(tree: Tree, n: int) -> list[TaskWithPath]:
    """Find up to N pending leaf tasks for parallel workers."""
    tasks: list[TaskWithPath] = []

    def dfs(node: TaskNode, path: list[str]) -> bool:
        """Returns True if we should stop searching."""
        current_path = path + [node.name]

        if node.is_leaf():
            if node.status == TaskStatus.PENDING:
                tasks.append(TaskWithPath(task=node, path=current_path))
                return len(tasks) >= n
            return False

        for child in node.children:
            if dfs(child, current_path):
                return True
        return False

    for child in tree.children:
        if dfs(child, [tree.name]):
            break

    return tasks


def find_task_by_path(tree: Tree, path: list[str]) -> Optional[TaskNode]:
    """Find a task node by its path in the tree."""
    if not path:
        return None

    # Skip root name if it matches
    search_path = path[1:] if path[0] == tree.name else path

    def search(node: TaskNode, remaining: list[str]) -> Optional[TaskNode]:
        if not remaining:
            return node
        if node.name != remaining[0]:
            return None
        if len(remaining) == 1:
            return node
        for child in node.children:
            if child.name == remaining[1]:
                return search(child, remaining[1:])
        return None

    for child in tree.children:
        if child.name == search_path[0]:
            result = search(child, search_path)
            if result:
                return result
    return None


def get_all_pending_tasks(tree: Tree) -> list[TaskWithPath]:
    """Get all pending leaf tasks in the tree."""
    tasks: list[TaskWithPath] = []

    def collect(node: TaskNode, path: list[str]) -> None:
        current_path = path + [node.name]
        if node.is_leaf():
            if node.status == TaskStatus.PENDING:
                tasks.append(TaskWithPath(task=node, path=current_path))
        else:
            for child in node.children:
                collect(child, current_path)

    for child in tree.children:
        collect(child, [tree.name])

    return tasks


# =============================================================================
# Tree Mutations (return new tree - immutable style)
# =============================================================================


def update_task_status(tree: Tree, path: list[str], status: TaskStatus) -> Tree:
    """Update a task's status, returning a new tree."""

    def update_node(node: TaskNode, remaining: list[str]) -> TaskNode:
        if not remaining or remaining[0] != node.name:
            return node

        if len(remaining) == 1:
            # This is the target node
            return node.model_copy(update={"status": status})

        # Recurse into children
        new_children = [update_node(child, remaining[1:]) for child in node.children]
        return node.model_copy(update={"children": new_children})

    # Skip root name
    search_path = path[1:] if path and path[0] == tree.name else path

    new_children = [update_node(child, search_path) for child in tree.children]
    return tree.model_copy(update={"children": new_children})


def mark_task_done(tree: Tree, path: list[str]) -> Tree:
    """Mark a task as done."""
    return update_task_status(tree, path, TaskStatus.DONE)


def mark_task_in_progress(tree: Tree, path: list[str]) -> Tree:
    """Mark a task as in-progress."""
    return update_task_status(tree, path, TaskStatus.IN_PROGRESS)


def add_task(tree: Tree, parent_path: list[str], task: TaskNode) -> Tree:
    """Add a new task under a parent node."""

    def add_to_node(node: TaskNode, remaining: list[str]) -> TaskNode:
        if not remaining or remaining[0] != node.name:
            return node

        if len(remaining) == 1:
            # This is the parent - add the new task
            new_children = node.children + [task]
            return node.model_copy(update={"children": new_children})

        # Recurse
        new_children = [add_to_node(child, remaining[1:]) for child in node.children]
        return node.model_copy(update={"children": new_children})

    search_path = parent_path[1:] if parent_path and parent_path[0] == tree.name else parent_path

    if not search_path:
        # Adding to root
        new_children = tree.children + [task]
        return tree.model_copy(update={"children": new_children})

    new_children = [add_to_node(child, search_path) for child in tree.children]
    return tree.model_copy(update={"children": new_children})


def prune_task(tree: Tree, path: list[str]) -> Tree:
    """Remove a task from the tree."""

    def prune_from_node(node: TaskNode, remaining: list[str]) -> Optional[TaskNode]:
        if not remaining:
            return node

        if len(remaining) == 1:
            # Remove children matching this name
            new_children = [c for c in node.children if c.name != remaining[0]]
            return node.model_copy(update={"children": new_children})

        if remaining[0] != node.name:
            return node

        # Recurse
        new_children = []
        for child in node.children:
            result = prune_from_node(child, remaining[1:])
            if result:
                new_children.append(result)
        return node.model_copy(update={"children": new_children})

    search_path = path[1:] if path and path[0] == tree.name else path

    new_children = []
    for child in tree.children:
        if len(search_path) == 1 and child.name == search_path[0]:
            continue  # Skip this child (prune it)
        result = prune_from_node(child, search_path)
        if result:
            new_children.append(result)

    return tree.model_copy(update={"children": new_children})


# =============================================================================
# Context Building
# =============================================================================


def build_context(tree: Tree, path: list[str], requirements: str = "") -> str:
    """Build accumulated context from root to the task."""
    contexts: list[str] = []

    if tree.context:
        contexts.append(f"Project: {tree.name}\n{tree.context}")

    def collect_context(node: TaskNode, remaining: list[str]) -> None:
        if node.context:
            contexts.append(f"{node.name}: {node.context}")

        if not remaining or len(remaining) == 1:
            return

        for child in node.children:
            if child.name == remaining[1]:
                collect_context(child, remaining[1:])
                break

    search_path = path[1:] if path and path[0] == tree.name else path
    for child in tree.children:
        if search_path and child.name == search_path[0]:
            collect_context(child, search_path)
            break

    if requirements:
        contexts.append(f"Requirements:\n{requirements}")

    return "\n\n".join(contexts)


# =============================================================================
# Token Estimation
# =============================================================================


def estimate_complexity(task: TaskNode) -> Literal["low", "medium", "high"]:
    """Estimate task complexity based on heuristics."""
    name_lower = task.name.lower()

    # High complexity indicators
    high_indicators = [
        "refactor",
        "rewrite",
        "migrate",
        "integration",
        "architecture",
        "security",
        "performance",
        "optimization",
    ]
    if any(ind in name_lower for ind in high_indicators):
        return "high"

    # Medium complexity indicators
    medium_indicators = [
        "implement",
        "create",
        "build",
        "add",
        "feature",
        "endpoint",
        "component",
    ]
    if any(ind in name_lower for ind in medium_indicators):
        return "medium"

    # File count also affects complexity
    if len(task.files) > 3:
        return "high"
    if len(task.files) > 1:
        return "medium"

    return "low"


def estimate_tokens(
    task: TaskNode, context: str, target: int = TARGET_TOKENS
) -> TokenEstimate:
    """Estimate token usage for a task."""
    # Context tokens
    context_tokens = int(len(context) * TOKENS_PER_CHAR)

    # Task description tokens
    task_text = task.name
    if task.spec:
        task_text += f"\n{task.spec}"
    task_tokens = int(len(task_text) * TOKENS_PER_CHAR)

    # File reads estimate
    file_count = len(task.read_first) + len(task.files)
    file_reads = file_count * TOKENS_PER_FILE

    # Tool calls estimate (based on complexity)
    complexity = estimate_complexity(task)
    tool_multiplier = {"low": 8, "medium": 15, "high": 25}
    tool_calls = tool_multiplier[complexity] * TOKENS_PER_TOOL_CALL

    # Response buffer (for generated code, explanations)
    buffer = int(target * 0.2)

    # Total
    total = BASE_OVERHEAD + context_tokens + task_tokens + file_reads + tool_calls + buffer

    return TokenEstimate(
        base_overhead=BASE_OVERHEAD,
        context_tokens=context_tokens,
        task_tokens=task_tokens,
        file_reads=file_reads,
        tool_calls=tool_calls,
        buffer=buffer,
        total=total,
        target=target,
        fits=total <= target,
        utilization=round(total / target * 100, 1),
        complexity=complexity,
    )


# =============================================================================
# Statistics
# =============================================================================


def count_tasks(tree: Tree) -> TreeStats:
    """Count tasks by status."""
    counts = {
        "total": 0,
        "done": 0,
        "pending": 0,
        "in_progress": 0,
        "blocked": 0,
    }

    def count_node(node: TaskNode) -> None:
        if node.is_leaf():
            counts["total"] += 1
            if node.status == TaskStatus.DONE:
                counts["done"] += 1
            elif node.status == TaskStatus.PENDING:
                counts["pending"] += 1
            elif node.status == TaskStatus.IN_PROGRESS:
                counts["in_progress"] += 1
            elif node.status == TaskStatus.BLOCKED:
                counts["blocked"] += 1
        else:
            for child in node.children:
                count_node(child)

    for child in tree.children:
        count_node(child)

    return TreeStats(**counts)


# =============================================================================
# Worker Management
# =============================================================================


def task_to_branch_name(task_name: str) -> str:
    """Convert a task name to a git branch name."""
    # Remove special characters, replace spaces with hyphens
    branch = re.sub(r"[^a-zA-Z0-9\s-]", "", task_name)
    branch = re.sub(r"\s+", "-", branch.strip())
    branch = branch.lower()[:50]
    return f"feat/{branch}"


def create_worker(task: TaskNode, path: list[str], worker_id: int) -> Worker:
    """Create a worker assignment for a task."""
    return Worker(
        id=worker_id,
        branch=task_to_branch_name(task.name),
        task=task.name,
        path=".".join(path),
        status="assigned",
    )


# =============================================================================
# Formatting
# =============================================================================


def format_task_prompt(
    task: TaskNode, context: str, estimate: TokenEstimate
) -> str:
    """Format a task for agent consumption."""
    lines = [
        "=" * 60,
        f"TASK: {task.name}",
        "=" * 60,
    ]

    if task.spec:
        lines.extend(["", "## Spec", task.spec])

    if context:
        lines.extend(["", "## Context", context])

    if task.read_first:
        lines.extend(["", "## Read First (before coding)"])
        for f in task.read_first:
            lines.append(f"  - {f}")

    if task.files:
        lines.extend(["", "## Files to Modify"])
        for f in task.files:
            lines.append(f"  - {f}")

    if task.acceptance:
        lines.extend(["", "## Acceptance Criteria (run before marking done)"])
        for cmd in task.acceptance:
            lines.append(f"  $ {cmd}")

    lines.extend([
        "",
        f"## Estimate: ~{estimate.total:,} tokens ({estimate.utilization}% of {estimate.target:,})",
        f"   Complexity: {estimate.complexity}",
        f"   Fits: {'Yes' if estimate.fits else 'NO - consider splitting'}",
    ])

    return "\n".join(lines)


def format_worker_prompt(worker: Worker, task: TaskNode, context: str) -> str:
    """Format a worker assignment prompt."""
    estimate = estimate_tokens(task, context)
    task_prompt = format_task_prompt(task, context, estimate)

    return f"""WORKER {worker.id} - BRANCH: {worker.branch}

{task_prompt}

When done:
  python ralph/cli.py done-one {worker.id}
"""
