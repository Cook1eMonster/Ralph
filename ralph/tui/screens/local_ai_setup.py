"""Local AI Setup screen for Ralph TUI.

Handles pulling Ollama models and indexing the codebase when Local AI is selected.
Shows real-time progress bars and status updates.
"""

import threading
from typing import TYPE_CHECKING, Optional

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, ProgressBar, Static

from ralph.models import AIConfig, AIProvider
from ralph.tui.widgets import Spinner

if TYPE_CHECKING:
    from ralph.tui.app import RalphApp


class SetupComplete(Message):
    """Message sent when setup is complete."""
    pass


class LocalAISetupScreen(Screen):
    """Screen for setting up Local AI (pulling models, indexing)."""

    CSS = """
    LocalAISetupScreen {
        background: $surface;
    }

    #setup-container {
        width: 100%;
        height: 1fr;
        padding: 1 2;
        align: center top;
    }

    #setup-box {
        width: 90;
        height: auto;
        max-height: 100%;
        border: solid $primary;
        padding: 1;
    }

    #setup-title {
        text-style: bold;
        text-align: center;
        color: $primary;
        width: 100%;
        margin-bottom: 1;
    }

    #overall-progress {
        margin: 0 0 1 0;
        width: 100%;
    }

    #overall-progress Bar {
        width: 1fr;
    }

    .step-container {
        margin-bottom: 1;
        padding: 0 1;
        border: solid $secondary;
        height: auto;
    }

    .step-container.active {
        border: solid $warning;
    }

    .step-container.done {
        border: solid $success;
    }

    .step-container.error {
        border: solid $error;
    }

    .step-header {
        width: 100%;
        height: auto;
    }

    .step-title {
        text-style: bold;
    }

    .step-status {
        color: $text-muted;
        text-align: right;
    }

    .step-status.active {
        color: $warning;
    }

    .step-status.done {
        color: $success;
    }

    .step-status.error {
        color: $error;
    }

    .status-row {
        width: auto;
        height: 1;
    }

    .status-row Spinner {
        margin-right: 1;
    }

    .step-detail {
        color: $text-muted;
        padding-left: 2;
        height: auto;
    }

    ProgressBar {
        padding: 0;
        height: 1;
        margin-top: 1;
    }

    ProgressBar Bar {
        width: 1fr;
        background: $surface-darken-1;
    }

    ProgressBar PercentageStatus {
        width: 5;
        text-align: right;
    }

    #log-container {
        height: 6;
        min-height: 4;
        border: solid $secondary;
        margin-top: 1;
        background: $surface-darken-1;
    }

    #log-scroll {
        height: 100%;
    }

    #log-text {
        padding: 0 1;
    }

    #button-bar {
        dock: bottom;
        width: 100%;
        height: auto;
        align: center middle;
        padding: 1;
        background: $surface;
    }

    #skip-btn {
        margin-right: 2;
    }
    """

    BINDINGS = [
        ("escape", "skip", "Skip"),
        ("enter", "continue", "Continue"),
    ]

    def __init__(self, ai_config: AIConfig, project_path: str):
        super().__init__()
        self._ai_config = ai_config
        self._project_path = project_path
        self._setup_thread: Optional[threading.Thread] = None
        self._is_running = False
        self._is_complete = False
        self._log_lines: list[str] = []

    def compose(self) -> ComposeResult:
        yield Header()

        with VerticalScroll(id="setup-container"):
            with Vertical(id="setup-box"):
                yield Label("Local AI Setup", id="setup-title")
                yield ProgressBar(id="overall-progress", total=100, show_eta=False)

                # Step 1: Check Ollama
                with Vertical(id="step-ollama", classes="step-container"):
                    with Horizontal(classes="step-header"):
                        yield Label("1. Check Ollama", classes="step-title")
                        with Horizontal(classes="status-row"):
                            yield Spinner(id="ollama-spinner")
                            yield Label("Waiting", id="ollama-status", classes="step-status")
                    yield Label("", id="ollama-detail", classes="step-detail")

                # Step 2: Pull models
                with Vertical(id="step-models", classes="step-container"):
                    with Horizontal(classes="step-header"):
                        yield Label("2. Pull Models", classes="step-title")
                        with Horizontal(classes="status-row"):
                            yield Spinner(id="models-spinner")
                            yield Label("Waiting", id="models-status", classes="step-status")
                    yield Label("", id="models-detail", classes="step-detail")
                    yield ProgressBar(id="models-progress", total=100, show_eta=False)

                # Step 3: Index codebase
                with Vertical(id="step-index", classes="step-container"):
                    with Horizontal(classes="step-header"):
                        yield Label("3. Index Codebase", classes="step-title")
                        with Horizontal(classes="status-row"):
                            yield Spinner(id="index-spinner")
                            yield Label("Waiting", id="index-status", classes="step-status")
                    yield Label("", id="index-detail", classes="step-detail")
                    yield ProgressBar(id="index-progress", total=100, show_eta=False)

                # Log output
                with Vertical(id="log-container"):
                    with VerticalScroll(id="log-scroll"):
                        yield Static("", id="log-text")

        # Buttons - docked at bottom, outside scroll area
        with Horizontal(id="button-bar"):
            yield Button("Skip Setup", id="skip-btn", variant="default")
            yield Button("Continue", id="continue-btn", variant="success", disabled=True)

        yield Footer()

    def on_mount(self) -> None:
        """Start setup process when screen mounts."""
        self._start_setup()

    def _log(self, message: str) -> None:
        """Add a log message."""
        self._log_lines.append(message)
        # Keep only last 20 lines
        if len(self._log_lines) > 20:
            self._log_lines = self._log_lines[-20:]
        self.app.call_from_thread(self._update_log)

    def _update_log(self) -> None:
        """Update log display (must be called from main thread)."""
        try:
            log_text = self.query_one("#log-text", Static)
            log_text.update("\n".join(self._log_lines))
            # Scroll to bottom
            scroll = self.query_one("#log-scroll", VerticalScroll)
            scroll.scroll_end(animate=False)
        except Exception:
            pass

    def _set_step_state(self, step: str, state: str, status_text: str, detail: str = "") -> None:
        """Update a step's visual state (call from thread)."""
        self.app.call_from_thread(self._do_set_step_state, step, state, status_text, detail)

    def _do_set_step_state(self, step: str, state: str, status_text: str, detail: str) -> None:
        """Update step state (must be called from main thread)."""
        try:
            container = self.query_one(f"#step-{step}", Vertical)
            status_label = self.query_one(f"#{step}-status", Label)
            detail_label = self.query_one(f"#{step}-detail", Label)
            spinner = self.query_one(f"#{step}-spinner", Spinner)

            # Remove old classes
            container.remove_class("active", "done", "error")
            status_label.remove_class("active", "done", "error")

            # Add new class and control spinner
            if state == "active":
                container.add_class(state)
                status_label.add_class(state)
                spinner.start()
            elif state in ("done", "error"):
                container.add_class(state)
                status_label.add_class(state)
                spinner.stop()
            else:
                spinner.stop()

            status_label.update(status_text)
            detail_label.update(detail)
        except Exception:
            pass

    def _set_progress(self, step: str, current: int, total: int) -> None:
        """Update progress bar (call from thread)."""
        self.app.call_from_thread(self._do_set_progress, step, current, total)

    def _do_set_progress(self, step: str, current: int, total: int) -> None:
        """Update progress bar (must be called from main thread)."""
        try:
            progress = self.query_one(f"#{step}-progress", ProgressBar)
            if total > 0:
                progress.update(total=total, progress=current)
        except Exception:
            pass

    def _enable_continue(self) -> None:
        """Enable the continue button."""
        self.app.call_from_thread(self._do_enable_continue)

    def _do_enable_continue(self) -> None:
        """Enable continue button (main thread)."""
        try:
            btn = self.query_one("#continue-btn", Button)
            btn.disabled = False
            btn.focus()
        except Exception:
            pass

    def _update_overall_progress(self, completed_steps: int, total_steps: int = 3) -> None:
        """Update overall progress (call from thread)."""
        pct = int(completed_steps / total_steps * 100)
        self.app.call_from_thread(self._do_update_overall, pct)

    def _do_update_overall(self, pct: int) -> None:
        """Update overall progress bar (main thread)."""
        try:
            progress = self.query_one("#overall-progress", ProgressBar)
            progress.update(progress=pct)
        except Exception:
            pass

    def _start_setup(self) -> None:
        """Start the setup process in a background thread."""
        if self._is_running:
            return

        self._is_running = True
        self._setup_thread = threading.Thread(target=self._run_setup, daemon=True)
        self._setup_thread.start()

    def _run_setup(self) -> None:
        """Run the setup steps (in background thread)."""
        try:
            # Step 1: Check Ollama
            self._update_overall_progress(0)
            self._set_step_state("ollama", "active", "Checking...", "Connecting to Ollama")
            ollama_ok = self._check_ollama()

            if not ollama_ok:
                self._set_step_state("ollama", "error", "Failed", "Ollama not available")
                self._log("ERROR: Ollama is not running or not installed.")
                self._log("Please install Ollama from https://ollama.ai")
                self._finish_setup(success=False)
                return

            self._set_step_state("ollama", "done", "Ready", "Ollama is running")
            self._update_overall_progress(1)

            # Step 2: Pull models if needed
            self._set_step_state("models", "active", "Checking...", "Checking installed models")
            models_ok = self._ensure_models()

            if not models_ok:
                self._set_step_state("models", "error", "Failed", "Failed to pull models")
                self._finish_setup(success=False)
                return

            self._set_step_state("models", "done", "Ready", "All models installed")
            self._set_progress("models", 100, 100)
            self._update_overall_progress(2)

            # Step 3: Index codebase (only if context uses local AI)
            if self._ai_config.context == AIProvider.LOCAL:
                self._set_step_state("index", "active", "Starting...", "Preparing to index")
                self._set_progress("index", 0, 100)
                index_ok = self._index_codebase()

                if not index_ok:
                    self._set_step_state("index", "error", "Failed", "Indexing failed")
                    self._finish_setup(success=False)
                    return

                self._set_step_state("index", "done", "Complete", "Codebase indexed")
                self._set_progress("index", 100, 100)
            else:
                self._set_step_state("index", "done", "Skipped", "Using Claude for context")

            self._update_overall_progress(3)
            self._finish_setup(success=True)

        except Exception as e:
            self._log(f"ERROR: {e}")
            self._finish_setup(success=False)

    def _check_ollama(self) -> bool:
        """Check if Ollama is available."""
        try:
            import ollama
            from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

            def do_list():
                return ollama.list()

            # Use thread pool with timeout to avoid hanging
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(do_list)
                try:
                    response = future.result(timeout=10)  # 10 second timeout
                except FuturesTimeoutError:
                    self._log("ERROR: Ollama not responding (timeout)")
                    self._log("Make sure Ollama is running: ollama serve")
                    return False

            # Count models
            if hasattr(response, 'models'):
                count = len(response.models)
            else:
                count = len(response.get("models", []))

            self._log(f"Ollama connected: {count} models installed")
            return True
        except ImportError:
            self._log("ERROR: ollama package not installed")
            self._log("Run: pip install ollama")
            return False
        except Exception as e:
            self._log(f"ERROR: Cannot connect to Ollama: {e}")
            return False

    def _ensure_models(self) -> bool:
        """Ensure required models are installed, pull if missing."""
        try:
            import ollama
            from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

            # Get list of installed models with timeout
            def do_list():
                return ollama.list()

            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(do_list)
                try:
                    response = future.result(timeout=10)
                except FuturesTimeoutError:
                    self._log("ERROR: Ollama not responding")
                    return False

            if hasattr(response, 'models'):
                installed = [m.model.split(":")[0] for m in response.models if hasattr(m, 'model')]
            else:
                installed = [m.get("name", "").split(":")[0] for m in response.get("models", [])]

            self._log(f"Installed models: {', '.join(installed) if installed else 'none'}")

            # Determine required models based on config
            required = []
            if self._ai_config.context == AIProvider.LOCAL:
                required.append("nomic-embed-text")
            if self._ai_config.planning == AIProvider.LOCAL or self._ai_config.coding == AIProvider.LOCAL:
                # Use the configured model or default
                model_base = self._ai_config.local_model.split(":")[0] if self._ai_config.local_model else "qwen2.5-coder"
                required.append(model_base)

            if not required:
                self._log("No models required")
                return True

            self._log(f"Required models: {', '.join(required)}")

            # Pull missing models with streaming progress
            for model in required:
                if model in installed:
                    self._log(f"  {model}: already installed")
                    continue

                self._log(f"  {model}: pulling...")
                self._set_step_state("models", "active", "Pulling...", f"Downloading {model}")
                self._set_progress("models", 0, 100)

                if not self._pull_model_streaming(model):
                    return False

                self._log(f"  {model}: installed")

            return True

        except Exception as e:
            self._log(f"ERROR checking models: {e}")
            return False

    def _pull_model_streaming(self, model_name: str) -> bool:
        """Pull a model with streaming progress updates."""
        try:
            import ollama

            last_status = ""
            for progress in ollama.pull(model_name, stream=True):
                status = progress.get('status', '')
                completed = progress.get('completed', 0)
                total = progress.get('total', 0)

                if total > 0:
                    # Downloading - show byte progress
                    pct = int(completed / total * 100)
                    size_mb = completed / 1024 / 1024
                    total_mb = total / 1024 / 1024
                    detail = f"{status}: {size_mb:.0f}MB / {total_mb:.0f}MB"
                    self._set_step_state("models", "active", f"{pct}%", detail)
                    self._set_progress("models", completed, total)
                else:
                    # Other status (pulling manifest, verifying, etc)
                    if status != last_status:
                        self._set_step_state("models", "active", "Working...", status)
                        last_status = status

            return True

        except Exception as e:
            self._log(f"ERROR pulling {model_name}: {e}")
            return False

    def _index_codebase(self) -> bool:
        """Index the codebase for context retrieval with progress."""
        try:
            from ralph.context import ContextEngine

            self._log(f"Indexing: {self._project_path}")

            engine = ContextEngine(self._project_path)

            # Check existing index
            status = engine.status()
            if status.get("indexed_files", 0) > 0:
                self._log(f"Existing index: {status['indexed_files']} files, {status['total_chunks']} chunks")

            # Define progress callback
            def on_progress(current: int, total: int, filepath: str, status: str):
                if total > 0:
                    pct = int(current / total * 100) if total > 0 else 0

                    # Truncate filepath for display
                    if len(filepath) > 50:
                        display_path = "..." + filepath[-47:]
                    else:
                        display_path = filepath

                    if status == "indexing":
                        self._set_step_state("index", "active", f"{pct}%", display_path)
                        self._set_progress("index", current, total)
                    elif status == "complete":
                        self._set_step_state("index", "active", "100%", "Finalizing...")
                        self._set_progress("index", total, total)

                    # Log every 50 files
                    if current > 0 and current % 50 == 0:
                        self._log(f"  Indexed {current}/{total} files...")

            # Run indexing with progress callback
            result = engine.index(force=False, verbose=False, progress_callback=on_progress)

            if result.error_message:
                self._log(f"ERROR: {result.error_message}")
                return False

            self._log(f"Indexing complete:")
            self._log(f"  New: {result.indexed}, Updated: {result.updated}, Unchanged: {result.skipped}")
            self._log(f"  Total chunks: {result.total_chunks}")
            return True

        except ImportError as e:
            self._log(f"ERROR: Missing dependency: {e}")
            self._log("Run: pip install chromadb ollama")
            return False
        except Exception as e:
            self._log(f"ERROR indexing: {e}")
            return False

    def _finish_setup(self, success: bool) -> None:
        """Finish setup and enable continue."""
        self._is_running = False
        self._is_complete = success

        if success:
            self._log("")
            self._log("Setup complete! Local AI is ready.")
        else:
            self._log("")
            self._log("Setup failed. You can skip to continue without local AI.")

        self._enable_continue()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "skip-btn":
            self.action_skip()
        elif event.button.id == "continue-btn":
            self.action_continue()

    def action_skip(self) -> None:
        """Skip setup and continue."""
        self._proceed_to_main()

    def action_continue(self) -> None:
        """Continue to main screen."""
        self._proceed_to_main()

    def _proceed_to_main(self) -> None:
        """Proceed to the main screen."""
        app = self.app
        app.pop_screen()
        app._push_main_screen()


__all__ = ["LocalAISetupScreen", "SetupComplete"]
