"""Main Ralph TUI Application.

The RalphApp class is the entry point for the terminal user interface.
It manages screens, keybindings, and coordinates between the UI and core logic.
"""

from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer

from ralph.models import TaskStatus, Project, AIConfig
from ralph.storage import list_projects, load_tree, save_tree, load_workers, get_project
from ralph.core import find_next_task, update_task_status, count_tasks, mark_task_done, mark_task_in_progress


class RalphApp(App):
    """Ralph Task Management TUI Application.

    A terminal interface for managing hierarchical task trees,
    tracking progress, and coordinating worker assignments.
    """

    TITLE = "Ralph - Task Manager"
    SUB_TITLE = "Hierarchical Task Management"

    CSS = """
    /* Global application styles */
    Screen {
        background: $surface;
    }

    /* Main layout containers */
    #main-container {
        layout: horizontal;
        height: 100%;
    }

    #left-panel {
        width: 50%;
        height: 100%;
        border-right: solid $primary;
        layout: vertical;
    }

    #right-panel {
        width: 50%;
        height: 100%;
        layout: vertical;
    }

    #tabbed-section {
        height: 60%;
        border-bottom: solid $primary;
    }

    #task-details {
        height: 40%;
    }

    /* Terminal widget styling */
    TerminalWidget {
        height: 100%;
        border: solid $secondary;
    }

    /* Tree view styling */
    TaskTreeWidget {
        height: 100%;
    }

    /* Task panel styling */
    TaskPanel {
        height: 100%;
        padding: 1;
    }

    /* Status panel styling */
    StatusPanel {
        height: 100%;
        padding: 1;
    }

    /* Footer styling */
    Footer {
        dock: bottom;
        height: 1;
        background: $primary;
    }

    /* TabbedContent styling */
    TabbedContent {
        height: 100%;
    }

    ContentSwitcher {
        height: 100%;
    }

    TabPane {
        height: 100%;
        padding: 0;
    }

    /* Chat widget in left panel */
    #left-tabs {
        height: 100%;
    }

    ChatWidget {
        height: 100%;
        border: none;
    }

    /* Project select screen */
    #project-list {
        height: 100%;
        padding: 1;
    }

    .project-item {
        padding: 1;
        margin: 1;
        border: solid $secondary;
    }

    .project-item:hover {
        background: $surface-lighten-1;
    }

    .project-item:focus {
        border: solid $primary;
        background: $surface-lighten-2;
    }

    /* Modal styling */
    #worker-modal {
        width: 60;
        height: 20;
        border: thick $primary;
        background: $surface;
        padding: 1;
    }

    /* Help modal */
    #help-modal {
        width: 70;
        height: 25;
        border: thick $primary;
        background: $surface;
        padding: 1;
    }

    /* Progress indicators */
    .progress-bar {
        height: 1;
        margin: 1 0;
    }

    /* Status colors */
    .status-pending {
        color: $text-muted;
    }

    .status-in-progress {
        color: $warning;
    }

    .status-done {
        color: $success;
    }

    .status-blocked {
        color: $error;
    }

    /* Section headers */
    .section-header {
        text-style: bold;
        padding: 0 1;
        background: $primary-darken-2;
    }
    """

    BINDINGS = [
        Binding("n", "next_task", "Next Task", show=True),
        Binding("d", "mark_done", "Done", show=True),
        Binding("v", "validate", "Validate", show=True),
        Binding("a", "assign_workers", "Assign", show=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("tab", "focus_next", "Focus", show=True),
        Binding("shift+tab", "focus_previous", "Focus Prev", show=False),
        Binding("question_mark", "show_help", "Help", show=True, key_display="?"),
        Binding("ctrl+p", "command_palette", "Commands", show=True),
        Binding("q", "quit", "Quit", show=True),
    ]

    def __init__(self, project_id: Optional[str] = None):
        """Initialize the Ralph TUI application.

        Args:
            project_id: Optional project ID to load on startup.
                       If None and multiple projects exist, shows project selection.
        """
        super().__init__()
        self._initial_project_id = project_id
        self._current_project: Optional[Project] = None
        self._selected_task_path: Optional[list[str]] = None
        self._ai_config: Optional[AIConfig] = None

    @property
    def current_project(self) -> Optional[Project]:
        """Get the currently loaded project."""
        return self._current_project

    @property
    def selected_task_path(self) -> Optional[list[str]]:
        """Get the currently selected task path."""
        return self._selected_task_path

    @selected_task_path.setter
    def selected_task_path(self, path: Optional[list[str]]) -> None:
        """Set the currently selected task path."""
        self._selected_task_path = path

    @property
    def ai_config(self) -> Optional[AIConfig]:
        """Get the current AI configuration."""
        return self._ai_config

    def on_mount(self) -> None:
        """Handle app mount - start with launcher."""
        from ralph.tui.screens.launcher import LauncherScreen
        self.push_screen(LauncherScreen())

    def on_project_opened(self, message) -> None:
        """Handle project selection from launcher."""
        from ralph.tui.screens.launcher import ProjectOpened
        if isinstance(message, ProjectOpened):
            if self.load_project(message.project_id):
                self.pop_screen()  # Remove launcher
                self._show_ai_config()
            else:
                self.notify(f"Failed to load project: {message.project_id}", severity="error")

    def _show_ai_config(self) -> None:
        """Show the AI configuration screen."""
        from ralph.tui.screens.ai_config import AIConfigScreen
        self.push_screen(AIConfigScreen())

    def _push_main_screen(self) -> None:
        """Push the main screen onto the stack."""
        from ralph.tui.screens.main import MainScreen
        self.push_screen(MainScreen())

    def _show_project_select(self, projects: list[Project]) -> None:
        """Show the project selection screen."""
        from ralph.tui.screens.project_select import ProjectSelectScreen
        self.push_screen(ProjectSelectScreen(projects))

    def load_project(self, project_id: str) -> bool:
        """Load a project by ID.

        Args:
            project_id: The ID of the project to load.

        Returns:
            True if the project was loaded successfully.
        """
        project = get_project(project_id)
        if project:
            self._current_project = project
            return True
        return False

    # =========================================================================
    # Actions
    # =========================================================================

    def action_next_task(self) -> None:
        """Mark the next pending task as in-progress."""
        if not self._current_project:
            self.notify("No project loaded", severity="warning")
            return

        tree = load_tree(self._current_project.id)
        if not tree:
            self.notify("No task tree found", severity="warning")
            return

        next_task = find_next_task(tree)
        if not next_task:
            self.notify("No pending tasks found", severity="info")
            return

        # Mark as in-progress
        updated_tree = mark_task_in_progress(tree, next_task.path)
        save_tree(self._current_project.id, updated_tree)

        # Update selection
        self._selected_task_path = next_task.path

        # Notify UI components
        self.notify(f"Started: {next_task.task.name}", severity="information")
        self._refresh_tree_widget()

    def action_mark_done(self) -> None:
        """Mark the currently selected task as done."""
        if not self._current_project:
            self.notify("No project loaded", severity="warning")
            return

        if not self._selected_task_path:
            self.notify("No task selected", severity="warning")
            return

        tree = load_tree(self._current_project.id)
        if not tree:
            self.notify("No task tree found", severity="warning")
            return

        # Mark as done
        updated_tree = mark_task_done(tree, self._selected_task_path)
        save_tree(self._current_project.id, updated_tree)

        task_name = self._selected_task_path[-1] if self._selected_task_path else "Task"
        self.notify(f"Completed: {task_name}", severity="information")

        # Clear selection and refresh
        self._selected_task_path = None
        self._refresh_tree_widget()

    def action_validate(self) -> None:
        """Run acceptance criteria in the terminal."""
        if not self._current_project:
            self.notify("No project loaded", severity="warning")
            return

        if not self._selected_task_path:
            self.notify("No task selected - select a task first", severity="warning")
            return

        tree = load_tree(self._current_project.id)
        if not tree:
            self.notify("No task tree found", severity="warning")
            return

        from ralph.core import find_task_by_path
        task = find_task_by_path(tree, self._selected_task_path)

        if not task:
            self.notify("Task not found", severity="error")
            return

        if not task.acceptance:
            self.notify("No acceptance criteria defined for this task", severity="info")
            return

        # Send validation commands to terminal
        self._run_in_terminal(task.acceptance)
        self.notify("Running acceptance tests...", severity="information")

    def action_assign_workers(self) -> None:
        """Show the worker assignment modal."""
        from ralph.tui.screens.main import WorkerModal
        self.push_screen(WorkerModal())

    def action_refresh(self) -> None:
        """Refresh the task tree display."""
        self._refresh_tree_widget()
        self.notify("Refreshed", severity="information")

    def action_show_help(self) -> None:
        """Show the help modal with keybinding reference."""
        from ralph.tui.screens.main import HelpModal
        self.push_screen(HelpModal())

    def action_focus_next(self) -> None:
        """Move focus to the next widget."""
        self.screen.focus_next()

    def action_focus_previous(self) -> None:
        """Move focus to the previous widget."""
        self.screen.focus_previous()

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _refresh_tree_widget(self) -> None:
        """Refresh the tree widget on the current screen."""
        try:
            from ralph.tui.widgets import TaskTreeWidget
            tree_widget = self.query_one(TaskTreeWidget)
            tree_widget.refresh_tree()
        except Exception:
            pass  # Tree widget might not be mounted yet

    def _run_in_terminal(self, commands: list[str]) -> None:
        """Run commands in the terminal widget."""
        try:
            from ralph.tui.widgets import TerminalWidget
            from textual.widgets import TabbedContent

            # Switch to terminal tab
            try:
                tabs = self.query_one("#left-tabs", TabbedContent)
                tabs.active = "terminal-tab"
            except Exception:
                pass

            # Write commands to terminal
            terminal = self.query_one(TerminalWidget)
            for cmd in commands:
                terminal.write(cmd + "\r")
        except Exception:
            self.notify("Terminal not available", severity="error")

    def get_project_stats(self) -> Optional[dict]:
        """Get statistics for the current project."""
        if not self._current_project:
            return None

        tree = load_tree(self._current_project.id)
        if not tree:
            return None

        stats = count_tasks(tree)
        return {
            "total": stats.total,
            "done": stats.done,
            "pending": stats.pending,
            "in_progress": stats.in_progress,
            "blocked": stats.blocked,
            "progress_percent": stats.progress_percent,
        }


# Export for easy importing
__all__ = ["RalphApp"]
