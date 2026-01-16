"""New Project screen for Ralph TUI.

Wizard for creating new projects (greenfield or brownfield).
"""

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Static

from ralph.storage import create_project, create_empty_tree

if TYPE_CHECKING:
    from ralph.tui.app import RalphApp


class ProjectCreated(Message):
    """Message sent when a project is created."""
    def __init__(self, project_id: str) -> None:
        self.project_id = project_id
        super().__init__()


class ProjectTypeCard(Static):
    """A selectable project type card."""

    DEFAULT_CSS = """
    ProjectTypeCard {
        height: 7;
        padding: 1 2;
        margin: 1;
        border: solid $secondary;
        background: $surface;
    }

    ProjectTypeCard:hover {
        background: $surface-lighten-1;
        border: solid $primary-lighten-1;
    }

    ProjectTypeCard:focus {
        background: $surface-lighten-2;
        border: solid $primary;
    }

    ProjectTypeCard .card-title {
        text-style: bold;
        color: $primary;
    }

    ProjectTypeCard .card-desc {
        color: $text-muted;
        margin-top: 1;
    }
    """

    can_focus = True

    def __init__(self, title: str, description: str, project_type: str, **kwargs):
        super().__init__(**kwargs)
        self.title = title
        self.description = description
        self.project_type = project_type

    def compose(self) -> ComposeResult:
        yield Label(self.title, classes="card-title")
        yield Label(self.description, classes="card-desc")


class NewProjectScreen(Screen):
    """Screen for creating a new project."""

    CSS = """
    NewProjectScreen {
        background: $surface;
    }

    #new-project-container {
        width: 100%;
        height: 100%;
        padding: 2;
        align: center middle;
    }

    #new-project-box {
        width: 70;
        height: auto;
        border: solid $primary;
        padding: 2;
    }

    #new-project-title {
        text-style: bold;
        text-align: center;
        padding: 1;
        color: $primary;
    }

    #type-selection {
        margin: 2 0;
    }

    #name-input-section {
        display: none;
        margin: 2 0;
        padding: 1;
        border: solid $secondary;
    }

    #name-input-section.visible {
        display: block;
    }

    #path-display-section {
        display: none;
        margin: 2 0;
        padding: 1;
        border: solid $secondary;
    }

    #path-display-section.visible {
        display: block;
    }

    #button-row {
        margin-top: 2;
        align: center middle;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("enter", "confirm", "Confirm"),
    ]

    def __init__(self):
        super().__init__()
        self._project_type: Optional[str] = None
        self._selected_path: Optional[str] = None

    def compose(self) -> ComposeResult:
        yield Header()

        with Container(id="new-project-container"):
            with Vertical(id="new-project-box"):
                yield Label("Create New Project", id="new-project-title")

                # Step 1: Choose type
                with Vertical(id="type-selection"):
                    yield Label("Choose project type:")
                    yield ProjectTypeCard(
                        "Greenfield",
                        "Start fresh with a new project",
                        "greenfield",
                        id="greenfield-card",
                    )
                    yield ProjectTypeCard(
                        "Brownfield",
                        "Work with an existing codebase",
                        "brownfield",
                        id="brownfield-card",
                    )

                # Step 2a: Name input (for greenfield)
                with Vertical(id="name-input-section"):
                    yield Label("Project Name:")
                    yield Input(placeholder="my-awesome-project", id="project-name-input")
                    yield Label("(A new folder will be created)", classes="help-text")

                # Step 2b: Path display (for brownfield)
                with Vertical(id="path-display-section"):
                    yield Label("Project Name:")
                    yield Input(placeholder="my-project", id="brownfield-name-input")
                    yield Label("Selected Path:", classes="section-label")
                    yield Label("No folder selected", id="selected-path-label")
                    yield Button("Browse...", id="browse-btn")

                # Buttons
                with Horizontal(id="button-row"):
                    yield Button("Create Project", id="create-btn", variant="success", disabled=True)
                    yield Button("Cancel", id="cancel-btn")

        yield Footer()

    def on_mount(self) -> None:
        """Focus first card on mount."""
        self.query_one("#greenfield-card", ProjectTypeCard).focus()

    def on_project_type_card_focus(self, event) -> None:
        """Track which card is focused."""
        pass

    def _select_type(self, project_type: str) -> None:
        """Select a project type and show appropriate inputs."""
        self._project_type = project_type

        name_section = self.query_one("#name-input-section")
        path_section = self.query_one("#path-display-section")
        create_btn = self.query_one("#create-btn", Button)

        if project_type == "greenfield":
            name_section.add_class("visible")
            path_section.remove_class("visible")
            self.query_one("#project-name-input", Input).focus()
            create_btn.disabled = False
        else:  # brownfield
            name_section.remove_class("visible")
            path_section.add_class("visible")
            create_btn.disabled = self._selected_path is None

    def on_static_focus(self, event) -> None:
        """Handle card focus via enter key."""
        pass

    def on_key(self, event) -> None:
        """Handle key events."""
        if event.key == "enter":
            # Check if a card is focused
            greenfield = self.query_one("#greenfield-card", ProjectTypeCard)
            brownfield = self.query_one("#brownfield-card", ProjectTypeCard)

            if greenfield.has_focus:
                self._select_type("greenfield")
            elif brownfield.has_focus:
                self._select_type("brownfield")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "browse-btn":
            self._open_browser()
        elif event.button.id == "create-btn":
            self._create_project()
        elif event.button.id == "cancel-btn":
            self.action_cancel()

    def _open_browser(self) -> None:
        """Open the folder browser."""
        from ralph.tui.screens.folder_browser import FolderBrowserScreen

        def handle_folder_selection(selected_path: Optional[str]) -> None:
            if selected_path:
                self._selected_path = selected_path

                # Update display
                path_label = self.query_one("#selected-path-label", Label)
                path_label.update(selected_path)

                # Auto-fill name from folder
                folder_name = Path(selected_path).name
                name_input = self.query_one("#brownfield-name-input", Input)
                name_input.value = folder_name

                # Enable create button
                create_btn = self.query_one("#create-btn", Button)
                create_btn.disabled = False

        self.app.push_screen(FolderBrowserScreen(), handle_folder_selection)

    def _create_project(self) -> None:
        """Create the project."""
        if self._project_type == "greenfield":
            name_input = self.query_one("#project-name-input", Input)
            name = name_input.value.strip()
            if not name:
                self.notify("Please enter a project name", severity="warning")
                return

            # Create project in a new folder
            project_path = str(Path.cwd() / name)
            Path(project_path).mkdir(parents=True, exist_ok=True)

        else:  # brownfield
            name_input = self.query_one("#brownfield-name-input", Input)
            name = name_input.value.strip()
            if not name:
                name = Path(self._selected_path).name

            project_path = self._selected_path

        # Create project
        try:
            project = create_project(name=name, path=project_path)
            create_empty_tree(project.id, name)

            self.notify(f"Created project: {name}", severity="information")
            self.post_message(ProjectCreated(project.id))
            self.app.pop_screen()

        except Exception as e:
            self.notify(f"Failed to create project: {e}", severity="error")

    def action_cancel(self) -> None:
        """Cancel and go back."""
        self.app.pop_screen()

    def action_confirm(self) -> None:
        """Confirm current selection."""
        create_btn = self.query_one("#create-btn", Button)
        if not create_btn.disabled:
            self._create_project()


__all__ = ["NewProjectScreen", "ProjectCreated"]
