"""Project selection screen for Ralph TUI.

Displayed when multiple projects exist and no specific project is specified.
Allows users to choose which project to work on.
"""

from typing import TYPE_CHECKING, Optional

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Footer, Header, Label, ListItem, ListView, Static

from ralph.models import Project, TreeStats
from ralph.storage import delete_project, load_tree
from ralph.core import count_tasks

if TYPE_CHECKING:
    from ralph.tui.app import RalphApp


class ProjectSelected(Message):
    """Message sent when a project is selected."""

    def __init__(self, project_id: str) -> None:
        """Initialize ProjectSelected message.

        Args:
            project_id: The ID of the selected project.
        """
        self.project_id = project_id
        super().__init__()


class ConfirmDeleteModal(ModalScreen):
    """Modal dialog to confirm project deletion."""

    CSS = """
    ConfirmDeleteModal {
        align: center middle;
    }

    #confirm-dialog {
        width: 50;
        height: auto;
        border: thick $error;
        background: $surface;
        padding: 1 2;
    }

    #confirm-title {
        text-style: bold;
        color: $error;
        text-align: center;
        padding: 1;
    }

    #confirm-message {
        text-align: center;
        padding: 1;
    }

    #confirm-project-name {
        text-style: bold;
        color: $primary;
        text-align: center;
        padding: 1;
    }

    #confirm-buttons {
        align: center middle;
        height: 3;
        margin-top: 1;
    }

    #delete-btn {
        margin-right: 2;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("enter", "confirm_delete", "Delete"),
    ]

    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Label("Delete Project?", id="confirm-title")
            yield Label("Are you sure you want to delete this project?", id="confirm-message")
            yield Label(self.project.name, id="confirm-project-name")
            yield Label(f"Path: {self.project.path}", classes="text-muted")
            with Horizontal(id="confirm-buttons"):
                yield Button("Delete", id="delete-btn", variant="error")
                yield Button("Cancel", id="cancel-btn", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "delete-btn":
            self.action_confirm_delete()
        elif event.button.id == "cancel-btn":
            self.action_cancel()

    def action_confirm_delete(self) -> None:
        """Confirm deletion and close modal."""
        self.dismiss(True)

    def action_cancel(self) -> None:
        """Cancel and close modal."""
        self.dismiss(False)


class CreateProjectItem(Static):
    """Create new project option."""

    DEFAULT_CSS = """
    CreateProjectItem {
        height: auto;
        padding: 1 2;
        margin: 0 1 1 1;
        border: dashed $success;
        background: $surface;
    }

    CreateProjectItem:hover {
        background: $success-darken-3;
        border: dashed $success-lighten-1;
    }

    CreateProjectItem:focus {
        background: $success-darken-2;
        border: solid $success;
    }

    CreateProjectItem .create-icon {
        color: $success;
        text-style: bold;
    }

    CreateProjectItem .create-text {
        color: $success;
        margin-left: 1;
    }
    """

    can_focus = True

    def compose(self) -> ComposeResult:
        yield Label("+ Create New Project", classes="create-text")


class ProjectItem(Static):
    """A selectable project item in the list."""

    DEFAULT_CSS = """
    ProjectItem {
        height: auto;
        padding: 1 2;
        margin: 0 1 1 1;
        border: solid $secondary;
        background: $surface;
    }

    ProjectItem:hover {
        background: $surface-lighten-1;
        border: solid $primary-lighten-1;
    }

    ProjectItem:focus {
        background: $surface-lighten-2;
        border: solid $primary;
    }

    ProjectItem .project-name {
        text-style: bold;
        color: $primary;
    }

    ProjectItem .project-path {
        color: $text-muted;
        margin-left: 2;
    }

    ProjectItem .project-stats {
        margin-top: 1;
        color: $text;
    }

    ProjectItem .progress-text {
        color: $success;
    }

    ProjectItem .no-tree {
        color: $warning;
        text-style: italic;
    }
    """

    can_focus = True

    def __init__(
        self,
        project: Project,
        stats: Optional[TreeStats] = None,
        **kwargs,
    ) -> None:
        """Initialize a project item.

        Args:
            project: The project to display.
            stats: Optional tree statistics for progress display.
        """
        super().__init__(**kwargs)
        self.project = project
        self.stats = stats

    def compose(self) -> ComposeResult:
        """Compose the project item content."""
        yield Label(self.project.name, classes="project-name")
        yield Label(self.project.path, classes="project-path")

        if self.stats:
            progress = self.stats.progress_percent
            total = self.stats.total
            done = self.stats.done
            yield Label(
                f"Progress: {done}/{total} tasks ({progress:.1f}%)",
                classes="project-stats progress-text",
            )
        else:
            yield Label("No task tree configured", classes="project-stats no-tree")


class ProjectSelectScreen(Screen):
    """Screen for selecting a project from available projects.

    Layout:
    +------------------------------------------+
    | Header                                    |
    +------------------------------------------+
    | Select a Project                          |
    |                                           |
    | +--------------------------------------+  |
    | | Project 1                            |  |
    | | /path/to/project                     |  |
    | | Progress: 5/10 tasks (50%)          |  |
    | +--------------------------------------+  |
    |                                           |
    | +--------------------------------------+  |
    | | Project 2                            |  |
    | | /path/to/another                     |  |
    | | No task tree configured              |  |
    | +--------------------------------------+  |
    |                                           |
    +------------------------------------------+
    | Footer                                    |
    +------------------------------------------+
    """

    BINDINGS = [
        ("enter", "select_project", "Select"),
        ("d", "delete_project", "Delete"),
        ("delete", "delete_project", "Delete"),
        ("escape", "go_back", "Back"),
        ("up", "cursor_up", "Up"),
        ("down", "cursor_down", "Down"),
        ("q", "quit", "Quit"),
    ]

    CSS = """
    ProjectSelectScreen {
        background: $surface;
    }

    #project-select-container {
        width: 100%;
        height: 100%;
        padding: 1 2;
    }

    #project-select-title {
        text-style: bold;
        text-align: center;
        padding: 1;
        color: $primary;
        width: 100%;
    }

    #project-select-subtitle {
        text-align: center;
        color: $text-muted;
        margin-bottom: 2;
        width: 100%;
    }

    #project-list-container {
        height: 100%;
        width: 100%;
    }
    """

    def __init__(self, projects: list[Project]) -> None:
        """Initialize the project selection screen.

        Args:
            projects: List of available projects to choose from.
        """
        super().__init__()
        self.projects = projects
        self._project_items: list[ProjectItem] = []
        self._create_item: Optional[CreateProjectItem] = None
        self._selected_index = 0

    def compose(self) -> ComposeResult:
        """Compose the project selection screen."""
        yield Header()

        with Container(id="project-select-container"):
            yield Label("Select a Project", id="project-select-title")
            yield Label(
                f"{len(self.projects)} projects. Enter=Open, D=Delete, Esc=Back",
                id="project-select-subtitle",
            )

            with VerticalScroll(id="project-list-container"):
                # Add create option at the top
                create_item = CreateProjectItem(id="create-project")
                self._create_item = create_item
                yield create_item

                for project in self.projects:
                    # Load stats if tree exists
                    stats = None
                    tree = load_tree(project.id)
                    if tree:
                        stats = count_tasks(tree)

                    item = ProjectItem(
                        project,
                        stats=stats,
                        id=f"project-{project.id}",
                    )
                    self._project_items.append(item)
                    yield item

        yield Footer()

    def on_mount(self) -> None:
        """Handle mount - focus the create item first."""
        if self._create_item:
            self._create_item.focus()

    def _get_all_items(self) -> list:
        """Get all focusable items (create item + project items)."""
        items = []
        if self._create_item:
            items.append(self._create_item)
        items.extend(self._project_items)
        return items

    def action_cursor_up(self) -> None:
        """Move selection up."""
        all_items = self._get_all_items()
        if self._selected_index > 0:
            self._selected_index -= 1
            all_items[self._selected_index].focus()

    def action_cursor_down(self) -> None:
        """Move selection down."""
        all_items = self._get_all_items()
        if self._selected_index < len(all_items) - 1:
            self._selected_index += 1
            all_items[self._selected_index].focus()

    def action_select_project(self) -> None:
        """Select the currently focused project."""
        # Check if create item is focused
        if self._create_item and self._create_item.has_focus:
            self._open_create_project()
            return

        if not self._project_items:
            return

        # Find which project item is focused
        for i, item in enumerate(self._project_items):
            if item.has_focus:
                self._select_project(item.project)
                return

        # Fallback to selected index (account for create item at index 0)
        all_items = self._get_all_items()
        if 0 <= self._selected_index < len(all_items):
            selected = all_items[self._selected_index]
            if isinstance(selected, CreateProjectItem):
                self._open_create_project()
            elif isinstance(selected, ProjectItem):
                self._select_project(selected.project)

    def _select_project(self, project: Project) -> None:
        """Handle project selection.

        Args:
            project: The selected project.
        """
        app: "RalphApp" = self.app  # type: ignore

        # Load the project
        if app.load_project(project.id):
            # Pop this screen and push main screen
            self.app.pop_screen()

            from ralph.tui.screens.main import MainScreen
            self.app.push_screen(MainScreen())
        else:
            app.notify(f"Failed to load project: {project.name}", severity="error")

    def _open_create_project(self) -> None:
        """Open the create project screen."""
        from ralph.tui.screens.new_project import NewProjectScreen
        self.app.push_screen(NewProjectScreen())

    def on_project_created(self, message) -> None:
        """Handle project creation."""
        from ralph.tui.screens.new_project import ProjectCreated
        if isinstance(message, ProjectCreated):
            app: "RalphApp" = self.app  # type: ignore
            if app.load_project(message.project_id):
                self.app.pop_screen()
                from ralph.tui.screens.main import MainScreen
                self.app.push_screen(MainScreen())

    def action_quit(self) -> None:
        """Quit the application."""
        self.app.exit()

    def action_go_back(self) -> None:
        """Go back to AI config screen."""
        self.app.pop_screen()
        from ralph.tui.screens.ai_config import AIConfigScreen
        self.app.push_screen(AIConfigScreen())

    def action_delete_project(self) -> None:
        """Delete the currently focused project."""
        # Find the focused project item
        focused_project = None
        for item in self._project_items:
            if item.has_focus:
                focused_project = item.project
                break

        if not focused_project:
            self.notify("Select a project to delete", severity="warning")
            return

        # Show confirmation modal
        def handle_delete_result(confirmed: bool) -> None:
            if confirmed and focused_project:
                if delete_project(focused_project.id):
                    self.notify(f"Deleted: {focused_project.name}", severity="information")
                    self._refresh_projects()
                else:
                    self.notify(f"Failed to delete: {focused_project.name}", severity="error")

        self.app.push_screen(ConfirmDeleteModal(focused_project), handle_delete_result)

    def _refresh_projects(self) -> None:
        """Refresh the project list after deletion."""
        from ralph.storage import list_projects

        # Reload projects
        self.projects = list_projects()

        # Clear and rebuild the list
        container = self.query_one("#project-list-container", VerticalScroll)
        container.remove_children()
        self._project_items.clear()
        self._selected_index = 0

        # Re-add create item
        create_item = CreateProjectItem(id="create-project-new")
        self._create_item = create_item
        container.mount(create_item)

        # Re-add project items
        for project in self.projects:
            stats = None
            tree = load_tree(project.id)
            if tree:
                stats = count_tasks(tree)

            item = ProjectItem(
                project,
                stats=stats,
                id=f"project-{project.id}",
            )
            self._project_items.append(item)
            container.mount(item)

        # Update subtitle
        subtitle = self.query_one("#project-select-subtitle", Label)
        subtitle.update(f"{len(self.projects)} projects. Enter=Open, D=Delete, Esc=Back")

        # Focus create item
        if self._create_item:
            self._create_item.focus()

    def on_click(self, event) -> None:
        """Handle click events on project items - single click to focus."""
        # Check if create item was clicked
        if self._create_item and self._create_item.region.contains(event.x, event.y):
            self._create_item.focus()
            self._selected_index = 0
            return

        # Find if a ProjectItem was clicked
        for i, item in enumerate(self._project_items):
            if item.region.contains(event.x, event.y):
                item.focus()
                self._selected_index = i + 1  # +1 for create item
                break


__all__ = ["ProjectSelectScreen", "ProjectSelected", "ProjectItem", "CreateProjectItem", "ConfirmDeleteModal"]
