"""Chat widget for interacting with the planning AI model."""

from __future__ import annotations

import shutil
import subprocess
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import Input, Static
from textual.reactive import reactive

if TYPE_CHECKING:
    from ralph.tui.app import RalphApp


@dataclass
class ChatMessage:
    """A chat message."""
    role: str  # "user" or "assistant"
    content: str


class ChatWidget(Widget):
    """A chat widget for interacting with the local planning AI."""

    DEFAULT_CSS = """
    ChatWidget {
        layout: vertical;
        height: 100%;
        background: $surface;
        border: solid $primary;
    }

    ChatWidget:focus-within {
        border: solid $accent;
    }

    #chat-messages {
        height: 1fr;
        padding: 0 1;
        background: $surface;
    }

    .chat-message {
        margin: 1 0;
        padding: 0 1;
    }

    .chat-user {
        color: $primary;
        background: $surface-darken-1;
    }

    .chat-assistant {
        color: $text;
        background: $surface-lighten-1;
    }

    .chat-role {
        text-style: bold;
        margin-bottom: 0;
    }

    .chat-role-user {
        color: $primary;
    }

    .chat-role-assistant {
        color: $success;
    }

    .chat-content {
        padding-left: 2;
    }

    #chat-input-container {
        height: auto;
        dock: bottom;
        padding: 1;
        background: $surface-darken-1;
    }

    #chat-input {
        width: 100%;
    }

    #chat-status {
        height: 1;
        dock: bottom;
        padding: 0 1;
        color: $text-muted;
        background: $surface-darken-2;
    }
    """

    can_focus = True
    is_streaming: reactive[bool] = reactive(False)

    def __init__(
        self,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the chat widget."""
        super().__init__(name=name, id=id, classes=classes)
        self._messages: list[ChatMessage] = []
        self._current_response = ""
        self._model_name = "qwen2.5-coder:7b"
        self._use_local = True
        self._claude_cli: str | None = None
        self._claude_available = False

    def compose(self) -> ComposeResult:
        """Compose the chat widget layout."""
        yield VerticalScroll(id="chat-messages")
        yield Static("Ready", id="chat-status")
        yield Input(placeholder="Type a message... (Enter to send)", id="chat-input")

    def on_mount(self) -> None:
        """Initialize with welcome message."""
        import os
        from ralph.models import AIProvider

        app: "RalphApp" = self.app  # type: ignore
        self._use_local = True

        if app._ai_config:
            self._model_name = app._ai_config.local_model
            self._use_local = app._ai_config.planning == AIProvider.LOCAL

        # Check for Anthropic SDK and API key
        self._anthropic_available = False
        if not self._use_local:
            try:
                import anthropic  # noqa: F401
                self._anthropic_available = bool(os.environ.get("ANTHROPIC_API_KEY"))
            except ImportError:
                pass

        self._add_system_message()
        if self._use_local:
            self._update_status(f"Model: {self._model_name}")
        elif self._anthropic_available:
            self._update_status("Model: Claude (streaming via API)")
        else:
            self._update_status("Claude selected - set ANTHROPIC_API_KEY to enable")

    def _add_system_message(self) -> None:
        """Add initial system/welcome message."""
        if self._use_local:
            welcome = (
                f"Welcome to Ralph Planning Assistant!\n\n"
                f"Using local model: {self._model_name}\n\n"
                "I can help you:\n"
                "- Break down tasks into smaller subtasks\n"
                "- Estimate complexity and dependencies\n"
                "- Suggest implementation approaches\n\n"
                "Type your question below."
            )
        elif self._claude_available:
            welcome = (
                "Welcome to Ralph Planning Assistant!\n\n"
                "Using Claude (via claude CLI)\n\n"
                "I can help you:\n"
                "- Break down tasks into smaller subtasks\n"
                "- Estimate complexity and dependencies\n"
                "- Suggest implementation approaches\n\n"
                "Type your question below."
            )
        else:
            welcome = (
                "Claude is selected but 'claude' CLI not found.\n\n"
                "Install Claude Code: npm install -g @anthropic-ai/claude-code\n"
                "Or switch to 'All Local' in AI config.\n\n"
                "You can also use the Terminal tab for commands."
            )
        self._messages.append(ChatMessage(role="assistant", content=welcome))
        self._refresh_messages()

    def _update_status(self, text: str) -> None:
        """Update the status bar."""
        try:
            status = self.query_one("#chat-status", Static)
            status.update(text)
        except Exception:
            pass

    def _refresh_messages(self) -> None:
        """Refresh the message display."""
        try:
            container = self.query_one("#chat-messages", VerticalScroll)
            container.remove_children()

            for msg in self._messages:
                role_class = "chat-role-user" if msg.role == "user" else "chat-role-assistant"
                msg_class = "chat-user" if msg.role == "user" else "chat-assistant"
                role_label = "You" if msg.role == "user" else "Assistant"

                # Create message widget
                role_widget = Static(f"{role_label}:", classes=f"chat-role {role_class}")
                content_widget = Static(msg.content, classes="chat-content")

                container.mount(role_widget)
                container.mount(content_widget)

            # Scroll to bottom
            self.call_later(lambda: container.scroll_end(animate=False))
        except Exception:
            pass

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle message submission."""
        if event.input.id != "chat-input":
            return

        message = event.value.strip()
        if not message:
            return

        # Check if chat is available
        if not self._use_local and not self._claude_available:
            self.notify("Install 'claude' CLI to enable Claude chat")
            event.input.value = ""
            return

        if self.is_streaming:
            self.notify("Please wait for the current response to finish")
            return

        # Clear input
        event.input.value = ""

        # Add user message
        self._messages.append(ChatMessage(role="user", content=message))
        self._refresh_messages()

        # Start streaming response
        self._stream_response(message)

    def _stream_response(self, _user_message: str) -> None:
        """Stream a response from the AI model."""
        self.is_streaming = True
        self._current_response = ""

        if self._use_local:
            self._update_status(f"Thinking... ({self._model_name})")
        else:
            self._update_status("Thinking... (Claude)")

        # Add placeholder for assistant response
        self._messages.append(ChatMessage(role="assistant", content="..."))
        self._refresh_messages()

        # Run in background thread
        thread = threading.Thread(
            target=self._do_stream_response,
            daemon=True
        )
        thread.start()

    def _do_stream_response(self) -> None:
        """Perform the streaming response in a background thread."""
        try:
            if self._use_local:
                self._stream_ollama()
            else:
                self._stream_claude()
        except Exception as e:
            self._current_response = f"Error: {type(e).__name__}: {str(e)}"

        # Always finalize, even if there was an error
        try:
            self.app.call_from_thread(self._finalize_response)
        except Exception:
            # App might be closing, ignore
            pass

    def _stream_ollama(self) -> None:
        """Stream response from Ollama."""
        import ollama

        # Build message history (last 10 messages for context)
        messages = []
        for msg in self._messages[-11:-1]:  # Exclude the placeholder
            messages.append({"role": msg.role, "content": msg.content})

        # Stream the response
        stream = ollama.chat(
            model=self._model_name,
            messages=messages,
            stream=True,
        )

        for chunk in stream:
            content = chunk.get("message", {}).get("content", "")
            if content:
                self._current_response += content
                self.app.call_from_thread(self._update_current_response)

    def _stream_claude(self) -> None:
        """Stream response from Claude using Anthropic SDK."""
        try:
            import anthropic
        except ImportError:
            self._current_response = (
                "Anthropic SDK not installed.\n\n"
                "Install with: pip install anthropic\n"
                "Or: pip install -e '.[ai]'"
            )
            return

        # Check for API key
        import os
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            self._current_response = (
                "ANTHROPIC_API_KEY not set.\n\n"
                "Set your API key:\n"
                "  set ANTHROPIC_API_KEY=your-key-here\n\n"
                "Get a key at: https://console.anthropic.com/"
            )
            return

        # Build message history (last 10 messages for context)
        messages = []
        for msg in self._messages[-11:-1]:  # Exclude the placeholder
            messages.append({"role": msg.role, "content": msg.content})

        try:
            client = anthropic.Anthropic(api_key=api_key)

            # Stream the response
            with client.messages.stream(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                messages=messages,
                system="You are a helpful software architect assistant. Help break down tasks, estimate complexity, and suggest implementation approaches. Be concise but thorough.",
            ) as stream:
                for text in stream.text_stream:
                    self._current_response += text
                    self.app.call_from_thread(self._update_current_response)

        except anthropic.APIConnectionError:
            self._current_response = "Error: Could not connect to Anthropic API"
        except anthropic.RateLimitError:
            self._current_response = "Error: Rate limit exceeded. Please wait and try again."
        except anthropic.APIStatusError as e:
            self._current_response = f"Error: API error {e.status_code}: {e.message}"
        except Exception as e:
            self._current_response = f"Error: {type(e).__name__}: {str(e)}"

    def _update_current_response(self) -> None:
        """Update the current streaming response in the UI."""
        if self._messages and self._messages[-1].role == "assistant":
            self._messages[-1].content = self._current_response
            self._refresh_messages()

    def _finalize_response(self) -> None:
        """Finalize the response after streaming completes."""
        self.is_streaming = False
        if self._use_local:
            self._update_status(f"Model: {self._model_name}")
        else:
            self._update_status("Model: Claude (via claude CLI)")

        if self._messages and self._messages[-1].role == "assistant":
            self._messages[-1].content = self._current_response or "(No response)"
            self._refresh_messages()

    def clear_chat(self) -> None:
        """Clear chat history and start fresh."""
        self._messages.clear()
        self._add_system_message()


__all__ = ["ChatWidget", "ChatMessage"]
