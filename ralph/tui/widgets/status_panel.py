"""Status panel widget for Ralph TUI."""

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Static, ProgressBar, DataTable

from ralph.models import TreeStats, Worker


class StatusPanel(Static):
    """Panel displaying overall progress and worker status."""

    DEFAULT_CSS = """
    StatusPanel {
        background: $surface;
        padding: 1 2;
        border: solid $primary;
        height: auto;
        min-height: 15;
    }

    StatusPanel .status-header {
        text-style: bold;
        text-align: center;
        margin-bottom: 1;
    }

    StatusPanel .progress-section {
        margin-bottom: 1;
    }

    StatusPanel .progress-label {
        margin-bottom: 0;
    }

    StatusPanel ProgressBar {
        width: 100%;
        margin: 0 0 1 0;
    }

    StatusPanel .status-counts {
        margin: 1 0;
    }

    StatusPanel .count-row {
        height: 1;
    }

    StatusPanel .count-label {
        width: 15;
    }

    StatusPanel .count-value {
        width: 8;
        text-align: right;
    }

    StatusPanel .count-pending {
        color: $text-muted;
    }

    StatusPanel .count-in-progress {
        color: yellow;
    }

    StatusPanel .count-done {
        color: green;
    }

    StatusPanel .count-blocked {
        color: red;
    }

    StatusPanel .workers-section {
        margin-top: 1;
    }

    StatusPanel .workers-header {
        text-style: bold;
        margin-bottom: 1;
    }

    StatusPanel DataTable {
        height: auto;
        max-height: 10;
    }

    StatusPanel .no-workers {
        color: $text-muted;
        text-align: center;
    }
    """

    def __init__(
        self,
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ) -> None:
        super().__init__(id=id, classes=classes)
        self._stats: Optional[TreeStats] = None
        self._workers: list[Worker] = []

    def compose(self) -> ComposeResult:
        """Create the panel structure."""
        with Vertical():
            # Header
            yield Static("Project Progress", classes="status-header")

            # Progress section
            with Vertical(classes="progress-section"):
                yield Static("0 / 0 tasks (0%)", id="progress-label", classes="progress-label")
                yield ProgressBar(total=100, show_eta=False, id="progress-bar")

            # Status counts
            with Vertical(classes="status-counts"):
                with Horizontal(classes="count-row"):
                    yield Static("Pending:", classes="count-label count-pending")
                    yield Static("0", id="count-pending", classes="count-value count-pending")
                with Horizontal(classes="count-row"):
                    yield Static("In Progress:", classes="count-label count-in-progress")
                    yield Static("0", id="count-in-progress", classes="count-value count-in-progress")
                with Horizontal(classes="count-row"):
                    yield Static("Done:", classes="count-label count-done")
                    yield Static("0", id="count-done", classes="count-value count-done")
                with Horizontal(classes="count-row"):
                    yield Static("Blocked:", classes="count-label count-blocked")
                    yield Static("0", id="count-blocked", classes="count-value count-blocked")

            # Workers section
            with Vertical(classes="workers-section"):
                yield Static("Workers", classes="workers-header")
                yield DataTable(id="workers-table")
                yield Static("No active workers", id="no-workers-label", classes="no-workers")

    def on_mount(self) -> None:
        """Initialize the workers table on mount."""
        table = self.query_one("#workers-table", DataTable)
        table.add_columns("ID", "Branch", "Task", "Status")
        table.display = False  # Hidden until workers exist

    def update_stats(self, stats: TreeStats) -> None:
        """Update the progress display with new stats.

        Args:
            stats: The TreeStats to display.
        """
        self._stats = stats
        self._refresh_stats()

    def update_workers(self, workers: list[Worker]) -> None:
        """Update the workers table.

        Args:
            workers: List of Worker assignments.
        """
        self._workers = workers
        self._refresh_workers()

    def _refresh_stats(self) -> None:
        """Refresh the stats display."""
        stats = self._stats

        if stats is None:
            return

        # Update progress label
        progress_label = self.query_one("#progress-label", Static)
        percent = stats.progress_percent
        progress_label.update(f"{stats.done} / {stats.total} tasks ({percent}%)")

        # Update progress bar
        progress_bar = self.query_one("#progress-bar", ProgressBar)
        progress_bar.update(total=100, progress=percent)

        # Update counts
        self.query_one("#count-pending", Static).update(str(stats.pending))
        self.query_one("#count-in-progress", Static).update(str(stats.in_progress))
        self.query_one("#count-done", Static).update(str(stats.done))
        self.query_one("#count-blocked", Static).update(str(stats.blocked))

    def _refresh_workers(self) -> None:
        """Refresh the workers table."""
        table = self.query_one("#workers-table", DataTable)
        no_workers_label = self.query_one("#no-workers-label", Static)

        # Clear existing rows
        table.clear()

        if not self._workers:
            table.display = False
            no_workers_label.display = True
            return

        table.display = True
        no_workers_label.display = False

        # Add worker rows
        for worker in self._workers:
            # Color-code status
            status_display = self._format_worker_status(worker.status)

            # Truncate long values
            branch = self._truncate(worker.branch, 20)
            task = self._truncate(worker.task, 25)

            table.add_row(
                str(worker.id),
                branch,
                task,
                status_display,
            )

    def _format_worker_status(self, status: str) -> str:
        """Format worker status with color.

        Args:
            status: The worker status string.

        Returns:
            Formatted status with color markup.
        """
        if status == "assigned":
            return "[dim]Assigned[/dim]"
        elif status == "in-progress":
            return "[yellow]In Progress[/yellow]"
        elif status == "done":
            return "[green]Done[/green]"
        return status

    def _truncate(self, text: str, max_len: int) -> str:
        """Truncate text to max length with ellipsis.

        Args:
            text: Text to truncate.
            max_len: Maximum length.

        Returns:
            Truncated text.
        """
        if len(text) <= max_len:
            return text
        return text[: max_len - 3] + "..."

    @property
    def current_stats(self) -> Optional[TreeStats]:
        """Get the current stats."""
        return self._stats

    @property
    def current_workers(self) -> list[Worker]:
        """Get the current workers list."""
        return self._workers.copy()

    def get_worker_by_id(self, worker_id: int) -> Optional[Worker]:
        """Find a worker by ID.

        Args:
            worker_id: The worker ID to find.

        Returns:
            The Worker if found, None otherwise.
        """
        for worker in self._workers:
            if worker.id == worker_id:
                return worker
        return None
