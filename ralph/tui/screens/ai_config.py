"""AI Configuration screen for Ralph TUI.

Allows users to configure which AI provider to use for different tasks.
"""

from typing import TYPE_CHECKING, Optional

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, RadioButton, RadioSet, Select

from ralph.models import AIConfig, AIProvider

if TYPE_CHECKING:
    from ralph.tui.app import RalphApp


def check_ollama_status() -> dict:
    """Check Ollama availability and model status."""
    result = {
        "available": False,
        "models": [],
        "llm_models": [],  # LLMs for planning/coding
        "embed_models": [],  # Embedding models
        "missing_models": [],
        "error": None,
    }

    # We need one LLM and one embedding model
    required_llm = "qwen2.5-coder"  # Single LLM for both planning and coding
    required_embed = "nomic-embed-text"

    try:
        import ollama
        models_response = ollama.list()

        # Handle both old dict format and new ListResponse object
        if hasattr(models_response, 'models'):
            installed_full = [m.model for m in models_response.models if hasattr(m, 'model')]
        else:
            installed_full = [m.get("name", "") for m in models_response.get("models", [])]

        result["available"] = True
        result["models"] = installed_full

        # Categorize models
        embed_keywords = ["embed", "nomic", "bge", "e5"]
        for model in installed_full:
            model_lower = model.lower()
            if any(kw in model_lower for kw in embed_keywords):
                result["embed_models"].append(model)
            else:
                result["llm_models"].append(model)

        # Check for required models
        installed_base = [name.split(":")[0] for name in installed_full]
        if required_llm not in installed_base:
            result["missing_models"].append(required_llm)
        if required_embed not in installed_base:
            result["missing_models"].append(required_embed)

    except ImportError:
        result["error"] = "ollama package not installed"
    except Exception as e:
        result["error"] = str(e)

    return result


class AIConfigComplete(Message):
    """Message sent when AI configuration is complete."""
    def __init__(self, config: AIConfig) -> None:
        self.config = config
        super().__init__()


class AIConfigScreen(Screen):
    """Screen for configuring AI providers."""

    CSS = """
    AIConfigScreen {
        background: $surface;
    }

    #ai-config-container {
        width: 100%;
        height: 1fr;
        padding: 1 2;
        align: center top;
    }

    #ai-config-box {
        width: 100%;
        max-width: 100;
        height: auto;
        border: solid $primary;
        padding: 1 2;
    }

    #ai-config-title {
        text-style: bold;
        text-align: center;
        color: $primary;
    }

    #ai-config-subtitle {
        text-align: center;
        color: $text-muted;
    }

    #columns-container {
        width: 100%;
        height: auto;
    }

    #left-column {
        width: 1fr;
        padding: 0 1 0 0;
    }

    #right-column {
        width: 1fr;
        padding: 0 0 0 1;
    }

    #ollama-status {
        padding: 0 1;
        margin: 0 0 1 0;
        border: solid $secondary;
        background: $surface-darken-1;
        height: auto;
    }

    #ollama-status.status-ok {
        border: solid $success;
    }

    #ollama-status.status-warning {
        border: solid $warning;
    }

    #ollama-status.status-error {
        border: solid $error;
    }

    .status-title {
        text-style: bold;
    }

    .status-ok {
        color: $success;
    }

    .status-warning {
        color: $warning;
    }

    .status-error {
        color: $error;
    }

    #llm-select-section {
        padding: 0 1;
        border: solid $primary;
        background: $surface-darken-1;
        height: auto;
    }

    #llm-select {
        width: 100%;
    }

    #presets-container {
        width: 100%;
        height: 3;
        align: center middle;
    }

    .preset-btn {
        margin: 0 1;
    }

    .config-section {
        padding: 0 1;
        border: solid $secondary;
        height: auto;
    }

    .config-section RadioSet {
        height: auto;
    }

    .section-label {
        text-style: bold;
    }

    #continue-container {
        width: 100%;
        height: auto;
        align: center middle;
        dock: bottom;
        padding: 1;
    }

    #continue-btn {
        width: 30;
    }
    """

    BINDINGS = [
        ("escape", "go_back", "Back"),
        ("enter", "continue", "Continue"),
    ]

    def __init__(self):
        super().__init__()
        self._config = AIConfig()
        self._ollama_status: dict = {}

    def compose(self) -> ComposeResult:
        yield Header()

        with VerticalScroll(id="ai-config-container"):
            with Vertical(id="ai-config-box"):
                yield Label("AI Configuration", id="ai-config-title")
                yield Label("Choose which AI to use for each task type", id="ai-config-subtitle")

                # Two-column layout
                with Horizontal(id="columns-container"):
                    # Left column - Local AI status and model selection
                    with Vertical(id="left-column"):
                        # Ollama status section
                        with Vertical(id="ollama-status"):
                            yield Label("Local AI Status", classes="status-title")
                            yield Label("Checking Ollama...", id="ollama-status-text")
                            yield Label("", id="ollama-models-list")

                        # LLM Model selector
                        with Vertical(id="llm-select-section"):
                            yield Label("Local LLM Model:", classes="section-label")
                            yield Select(
                                [],  # Options populated on mount
                                id="llm-select",
                                prompt="Select LLM model",
                            )

                    # Right column - Provider selection
                    with Vertical(id="right-column"):
                        # Presets
                        with Horizontal(id="presets-container"):
                            yield Button("All Claude", id="preset-claude", classes="preset-btn")
                            yield Button("Hybrid", id="preset-hybrid", classes="preset-btn", variant="primary")
                            yield Button("All Local", id="preset-local", classes="preset-btn")

                        # Planning section
                        with Vertical(classes="config-section"):
                            yield Label("Planning (task breakdown):", classes="section-label")
                            with RadioSet(id="planning-radio"):
                                yield RadioButton("Claude (Recommended)", id="planning-claude", value=True)
                                yield RadioButton("Local AI", id="planning-local")

                        # Context section
                        with Vertical(classes="config-section"):
                            yield Label("Context Retrieval:", classes="section-label")
                            with RadioSet(id="context-radio"):
                                yield RadioButton("Claude", id="context-claude")
                                yield RadioButton("Local AI (nomic-embed-text)", id="context-local", value=True)

                        # Coding section
                        with Vertical(classes="config-section"):
                            yield Label("Coding (code generation):", classes="section-label")
                            with RadioSet(id="coding-radio"):
                                yield RadioButton("Claude (Recommended)", id="coding-claude", value=True)
                                yield RadioButton("Local AI", id="coding-local")

        # Bottom buttons - outside the scroll area so always visible
        with Horizontal(id="continue-container"):
            yield Button("Continue", id="continue-btn", variant="success")

        yield Footer()

    def on_mount(self) -> None:
        """Check Ollama status when screen mounts."""
        self._check_ollama()

    def _check_ollama(self) -> None:
        """Check Ollama status and update display."""
        self._ollama_status = check_ollama_status()
        status_container = self.query_one("#ollama-status", Vertical)
        status_text = self.query_one("#ollama-status-text", Label)
        models_list = self.query_one("#ollama-models-list", Label)

        # Remove old status classes
        status_container.remove_class("status-ok", "status-warning", "status-error")

        if self._ollama_status.get("error"):
            status_container.add_class("status-error")
            status_text.update(f"[red]Not available: {self._ollama_status['error']}[/red]")
            models_list.update("")
        elif self._ollama_status.get("missing_models"):
            status_container.add_class("status-warning")
            missing = ", ".join(self._ollama_status["missing_models"])
            status_text.update(f"[yellow]Missing: {missing}[/yellow]")
            # Still show installed models
            self._update_models_list(models_list)
        elif self._ollama_status.get("available"):
            status_container.add_class("status-ok")
            status_text.update("[green]Ready[/green]")
            self._update_models_list(models_list)

        # Populate the LLM select dropdown
        self._populate_llm_select()

    def _update_models_list(self, models_list: Label) -> None:
        """Update the models list display."""
        llm_models = self._ollama_status.get("llm_models", [])
        embed_models = self._ollama_status.get("embed_models", [])

        lines = []
        if llm_models:
            llm_str = ", ".join(llm_models)
            lines.append(f"[cyan]LLM:[/cyan] {llm_str}")
        if embed_models:
            embed_str = ", ".join(embed_models)
            lines.append(f"[cyan]Embed:[/cyan] {embed_str}")

        models_list.update("\n".join(lines) if lines else "[dim]No models found[/dim]")

    def _populate_llm_select(self) -> None:
        """Populate the LLM select dropdown with available models."""
        llm_select = self.query_one("#llm-select", Select)
        llm_models = self._ollama_status.get("llm_models", [])

        if not llm_models:
            llm_select.set_options([("No models available", None)])
            return

        # Create options from available LLM models
        options = [(model, model) for model in llm_models]
        llm_select.set_options(options)

        # Select the first model by default, or preferred model if available
        for model in llm_models:
            if "qwen2.5-coder" in model:
                llm_select.value = model
                break
        else:
            # No preferred model found, select first
            llm_select.value = llm_models[0]

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "preset-claude":
            self._apply_preset("claude")
            self._complete()  # Auto-continue after preset
        elif event.button.id == "preset-hybrid":
            self._apply_preset("hybrid")
            self._complete()  # Auto-continue after preset
        elif event.button.id == "preset-local":
            self._apply_preset("local")
            self._complete()  # Auto-continue after preset
        elif event.button.id == "continue-btn":
            self._complete()
        elif event.button.id == "back-btn":
            self.action_go_back()

    def _apply_preset(self, preset: str) -> None:
        """Apply a preset configuration."""
        # Get radio buttons directly
        planning_claude = self.query_one("#planning-claude", RadioButton)
        planning_local = self.query_one("#planning-local", RadioButton)
        context_claude = self.query_one("#context-claude", RadioButton)
        context_local = self.query_one("#context-local", RadioButton)
        coding_claude = self.query_one("#coding-claude", RadioButton)
        coding_local = self.query_one("#coding-local", RadioButton)

        if preset == "claude":
            # All Claude
            planning_claude.value = True
            context_claude.value = True
            coding_claude.value = True
        elif preset == "local":
            # All Local
            planning_local.value = True
            context_local.value = True
            coding_local.value = True
        else:  # hybrid
            # Claude for planning/coding, Local for context
            planning_claude.value = True
            context_local.value = True
            coding_claude.value = True

        self.notify(f"Applied {preset} preset")

    def _get_current_config(self) -> AIConfig:
        """Get the current configuration from radio buttons and LLM select."""
        planning_claude = self.query_one("#planning-claude", RadioButton)
        context_claude = self.query_one("#context-claude", RadioButton)
        coding_claude = self.query_one("#coding-claude", RadioButton)
        llm_select = self.query_one("#llm-select", Select)

        # Get the selected LLM model
        selected_model = llm_select.value
        if selected_model is None or selected_model == Select.BLANK:
            selected_model = "qwen2.5-coder:7b"  # Default fallback

        return AIConfig(
            planning=AIProvider.CLAUDE if planning_claude.value else AIProvider.LOCAL,
            context=AIProvider.CLAUDE if context_claude.value else AIProvider.LOCAL,
            coding=AIProvider.CLAUDE if coding_claude.value else AIProvider.LOCAL,
            local_model=str(selected_model),
        )

    def _complete(self) -> None:
        """Complete configuration and proceed."""
        config = self._get_current_config()

        # Save to global config
        from ralph.global_config import save_global_config
        save_global_config(config)

        # Set config on app
        app = self.app
        app._ai_config = config
        app.pop_screen()

        # Check if any local AI is selected - if so, show setup screen
        uses_local = (
            config.planning == AIProvider.LOCAL or
            config.context == AIProvider.LOCAL or
            config.coding == AIProvider.LOCAL
        )

        if uses_local and app._current_project:
            from ralph.tui.screens.local_ai_setup import LocalAISetupScreen
            app.push_screen(LocalAISetupScreen(config, app._current_project.path))
        else:
            app._push_main_screen()

    def action_continue(self) -> None:
        """Handle enter key."""
        self._complete()

    def action_go_back(self) -> None:
        """Handle escape key - go back to previous screen."""
        self.app.pop_screen()


__all__ = ["AIConfigScreen", "AIConfigComplete"]
