"""Task tree widget for Ralph TUI."""

from typing import Optional

from textual.message import Message
from textual.widgets import Tree
from textual.widgets.tree import TreeNode

from ralph.models import TaskNode, TaskStatus, Tree as RalphTree


# Status icons for visual representation
STATUS_ICONS = {
    TaskStatus.DONE: "[green][\u2611][/green]",        # Checkmark
    TaskStatus.PENDING: "[dim][\u2610][/dim]",         # Empty box
    TaskStatus.IN_PROGRESS: "[yellow][\u25cf][/yellow]",  # Filled circle
    TaskStatus.BLOCKED: "[red][\u26d4][/red]",         # No entry
}


class TaskSelected(Message):
    """Message posted when a task is selected in the tree."""

    def __init__(self, task: TaskNode, path: list[str]) -> None:
        super().__init__()
        self.task = task
        self.path = path


class TaskTreeWidget(Tree[TaskNode]):
    """Widget displaying the task tree with status icons and expand/collapse."""

    DEFAULT_CSS = """
    TaskTreeWidget {
        background: $surface;
        padding: 1;
        border: solid $primary;
    }

    TaskTreeWidget > .tree--label {
        padding: 0 1;
    }

    TaskTreeWidget > .tree--cursor {
        background: $accent;
        color: $text;
    }

    TaskTreeWidget:focus > .tree--cursor {
        background: $primary;
    }
    """

    def __init__(
        self,
        label: str = "Tasks",
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ) -> None:
        super().__init__(label, id=id, classes=classes)
        self._ralph_tree: Optional[RalphTree] = None
        self._task_paths: dict[int, list[str]] = {}  # node_id -> path

    def load_tree(self, tree: RalphTree) -> None:
        """Load a Ralph tree into the widget.

        Args:
            tree: The Ralph Tree model to display.
        """
        self._ralph_tree = tree
        self._task_paths.clear()
        self.clear()

        # Set root label with tree name
        self.root.set_label(f"[bold]{tree.name}[/bold]")
        self.root.data = None  # Root doesn't have task data

        # Add children recursively
        for child in tree.children:
            self._add_task_node(self.root, child, [tree.name])

        # Expand the root by default
        self.root.expand()

    def _add_task_node(
        self,
        parent: TreeNode[TaskNode],
        task: TaskNode,
        parent_path: list[str],
    ) -> None:
        """Recursively add a task node to the tree.

        Args:
            parent: The parent tree node.
            task: The TaskNode to add.
            parent_path: Path to the parent node.
        """
        current_path = parent_path + [task.name]

        # Build the label with status icon
        icon = STATUS_ICONS.get(task.status, "[ ]")
        if task.is_leaf():
            label = f"{icon} {task.name}"
        else:
            # Non-leaf nodes show as folders/groups
            label = f"[bold]{icon} {task.name}[/bold]"

        # Add the node
        if task.is_leaf():
            # Leaf nodes don't expand
            node = parent.add_leaf(label, data=task)
        else:
            # Non-leaf nodes can expand
            node = parent.add(label, data=task)
            # Add children
            for child in task.children:
                self._add_task_node(node, child, current_path)

        # Store the path mapping
        self._task_paths[id(node)] = current_path

    def on_tree_node_selected(self, event: Tree.NodeSelected[TaskNode]) -> None:
        """Handle node selection and post TaskSelected message."""
        event.stop()

        node = event.node
        task = node.data

        if task is not None:
            # Get the path for this node
            path = self._task_paths.get(id(node), [])
            self.post_message(TaskSelected(task, path))

    def refresh_node(self, path: list[str], task: TaskNode) -> None:
        """Refresh a specific node's display after status change.

        Args:
            path: Path to the node in the tree.
            task: Updated task data.
        """
        # Find the node by path
        node = self._find_node_by_path(path)
        if node is None:
            return

        # Update the label
        icon = STATUS_ICONS.get(task.status, "[ ]")
        if task.is_leaf():
            label = f"{icon} {task.name}"
        else:
            label = f"[bold]{icon} {task.name}[/bold]"

        node.set_label(label)
        node.data = task

    def _find_node_by_path(self, path: list[str]) -> Optional[TreeNode[TaskNode]]:
        """Find a tree node by its path.

        Args:
            path: List of node names from root to target.

        Returns:
            The TreeNode if found, None otherwise.
        """
        if not path or not self._ralph_tree:
            return None

        # Start from root's children (skip root name in path)
        search_path = path[1:] if path[0] == self._ralph_tree.name else path

        current_node = self.root
        for name in search_path:
            found = False
            for child in current_node.children:
                if child.data and child.data.name == name:
                    current_node = child
                    found = True
                    break
            if not found:
                return None

        return current_node if current_node != self.root else None

    def expand_to_path(self, path: list[str]) -> None:
        """Expand tree to show a specific node.

        Args:
            path: Path to the node to reveal.
        """
        if not path or not self._ralph_tree:
            return

        search_path = path[1:] if path[0] == self._ralph_tree.name else path

        current_node = self.root
        current_node.expand()

        for name in search_path:
            for child in current_node.children:
                if child.data and child.data.name == name:
                    child.expand()
                    current_node = child
                    break

    def collapse_all(self) -> None:
        """Collapse all nodes except root."""
        def collapse_recursive(node: TreeNode[TaskNode]) -> None:
            for child in node.children:
                child.collapse()
                collapse_recursive(child)

        collapse_recursive(self.root)

    def expand_all(self) -> None:
        """Expand all nodes in the tree."""
        def expand_recursive(node: TreeNode[TaskNode]) -> None:
            node.expand()
            for child in node.children:
                expand_recursive(child)

        expand_recursive(self.root)

    def get_selected_task(self) -> Optional[tuple[TaskNode, list[str]]]:
        """Get the currently selected task and its path.

        Returns:
            Tuple of (TaskNode, path) if a task is selected, None otherwise.
        """
        cursor_node = self.cursor_node
        if cursor_node is None or cursor_node.data is None:
            return None

        path = self._task_paths.get(id(cursor_node), [])
        return (cursor_node.data, path)

    def set_tree(self, tree: RalphTree) -> None:
        """Alias for load_tree for compatibility."""
        self.load_tree(tree)

    def refresh_tree(self) -> None:
        """Refresh the tree display by reloading from the stored tree."""
        if self._ralph_tree:
            self.load_tree(self._ralph_tree)
