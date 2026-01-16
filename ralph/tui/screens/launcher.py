"""Simple launcher screen for Ralph TUI.

Provides a radio button menu for intuitive project selection.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    RadioButton,
    RadioSet,
    Static,
)

from ralph.models import Project
from ralph.storage import list_projects, load_tree, create_project, create_empty_tree
from ralph.core import count_tasks

if TYPE_CHECKING:
    from ralph.tui.app import RalphApp


class ProjectOpened(Message):
    """Message sent when a project is selected to open."""
    def __init__(self, project_id: str) -> None:
        self.project_id = project_id
        super().__init__()


class LauncherScreen(Screen):
    """Radio button menu for project selection."""

    CSS = """
    LauncherScreen {
        background: $surface;
    }

    #launcher-container {
        width: 100%;
        height: 100%;
        padding: 1 2;
    }

    #title {
        text-align: center;
        text-style: bold;
        color: $primary;
        padding: 1;
        width: 100%;
    }

    #subtitle {
        text-align: center;
        color: $text-muted;
        width: 100%;
        margin-bottom: 1;
    }

    #project-section {
        height: auto;
        max-height: 70%;
        border: solid $secondary;
        padding: 1;
        margin: 1 0;
    }

    #project-radio-set {
        width: 100%;
    }

    RadioButton {
        padding: 0 1;
        margin: 0;
    }

    RadioButton:focus {
        background: $surface-lighten-1;
    }

    .project-info {
        color: $text-muted;
        padding-left: 4;
        margin-bottom: 1;
    }

    #button-bar {
        height: auto;
        align: center middle;
        padding: 1;
        margin: 1 0;
    }

    #button-bar Button {
        margin: 0 1;
    }

    #new-project-section {
        display: none;
        border: solid $success;
        padding: 1;
        margin: 1 0;
    }

    #new-project-section.visible {
        display: block;
    }

    #type-selection {
        margin: 1 0;
    }

    #path-section {
        display: none;
        margin: 1 0;
    }

    #path-section.visible {
        display: block;
    }

    #name-section {
        display: none;
        margin: 1 0;
    }

    #name-section.visible {
        display: block;
    }

    .section-label {
        margin-bottom: 0;
        color: $text;
    }

    .no-projects {
        color: $text-muted;
        text-style: italic;
        padding: 2;
        text-align: center;
    }
    """

    BINDINGS = [
        ("enter", "open_selected", "Open"),
        ("n", "new_project", "New"),
        ("d", "delete_selected", "Delete"),
        ("escape", "cancel", "Cancel"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self):
        super().__init__()
        self._projects: list[Project] = []
        self._creating_new = False
        self._new_project_type: Optional[str] = None
        self._new_project_path: Optional[str] = None

    def compose(self) -> ComposeResult:
        yield Header()

        with Container(id="launcher-container"):
            yield Label("Ralph Project Manager", id="title")
            yield Label("Select a project or create a new one", id="subtitle")

            # Project selection section
            with VerticalScroll(id="project-section"):
                yield RadioSet(id="project-radio-set")

            # Action buttons
            with Horizontal(id="button-bar"):
                yield Button("Open", id="open-btn", variant="primary")
                yield Button("New", id="new-btn", variant="success")
                yield Button("Delete", id="delete-btn", variant="error")
                yield Button("Quit", id="quit-btn")

            # New project form (hidden by default)
            with Vertical(id="new-project-section"):
                yield Label("Create New Project", classes="section-label")

                with Vertical(id="type-selection"):
                    yield Label("Project Type:")
                    with RadioSet(id="type-radio-set"):
                        yield RadioButton("Greenfield - Start fresh with a new project", id="greenfield-radio")
                        yield RadioButton("Brownfield - Work with existing codebase", id="brownfield-radio")

                with Vertical(id="path-section"):
                    yield Label("Project Path:", classes="section-label")
                    yield Input(placeholder="Enter or paste the folder path...", id="path-input")

                with Vertical(id="name-section"):
                    yield Label("Project Name:", classes="section-label")
                    yield Input(placeholder="Enter project name (or leave blank for folder name)", id="name-input")

                with Horizontal(id="new-button-bar"):
                    yield Button("Create", id="create-btn", variant="success")
                    yield Button("Cancel", id="cancel-new-btn")

        yield Footer()

    def on_mount(self) -> None:
        """Load projects and display them."""
        self._load_projects()

    def _load_projects(self) -> None:
        """Load and display projects."""
        try:
            from ralph.storage import get_projects_by_recent
            self._projects = get_projects_by_recent()
        except ImportError:
            self._projects = list_projects()

        self._update_project_list()

    def _update_project_list(self) -> None:
        """Update the radio button list of projects."""
        radio_set = self.query_one("#project-radio-set", RadioSet)

        # Clear all existing children
        for child in list(radio_set.children):
            child.remove()

        if not self._projects:
            radio_set.mount(Static("No projects yet. Click 'New' to create one.", classes="no-projects"))
            return

        # Add radio buttons for each project
        for project in self._projects[:9]:
            # Get progress info
            try:
                tree = load_tree(project.id)
                if tree:
                    stats = count_tasks(tree)
                    progress = f"{stats.done}/{stats.total} tasks ({stats.progress_percent:.0f}%)"
                else:
                    progress = "No tasks yet"
            except Exception:
                progress = "Error loading"

            # Create radio button with project info
            label = f"{project.name}  ({progress})\n      {project.path}"
            radio_set.mount(RadioButton(label, id=f"project-{project.id}"))

        # Focus the radio set (defer to avoid issues during recomposition)
        self.call_later(radio_set.focus)

    def _get_selected_project(self) -> Optional[Project]:
        """Get the currently selected project."""
        radio_set = self.query_one("#project-radio-set", RadioSet)
        if radio_set.pressed_button is None:
            return None

        button_id = radio_set.pressed_button.id
        if button_id and button_id.startswith("project-"):
            project_id = button_id[8:]  # Remove "project-" prefix
            for project in self._projects:
                if project.id == project_id:
                    return project
        return None

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks."""
        button_id = event.button.id

        if button_id == "open-btn":
            self.action_open_selected()
        elif button_id == "new-btn":
            self.action_new_project()
        elif button_id == "delete-btn":
            self.action_delete_selected()
        elif button_id == "quit-btn":
            self.action_quit()
        elif button_id == "create-btn":
            self._create_project()
        elif button_id == "cancel-new-btn":
            self._hide_new_form()

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        """Handle radio selection changes."""
        # If in type selection for new project
        if event.radio_set.id == "type-radio-set":
            if event.pressed.id == "greenfield-radio":
                self._new_project_type = "greenfield"
            elif event.pressed.id == "brownfield-radio":
                self._new_project_type = "brownfield"

            # Show path section
            path_section = self.query_one("#path-section")
            path_section.add_class("visible")
            self.query_one("#path-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission."""
        if event.input.id == "path-input":
            self._validate_path(event.value.strip())
        elif event.input.id == "name-input":
            self._create_project()

    def _validate_path(self, path_str: str) -> None:
        """Validate the entered path and proceed."""
        if not path_str:
            self.notify("Please enter a path", severity="warning")
            return

        path = Path(path_str)

        if self._new_project_type == "brownfield":
            if not path.exists():
                self.notify(f"Path does not exist: {path_str}", severity="error")
                return
            if not path.is_dir():
                self.notify("Path must be a directory", severity="error")
                return

        self._new_project_path = str(path.absolute())

        # Show name section with default
        name_section = self.query_one("#name-section")
        name_section.add_class("visible")

        name_input = self.query_one("#name-input", Input)
        name_input.placeholder = f"Project name (default: {path.name})"
        name_input.focus()

    def _create_project(self) -> None:
        """Create the new project."""
        if not self._new_project_path:
            self.notify("Please enter a path first", severity="warning")
            return

        path = Path(self._new_project_path)
        name_input = self.query_one("#name-input", Input)
        name = name_input.value.strip() if name_input.value.strip() else path.name

        try:
            # Create folder for greenfield
            if self._new_project_type == "greenfield":
                path.mkdir(parents=True, exist_ok=True)

            # Create project
            project = create_project(name=name, path=str(path))
            create_empty_tree(project.id, name)

            self.notify(f"Created: {name}", severity="information")

            # Hide form and reload
            self._hide_new_form()
            self._load_projects()

            # Open the new project
            self._open_project(project)

        except Exception as e:
            self.notify(f"Failed to create project: {e}", severity="error")

    def _open_project(self, project: Project) -> None:
        """Open a project."""
        try:
            from ralph.storage import update_recent
            update_recent(project.id)
        except ImportError:
            pass

        self.post_message(ProjectOpened(project.id))

    def _show_new_form(self) -> None:
        """Show the new project form."""
        self._creating_new = True
        self._new_project_type = None
        self._new_project_path = None

        # Reset and show form
        self.query_one("#path-section").remove_class("visible")
        self.query_one("#name-section").remove_class("visible")
        self.query_one("#path-input", Input).value = ""
        self.query_one("#name-input", Input).value = ""

        new_section = self.query_one("#new-project-section")
        new_section.add_class("visible")

        # Focus the type selection
        self.query_one("#type-radio-set", RadioSet).focus()

    def _hide_new_form(self) -> None:
        """Hide the new project form."""
        self._creating_new = False
        self._new_project_type = None
        self._new_project_path = None

        new_section = self.query_one("#new-project-section")
        new_section.remove_class("visible")

        self.query_one("#path-section").remove_class("visible")
        self.query_one("#name-section").remove_class("visible")

        # Re-focus project list
        self.query_one("#project-radio-set", RadioSet).focus()

    # Actions

    def action_open_selected(self) -> None:
        """Open the selected project."""
        project = self._get_selected_project()
        if project:
            self._open_project(project)
        else:
            self.notify("Select a project first", severity="warning")

    def action_new_project(self) -> None:
        """Start new project creation."""
        self._show_new_form()

    def action_delete_selected(self) -> None:
        """Delete the selected project."""
        project = self._get_selected_project()
        if not project:
            self.notify("Select a project first", severity="warning")
            return

        from ralph.storage import delete_project
        if delete_project(project.id):
            self.notify(f"Deleted: {project.name}", severity="information")
            self._load_projects()
        else:
            self.notify("Failed to delete project", severity="error")

    def action_cancel(self) -> None:
        """Cancel current operation."""
        if self._creating_new:
            self._hide_new_form()
        else:
            self.action_quit()

    def action_quit(self) -> None:
        """Quit the app."""
        self.app.exit()


__all__ = ["LauncherScreen", "ProjectOpened"]
