"""Task details panel widget for Ralph TUI."""

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Static, ProgressBar, Label

from ralph.models import TaskNode, TaskStatus, TokenEstimate


# Status colors for display
STATUS_COLORS = {
    TaskStatus.DONE: "green",
    TaskStatus.PENDING: "dim",
    TaskStatus.IN_PROGRESS: "yellow",
    TaskStatus.BLOCKED: "red",
}

# Complexity colors
COMPLEXITY_COLORS = {
    "low": "green",
    "medium": "yellow",
    "high": "red",
}


class TaskPanel(Static):
    """Panel displaying details of the selected task."""

    DEFAULT_CSS = """
    TaskPanel {
        background: $surface;
        padding: 1 2;
        border: solid $primary;
        height: auto;
        min-height: 20;
    }

    TaskPanel .task-header {
        text-style: bold;
        margin-bottom: 1;
    }

    TaskPanel .task-status {
        margin-bottom: 1;
    }

    TaskPanel .task-section {
        margin-top: 1;
    }

    TaskPanel .task-section-header {
        text-style: bold underline;
        margin-bottom: 0;
    }

    TaskPanel .task-list-item {
        padding-left: 2;
    }

    TaskPanel .token-section {
        margin-top: 1;
        padding: 1;
        background: $surface-darken-1;
    }

    TaskPanel ProgressBar {
        margin-top: 1;
        width: 100%;
    }

    TaskPanel .complexity-low {
        color: green;
    }

    TaskPanel .complexity-medium {
        color: yellow;
    }

    TaskPanel .complexity-high {
        color: red;
    }

    TaskPanel .no-task {
        color: $text-muted;
        text-align: center;
        margin-top: 5;
    }
    """

    def __init__(
        self,
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ) -> None:
        super().__init__(id=id, classes=classes)
        self._task: Optional[TaskNode] = None
        self._path: list[str] = []
        self._estimate: Optional[TokenEstimate] = None

    def compose(self) -> ComposeResult:
        """Create the panel structure."""
        yield Vertical(
            Static("No task selected", id="task-content", classes="no-task"),
            id="task-panel-container",
        )

    def update_task(
        self,
        task: TaskNode,
        path: list[str],
        estimate: TokenEstimate,
    ) -> None:
        """Update the panel with a new task.

        Args:
            task: The TaskNode to display.
            path: Path to the task in the tree.
            estimate: Token usage estimate for the task.
        """
        self._task = task
        self._path = path
        self._estimate = estimate
        self._refresh_content()

    def clear_task(self) -> None:
        """Clear the task display."""
        self._task = None
        self._path = []
        self._estimate = None
        self._refresh_content()

    def _refresh_content(self) -> None:
        """Refresh the panel content."""
        content_widget = self.query_one("#task-content", Static)

        if self._task is None:
            content_widget.update("No task selected")
            content_widget.add_class("no-task")
            return

        content_widget.remove_class("no-task")
        task = self._task
        estimate = self._estimate

        # Build the content
        lines = []

        # Task name header
        lines.append(f"[bold underline]{task.name}[/bold underline]")
        lines.append("")

        # Path
        if self._path:
            path_str = " > ".join(self._path)
            lines.append(f"[dim]Path: {path_str}[/dim]")
            lines.append("")

        # Status with color
        status_color = STATUS_COLORS.get(task.status, "white")
        status_display = task.status.value.replace("-", " ").title()
        lines.append(f"Status: [{status_color}]{status_display}[/{status_color}]")
        lines.append("")

        # Spec
        if task.spec:
            lines.append("[bold]Spec:[/bold]")
            # Indent spec lines
            for line in task.spec.split("\n"):
                lines.append(f"  {line}")
            lines.append("")

        # Context
        if task.context:
            lines.append("[bold]Context:[/bold]")
            for line in task.context.split("\n"):
                lines.append(f"  {line}")
            lines.append("")

        # Read First files
        if task.read_first:
            lines.append("[bold]Read First:[/bold]")
            for f in task.read_first:
                lines.append(f"  [cyan]{f}[/cyan]")
            lines.append("")

        # Files to modify
        if task.files:
            lines.append("[bold]Files to Modify:[/bold]")
            for f in task.files:
                lines.append(f"  [magenta]{f}[/magenta]")
            lines.append("")

        # Acceptance criteria
        if task.acceptance:
            lines.append("[bold]Acceptance Criteria:[/bold]")
            for cmd in task.acceptance:
                lines.append(f"  [green]$ {cmd}[/green]")
            lines.append("")

        # Token estimate section
        if estimate:
            lines.append("[bold]Token Estimate:[/bold]")

            # Progress indicator
            utilization = estimate.utilization
            if utilization <= 80:
                util_color = "green"
            elif utilization <= 100:
                util_color = "yellow"
            else:
                util_color = "red"

            lines.append(
                f"  [{util_color}]{estimate.total:,}[/{util_color}] / {estimate.target:,} tokens "
                f"([{util_color}]{utilization}%[/{util_color}])"
            )

            # Fits indicator
            if estimate.fits:
                lines.append("  [green][\u2713] Fits within target[/green]")
            else:
                lines.append("  [red][\u2717] Exceeds target - consider splitting[/red]")

            # Breakdown
            lines.append("")
            lines.append("  [dim]Breakdown:[/dim]")
            lines.append(f"    Base overhead: {estimate.base_overhead:,}")
            lines.append(f"    Context: {estimate.context_tokens:,}")
            lines.append(f"    Task description: {estimate.task_tokens:,}")
            lines.append(f"    File reads: {estimate.file_reads:,}")
            lines.append(f"    Tool calls: {estimate.tool_calls:,}")
            lines.append(f"    Buffer: {estimate.buffer:,}")
            lines.append("")

            # Complexity indicator
            complexity_color = COMPLEXITY_COLORS.get(estimate.complexity, "white")
            complexity_label = estimate.complexity.upper()
            lines.append(f"  Complexity: [{complexity_color}]{complexity_label}[/{complexity_color}]")

        content_widget.update("\n".join(lines))

    @property
    def current_task(self) -> Optional[TaskNode]:
        """Get the currently displayed task."""
        return self._task

    @property
    def current_path(self) -> list[str]:
        """Get the path of the currently displayed task."""
        return self._path.copy()

    @property
    def current_estimate(self) -> Optional[TokenEstimate]:
        """Get the token estimate for the current task."""
        return self._estimate
