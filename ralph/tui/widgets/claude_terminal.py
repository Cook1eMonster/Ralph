"""Claude terminal widget for Ralph TUI.

Embeds a full Claude Code session in a PTY, giving the same
interactive experience as running claude in a terminal.
"""

from __future__ import annotations

import asyncio
import shutil
import sys
from typing import TYPE_CHECKING

from rich.text import Text
from textual.reactive import reactive

from .terminal import TerminalWidget

if TYPE_CHECKING:
    pass


class ClaudeTerminalWidget(TerminalWidget):
    """A terminal widget that runs Claude Code.

    This gives the full Claude Code terminal experience embedded
    in the Ralph TUI, with streaming responses, tool use, and
    full interactivity.
    """

    DEFAULT_CSS = """
    ClaudeTerminalWidget {
        background: $surface;
        color: $text;
        padding: 0;
        border: solid $primary;
    }

    ClaudeTerminalWidget:focus {
        border: solid $accent;
    }
    """

    # Track if Claude is available
    claude_available: reactive[bool] = reactive(False)
    _started: reactive[bool] = reactive(False)

    def __init__(
        self,
        working_dir: str | None = None,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the Claude terminal widget.

        Args:
            working_dir: Directory to run Claude in (project root).
            name: Widget name.
            id: Widget ID.
            classes: Widget CSS classes.
        """
        self._working_dir = working_dir
        self._claude_path = shutil.which("claude")
        self._pending_start = False

        # Initialize parent but don't spawn yet
        super().__init__(
            shell=self._claude_path or "echo 'Claude not found'",
            name=name,
            id=id,
            classes=classes,
        )

        self.claude_available = bool(self._claude_path)

    def on_mount(self) -> None:
        """Override mount to delay spawning until we have project context."""
        # Don't call super().on_mount() - we'll spawn later when project is set
        # Just show placeholder until then
        if not self._claude_path:
            self._error_message = (
                "Claude CLI not found.\n\n"
                "Install with: npm install -g @anthropic-ai/claude-code"
            )
        # Don't spawn anything here - wait for set_working_dir

    def set_working_dir(self, working_dir: str) -> None:
        """Set the working directory for when Claude starts.

        Args:
            working_dir: The project directory to run Claude in.
        """
        self._working_dir = working_dir
        # Don't auto-start - let user press Enter to start
        self.refresh()

    def start_claude(self) -> None:
        """Start the Claude session."""
        if self._started or not self._claude_path:
            return

        self._started = True
        self._pending_commands: list[str] = []

        try:
            self._spawn_pty()
            if self._process_alive:
                self._read_task = asyncio.create_task(self._read_pty_output())
                # Send pending commands after a short delay for shell to initialize
                # _spawn_pty sets _pending_commands on Windows
                if getattr(self, '_pending_commands', None):
                    asyncio.create_task(self._send_pending_commands())
        except Exception as e:
            self._error_message = f"Failed to start Claude: {e}"
            self._process_alive = False

    async def _send_pending_commands(self) -> None:
        """Send pending commands to the shell after it starts."""
        # Wait for shell to be ready
        await asyncio.sleep(0.5)

        for cmd in self._pending_commands:
            if self._process_alive:
                self._write_to_pty((cmd + "\r").encode("utf-8"))
                # Small delay between commands
                await asyncio.sleep(0.1)

        self._pending_commands = []

    def _write_to_pty(self, data: bytes) -> None:
        """Write data to the PTY."""
        if sys.platform == "win32":
            if self._pty is not None:
                try:
                    text = data.decode("utf-8", errors="replace")
                    self._pty.write(text)
                except Exception:
                    pass
        else:
            import os
            if self._pty_fd is not None:
                try:
                    os.write(self._pty_fd, data)
                except OSError:
                    pass

    def _spawn_pty(self) -> None:
        """Spawn the PTY with Claude, setting the working directory."""
        if sys.platform == "win32":
            self._spawn_pty_windows_with_cwd()
        else:
            self._spawn_pty_unix_with_cwd()

    def _spawn_pty_windows_with_cwd(self) -> None:
        """Spawn PTY on Windows with working directory support."""
        import shutil

        try:
            import winpty
        except ImportError:
            self._error_message = "Terminal unavailable: winpty not installed"
            self._process_alive = False
            return

        if not self._claude_path:
            self._error_message = "Claude CLI not found"
            self._process_alive = False
            return

        try:
            self._pty = winpty.PTY(self._cols, self._rows)

            # Spawn PowerShell as interactive shell
            powershell = shutil.which("powershell") or "powershell.exe"
            self._pty.spawn(f'{powershell} -NoProfile -NoLogo')
            self._process_alive = True

            # Queue commands to send after shell starts
            self._pending_commands = []
            if self._working_dir:
                self._pending_commands.append(f'cd "{self._working_dir}"')
            self._pending_commands.append('claude')

        except Exception as e:
            self._error_message = f"Failed to start Claude: {e}"
            self._process_alive = False

    def _spawn_pty_unix_with_cwd(self) -> None:
        """Spawn PTY on Unix with working directory support."""
        import fcntl
        import os
        import pty
        import struct
        import termios

        if not self._claude_path:
            self._error_message = "Claude CLI not found"
            self._process_alive = False
            return

        pid, fd = pty.fork()

        if pid == 0:
            # Child process
            if self._working_dir:
                os.chdir(self._working_dir)
            os.execvp(self._claude_path, [self._claude_path])
        else:
            # Parent process
            self._pty_fd = fd
            self._pty = pid

            # Set the terminal size
            winsize = struct.pack("HHHH", self._rows, self._cols, 0, 0)
            fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)

            # Set non-blocking mode
            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

            self._process_alive = True

    def render(self) -> Text:
        """Render the terminal or a waiting message."""
        if self._error_message:
            result = Text()
            result.append("\n\n  ", style="dim")
            result.append(self._error_message, style="yellow")
            return result

        if not self._started:
            result = Text()
            result.append("\n\n  ", style="dim")
            result.append("Claude Code", style="bold cyan")
            result.append("\n\n  ", style="dim")
            if self._working_dir:
                result.append(f"Project: {self._working_dir}", style="green")
                result.append("\n\n  ", style="dim")
                result.append("Press ", style="dim")
                result.append("Enter", style="bold yellow")
                result.append(" to start Claude session.", style="dim")
            else:
                result.append("Select a project to enable Claude.", style="dim")
            return result

        return super().render()

    def on_key(self, event) -> None:
        """Handle key events."""
        # If not started and Enter is pressed, start Claude
        if not self._started and self._working_dir and event.key == "enter":
            self.start_claude()
            event.stop()
            return

        # Otherwise let parent handle it (sends to PTY)
        if self._started:
            super().on_key(event)

    def restart_claude(self) -> None:
        """Restart Claude with a fresh session."""
        self._started = False
        self._cleanup_pty()
        self._screen.reset()
        self.start_claude()
        self.refresh()


__all__ = ["ClaudeTerminalWidget"]
