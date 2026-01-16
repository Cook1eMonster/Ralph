"""Main screen for Ralph TUI.

The MainScreen provides the primary interface for task management,
featuring a split layout with terminal, tree view, and task details.
"""

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.message import Message
from textual.screen import Screen, ModalScreen
from textual.widgets import (
    Footer,
    Header,
    Static,
    TabbedContent,
    TabPane,
    Label,
    Button,
    Input,
)

from ralph.tui.widgets import TaskTreeWidget, TaskPanel, StatusPanel, TerminalWidget
from ralph.storage import load_tree, load_workers
from ralph.core import count_tasks, find_n_tasks

if TYPE_CHECKING:
    from ralph.tui.app import RalphApp


class TaskSelected(Message):
    """Message sent when a task is selected in the tree."""

    def __init__(self, path: list[str]) -> None:
        """Initialize TaskSelected message.

        Args:
            path: The path to the selected task in the tree.
        """
        self.path = path
        super().__init__()


class MainScreen(Screen):
    """Main application screen with split layout.

    Layout:
    +-----------------------+-------------------------+
    | Terminal (50%)        | Tree View | Status      |
    |                       |--------------------------|
    |                       | Task Details             |
    +-----------------------+-------------------------+
    | Footer with keybindings                         |
    +------------------------------------------------+
    """

    BINDINGS = [
        ("escape", "app.focus('terminal')", "Focus Terminal"),
    ]

    def compose(self) -> ComposeResult:
        """Compose the main screen layout."""
        yield Header()

        with Horizontal(id="main-container"):
            # Left panel - Terminal (type 'claude' to start Claude Code)
            with Container(id="left-panel"):
                yield TerminalWidget(id="terminal")

            # Right panel - Tree and Details
            with Vertical(id="right-panel"):
                # Tabbed section for Tree/Status
                with TabbedContent(id="tabbed-section"):
                    with TabPane("Tree", id="tree-tab"):
                        yield TaskTreeWidget(id="task-tree")
                    with TabPane("Status", id="status-tab"):
                        yield StatusPanel(id="status-panel")

                # Task details section
                with Container(id="task-details"):
                    yield TaskPanel(id="task-panel")

        yield Footer()

    def on_mount(self) -> None:
        """Handle screen mount - initialize widgets with data."""
        self._refresh_data()

    def _refresh_data(self) -> None:
        """Refresh all widgets with current project data."""
        app: "RalphApp" = self.app  # type: ignore

        if not app.current_project:
            return

        project_id = app.current_project.id

        # Load tree data
        tree = load_tree(project_id)
        if tree:
            # Update tree widget
            try:
                tree_widget = self.query_one("#task-tree", TaskTreeWidget)
                tree_widget.load_tree(tree)
            except Exception:
                pass

            # Update status panel
            try:
                status_panel = self.query_one("#status-panel", StatusPanel)
                stats = count_tasks(tree)
                status_panel.update_stats(stats)
            except Exception:
                pass

        # Load workers
        worker_list = load_workers(project_id)
        try:
            status_panel = self.query_one("#status-panel", StatusPanel)
            status_panel.update_workers(worker_list.workers)
        except Exception:
            pass

    def on_task_selected(self, event: TaskSelected) -> None:
        """Handle task selection from the tree widget."""
        app: "RalphApp" = self.app  # type: ignore

        # Update app's selected task
        app.selected_task_path = event.path

        # Update task panel
        if app.current_project:
            tree = load_tree(app.current_project.id)
            if tree:
                try:
                    from ralph.core import find_task_by_path, estimate_tokens
                    task = find_task_by_path(tree, event.path)
                    if task:
                        task_panel = self.query_one("#task-panel", TaskPanel)
                        estimate = estimate_tokens(task, "")  # No context available here
                        task_panel.update_task(task, event.path, estimate)
                except Exception:
                    pass


class WorkerModal(ModalScreen):
    """Modal dialog for assigning workers to tasks."""

    BINDINGS = [
        ("escape", "dismiss", "Close"),
    ]

    CSS = """
    WorkerModal {
        align: center middle;
    }

    #worker-modal {
        width: 60;
        height: auto;
        max-height: 25;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    #worker-modal-title {
        text-style: bold;
        text-align: center;
        margin-bottom: 1;
    }

    #worker-count-input {
        margin: 1 0;
    }

    #worker-buttons {
        layout: horizontal;
        margin-top: 1;
        align: center middle;
    }

    #worker-buttons Button {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        """Compose the worker assignment modal."""
        with Container(id="worker-modal"):
            yield Label("Assign Workers", id="worker-modal-title")
            yield Label("Number of parallel workers to assign:")
            yield Input(
                placeholder="Enter number (1-8)",
                id="worker-count-input",
                type="integer",
            )
            with Horizontal(id="worker-buttons"):
                yield Button("Assign", variant="primary", id="btn-assign")
                yield Button("Cancel", variant="default", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-cancel":
            self.dismiss()
        elif event.button.id == "btn-assign":
            self._assign_workers()

    def _assign_workers(self) -> None:
        """Assign workers based on input."""
        from ralph.tui.app import RalphApp
        from ralph.storage import save_workers
        from ralph.core import create_worker
        from ralph.models import WorkerList

        app: RalphApp = self.app  # type: ignore

        if not app.current_project:
            app.notify("No project loaded", severity="warning")
            self.dismiss()
            return

        try:
            input_widget = self.query_one("#worker-count-input", Input)
            count = int(input_widget.value)
            if count < 1 or count > 8:
                app.notify("Please enter a number between 1 and 8", severity="warning")
                return
        except (ValueError, TypeError):
            app.notify("Please enter a valid number", severity="warning")
            return

        tree = load_tree(app.current_project.id)
        if not tree:
            app.notify("No task tree found", severity="warning")
            self.dismiss()
            return

        # Find available tasks
        tasks = find_n_tasks(tree, count)
        if not tasks:
            app.notify("No pending tasks available", severity="information")
            self.dismiss()
            return

        # Create workers
        workers = []
        for i, task_with_path in enumerate(tasks, start=1):
            worker = create_worker(task_with_path.task, task_with_path.path, i)
            workers.append(worker)

        # Save workers
        worker_list = WorkerList(workers=workers)
        save_workers(app.current_project.id, worker_list)

        app.notify(f"Assigned {len(workers)} workers", severity="information")
        self.dismiss()


class HelpModal(ModalScreen):
    """Modal dialog showing keybinding help."""

    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("question_mark", "dismiss", "Close"),
    ]

    CSS = """
    HelpModal {
        align: center middle;
    }

    #help-modal {
        width: 70;
        height: auto;
        max-height: 30;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    #help-title {
        text-style: bold;
        text-align: center;
        margin-bottom: 1;
        color: $primary;
    }

    .help-section {
        margin: 1 0;
    }

    .help-section-title {
        text-style: bold;
        color: $secondary;
    }

    .help-row {
        layout: horizontal;
        height: 1;
    }

    .help-key {
        width: 15;
        color: $warning;
    }

    .help-desc {
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        """Compose the help modal content."""
        with Container(id="help-modal"):
            yield Label("Ralph TUI - Keyboard Shortcuts", id="help-title")

            yield Label("Task Management", classes="help-section-title")
            yield self._help_row("n", "Start next pending task")
            yield self._help_row("d", "Mark selected task as done")
            yield self._help_row("v", "Run acceptance criteria")
            yield self._help_row("a", "Assign parallel workers")
            yield self._help_row("r", "Refresh tree view")

            yield Label("Navigation", classes="help-section-title")
            yield self._help_row("Tab", "Move focus to next widget")
            yield self._help_row("Shift+Tab", "Move focus to previous widget")
            yield self._help_row("Up/Down", "Navigate tree/lists")
            yield self._help_row("Enter", "Select/expand item")

            yield Label("Application", classes="help-section-title")
            yield self._help_row("Ctrl+P", "Open command palette")
            yield self._help_row("?", "Show this help")
            yield self._help_row("q", "Quit application")
            yield self._help_row("Escape", "Close modal/focus terminal")

            yield Label("")
            yield Label("Press Escape or ? to close", id="help-footer")

    def _help_row(self, key: str, description: str) -> Horizontal:
        """Create a help row with key and description."""
        return Horizontal(
            Label(f"  {key}", classes="help-key"),
            Label(description, classes="help-desc"),
            classes="help-row",
        )


__all__ = ["MainScreen", "TaskSelected", "WorkerModal", "HelpModal"]
