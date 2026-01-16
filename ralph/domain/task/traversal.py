"""Pure tree traversal combinators.

All functions in this module are pure - no I/O, no side effects.
They take data in, return data out.
"""

from collections.abc import Callable
from typing import TypeVar

from .models import TaskNode, TaskStatus, TaskWithPath, Tree

T = TypeVar("T")


# =============================================================================
# Fundamental Operations
# =============================================================================


def fold_tree(
    tree: Tree,
    initial: T,
    f: Callable[[T, TaskNode, list[str]], T],
) -> T:
    """Fold over all nodes in the tree with their paths.

    This is the fundamental operation from which many others derive.
    Visits every node in depth-first order, accumulating a result.

    Args:
        tree: The tree to fold over
        initial: Starting accumulator value
        f: Function (accumulator, node, path) -> new_accumulator

    Returns:
        Final accumulated value after visiting all nodes
    """

    def fold_node(acc: T, node: TaskNode, path: list[str]) -> T:
        current_path = path + [node.name]
        acc = f(acc, node, current_path)
        for child in node.children:
            acc = fold_node(acc, child, current_path)
        return acc

    result = initial
    for child in tree.children:
        result = fold_node(result, child, [tree.name])
    return result


def filter_nodes(
    tree: Tree,
    predicate: Callable[[TaskNode, list[str]], bool],
) -> list[TaskWithPath]:
    """Filter nodes matching a predicate.

    Args:
        tree: The tree to search
        predicate: Function (node, path) -> bool

    Returns:
        List of matching nodes with their paths
    """

    def collect(
        acc: list[TaskWithPath],
        node: TaskNode,
        path: list[str],
    ) -> list[TaskWithPath]:
        if predicate(node, path):
            acc.append(TaskWithPath(task=node, path=path))
        return acc

    return fold_tree(tree, [], collect)


def find_first(
    tree: Tree,
    predicate: Callable[[TaskNode, list[str]], bool],
) -> TaskWithPath | None:
    """Find the first node matching a predicate (depth-first).

    Args:
        tree: The tree to search
        predicate: Function (node, path) -> bool

    Returns:
        First matching node with path, or None
    """

    def search(node: TaskNode, path: list[str]) -> TaskWithPath | None:
        current_path = path + [node.name]
        if predicate(node, current_path):
            return TaskWithPath(task=node, path=current_path)
        for child in node.children:
            result = search(child, current_path)
            if result:
                return result
        return None

    for child in tree.children:
        result = search(child, [tree.name])
        if result:
            return result
    return None


def map_nodes(
    tree: Tree,
    f: Callable[[TaskNode, list[str]], TaskNode],
) -> Tree:
    """Transform all nodes in the tree.

    Args:
        tree: The tree to transform
        f: Function (node, path) -> new_node

    Returns:
        New tree with all nodes transformed
    """

    def transform(node: TaskNode, path: list[str]) -> TaskNode:
        current_path = path + [node.name]
        new_children = [transform(child, current_path) for child in node.children]
        transformed = f(node, current_path)
        return transformed.model_copy(update={"children": new_children})

    new_children = [transform(child, [tree.name]) for child in tree.children]
    return tree.model_copy(update={"children": new_children})


def update_at_path(
    tree: Tree,
    path: list[str],
    update: Callable[[TaskNode], TaskNode],
) -> Tree:
    """Update a node at a specific path.

    Args:
        tree: The tree to update
        path: Path to the node (list of names from root)
        update: Function (node) -> new_node

    Returns:
        New tree with the node at path updated
    """

    def update_node(node: TaskNode, remaining: list[str]) -> TaskNode:
        if not remaining or remaining[0] != node.name:
            return node

        if len(remaining) == 1:
            # This is the target node
            return update(node)

        # Recurse into children
        new_children = [update_node(child, remaining[1:]) for child in node.children]
        return node.model_copy(update={"children": new_children})

    # Skip root name if present
    search_path = path[1:] if path and path[0] == tree.name else path

    new_children = [update_node(child, search_path) for child in tree.children]
    return tree.model_copy(update={"children": new_children})


# =============================================================================
# Predicate Functions
# =============================================================================


def is_leaf(node: TaskNode, path: list[str]) -> bool:
    """Check if a node is a leaf (no children).

    Can be used directly as a predicate or combined with others.
    """
    return node.is_leaf()


def is_pending_leaf(node: TaskNode, path: list[str]) -> bool:
    """Check if a node is a pending leaf task.

    Leaf nodes with PENDING status are eligible for execution.
    """
    return node.is_leaf() and node.status == TaskStatus.PENDING


def has_status(status: TaskStatus) -> Callable[[TaskNode, list[str]], bool]:
    """Return a predicate that checks for a specific status.

    Args:
        status: The status to check for

    Returns:
        Predicate function (node, path) -> bool
    """

    def predicate(node: TaskNode, path: list[str]) -> bool:
        return node.status == status

    return predicate


def path_matches(target_path: list[str]) -> Callable[[TaskNode, list[str]], bool]:
    """Return a predicate that matches a specific path.

    Args:
        target_path: The path to match

    Returns:
        Predicate function (node, path) -> bool
    """

    def predicate(node: TaskNode, path: list[str]) -> bool:
        return path == target_path

    return predicate


# =============================================================================
# High-Level Operations
# =============================================================================


def find_next_pending(tree: Tree) -> TaskWithPath | None:
    """Find the next pending leaf task using depth-first search.

    This is the primary way to get the next task to work on.

    Returns:
        Next pending leaf task with path, or None if all done
    """
    return find_first(tree, is_pending_leaf)


def find_n_pending(tree: Tree, n: int) -> list[TaskWithPath]:
    """Find up to N pending leaf tasks for parallel workers.

    Args:
        tree: The tree to search
        n: Maximum number of tasks to return

    Returns:
        List of up to n pending leaf tasks with paths
    """
    tasks: list[TaskWithPath] = []

    def collect_up_to_n(node: TaskNode, path: list[str]) -> bool:
        """Returns True if we should stop searching."""
        current_path = path + [node.name]

        if node.is_leaf():
            if node.status == TaskStatus.PENDING:
                tasks.append(TaskWithPath(task=node, path=current_path))
                return len(tasks) >= n
            return False

        for child in node.children:
            if collect_up_to_n(child, current_path):
                return True
        return False

    for child in tree.children:
        if collect_up_to_n(child, [tree.name]):
            break

    return tasks


def count_by_status(tree: Tree) -> dict[TaskStatus, int]:
    """Count leaf tasks by status.

    Only counts leaf nodes (actual tasks), not grouping nodes.

    Returns:
        Dict mapping status to count
    """
    counts: dict[TaskStatus, int] = {
        TaskStatus.PENDING: 0,
        TaskStatus.IN_PROGRESS: 0,
        TaskStatus.DONE: 0,
        TaskStatus.BLOCKED: 0,
    }

    def count(
        acc: dict[TaskStatus, int],
        node: TaskNode,
        path: list[str],
    ) -> dict[TaskStatus, int]:
        if node.is_leaf():
            acc[node.status] += 1
        return acc

    return fold_tree(tree, counts, count)


def find_by_path(tree: Tree, path: list[str]) -> TaskNode | None:
    """Find a task node by its path in the tree.

    Args:
        tree: The tree to search
        path: Path to the node (list of names)

    Returns:
        The node at the path, or None if not found
    """
    result = find_first(tree, path_matches(path))
    return result.task if result else None


def get_all_leaves(tree: Tree) -> list[TaskWithPath]:
    """Get all leaf nodes (executable tasks) in the tree.

    Returns:
        List of all leaf nodes with their paths
    """
    return filter_nodes(tree, is_leaf)


def get_all_pending(tree: Tree) -> list[TaskWithPath]:
    """Get all pending leaf tasks in the tree.

    Returns:
        List of all pending leaf tasks with paths
    """
    return filter_nodes(tree, is_pending_leaf)
