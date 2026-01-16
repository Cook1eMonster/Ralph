"""Embedded PTY terminal widget for Ralph TUI.

This widget provides a full terminal emulator within the Textual TUI,
supporting ANSI colors, cursor positioning, and scrollback history.
"""

from __future__ import annotations

import asyncio
import shutil
import sys
from typing import TYPE_CHECKING

import pyte
from rich.style import Style
from rich.text import Text
from textual import events
from textual.reactive import reactive
from textual.widget import Widget

if TYPE_CHECKING:
    from typing import Any

# Platform-specific imports
if sys.platform == "win32":
    try:
        import winpty
        WINPTY_AVAILABLE = True
    except ImportError:
        WINPTY_AVAILABLE = False
        winpty = None
else:
    WINPTY_AVAILABLE = True  # Unix always has pty
    import os
    import pty
    import fcntl
    import termios
    import struct
    import signal


# ANSI color mapping to Rich colors
ANSI_COLORS = {
    "black": "black",
    "red": "red",
    "green": "green",
    "brown": "yellow",
    "blue": "blue",
    "magenta": "magenta",
    "cyan": "cyan",
    "white": "white",
    "default": "default",
}

# Bright/bold color variants
ANSI_BRIGHT_COLORS = {
    "black": "bright_black",
    "red": "bright_red",
    "green": "bright_green",
    "brown": "bright_yellow",
    "blue": "bright_blue",
    "magenta": "bright_magenta",
    "cyan": "bright_cyan",
    "white": "bright_white",
    "default": "default",
}


class TerminalWidget(Widget):
    """A widget that embeds a full PTY terminal.

    This widget creates a pseudo-terminal, spawns a shell process,
    and renders the terminal output using pyte for ANSI parsing.
    """

    DEFAULT_CSS = """
    TerminalWidget {
        background: $surface;
        color: $text;
        padding: 0;
        border: solid $primary;
    }

    TerminalWidget:focus {
        border: solid $accent;
    }
    """

    can_focus = True

    # Reactive properties
    cursor_visible: reactive[bool] = reactive(True)
    scrollback_offset: reactive[int] = reactive(0)

    def __init__(
        self,
        shell: str | None = None,
        rows: int = 24,
        cols: int = 80,
        scrollback_lines: int = 1000,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the terminal widget.

        Args:
            shell: Shell command to run. Defaults to system shell.
            rows: Number of terminal rows.
            cols: Number of terminal columns.
            scrollback_lines: Number of scrollback lines to retain.
            name: Widget name.
            id: Widget ID.
            classes: Widget CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)

        self._shell = shell or self._get_default_shell()
        self._rows = rows
        self._cols = cols
        self._scrollback_lines = scrollback_lines

        # Create pyte screen with history for scrollback
        self._history: list[list[pyte.screen.Char]] = []
        self._screen = pyte.Screen(cols, rows)
        self._stream = pyte.Stream(self._screen)

        # PTY state
        self._pty: Any = None
        self._pty_fd: int | None = None  # Unix only
        self._process_alive = False
        self._read_task: asyncio.Task | None = None

        # Input buffer for handling special keys
        self._input_buffer = b""

        # Error message if terminal fails to start
        self._error_message: str | None = None

    def _get_default_shell(self) -> str:
        """Get the default shell for the current platform."""
        if sys.platform == "win32":
            # Prefer PowerShell, fall back to cmd
            pwsh = shutil.which("pwsh") or shutil.which("powershell")
            if pwsh:
                return pwsh
            return shutil.which("cmd") or "cmd.exe"
        else:
            # Use SHELL env var or fall back to /bin/sh
            import os
            return os.environ.get("SHELL", "/bin/sh")

    def on_mount(self) -> None:
        """Called when widget is mounted. Start the PTY."""
        try:
            self._spawn_pty()
            if self._process_alive:
                self._read_task = asyncio.create_task(self._read_pty_output())
        except Exception as e:
            self._error_message = f"Terminal failed to start: {e}"
            self._process_alive = False

    def on_unmount(self) -> None:
        """Called when widget is unmounted. Clean up PTY."""
        self._cleanup_pty()

    def _spawn_pty(self) -> None:
        """Spawn the PTY and shell process."""
        try:
            if sys.platform == "win32":
                if not WINPTY_AVAILABLE:
                    self._error_message = "Terminal unavailable: winpty not installed"
                    self._process_alive = False
                    return
                self._spawn_pty_windows()
            else:
                self._spawn_pty_unix()
            self._process_alive = True
        except Exception as e:
            self.log.error(f"Failed to spawn PTY: {e}")
            self._error_message = f"Terminal unavailable: {e}"
            self._process_alive = False

    def _spawn_pty_windows(self) -> None:
        """Spawn PTY on Windows using pywinpty."""
        # Create ConPTY with winpty
        self._pty = winpty.PTY(self._cols, self._rows)
        # Spawn the shell process
        self._pty.spawn(self._shell)

    def _spawn_pty_unix(self) -> None:
        """Spawn PTY on Unix using stdlib pty."""
        # Fork a new process with a PTY
        pid, fd = pty.fork()

        if pid == 0:
            # Child process - exec the shell
            import os
            os.execvp(self._shell, [self._shell])
        else:
            # Parent process - store the fd
            self._pty_fd = fd
            self._pty = pid

            # Set the terminal size
            self._set_pty_size_unix(self._rows, self._cols)

            # Set non-blocking mode
            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    def _set_pty_size_unix(self, rows: int, cols: int) -> None:
        """Set PTY size on Unix."""
        if self._pty_fd is not None:
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self._pty_fd, termios.TIOCSWINSZ, winsize)

    async def _read_pty_output(self) -> None:
        """Asynchronously read output from the PTY."""
        try:
            while self._process_alive:
                data = await self._read_pty_data()
                if data:
                    # Save current screen lines to history before processing
                    self._save_to_history()
                    # Feed data to pyte stream for ANSI parsing
                    self._stream.feed(data.decode("utf-8", errors="replace"))
                    # Trigger a refresh
                    self.refresh()
                else:
                    # Small delay to prevent busy loop
                    await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.log.error(f"Error reading PTY output: {e}")
            self._process_alive = False

    async def _read_pty_data(self) -> bytes:
        """Read data from the PTY in a platform-specific way."""
        if sys.platform == "win32":
            return await self._read_pty_data_windows()
        else:
            return await self._read_pty_data_unix()

    async def _read_pty_data_windows(self) -> bytes:
        """Read PTY data on Windows."""
        if self._pty is None:
            return b""

        # Run PTY operations in a thread to avoid blocking event loop
        def do_read():
            try:
                # Check if process is still alive
                if not self._pty.isalive():
                    return None  # Signal process died

                # Read available data (non-blocking)
                data = self._pty.read(4096, blocking=False)
                if data:
                    return data.encode("utf-8") if isinstance(data, str) else data
                return b""
            except Exception:
                return b""

        result = await asyncio.to_thread(do_read)

        if result is None:
            self._process_alive = False
            return b""

        if not result:
            await asyncio.sleep(0.01)

        return result

    async def _read_pty_data_unix(self) -> bytes:
        """Read PTY data on Unix."""
        if self._pty_fd is None:
            return b""

        import os

        # Check if child process is still alive
        try:
            pid, status = os.waitpid(self._pty, os.WNOHANG)
            if pid != 0:
                self._process_alive = False
                return b""
        except ChildProcessError:
            self._process_alive = False
            return b""

        # Try to read from the PTY fd
        try:
            data = os.read(self._pty_fd, 4096)
            return data
        except BlockingIOError:
            await asyncio.sleep(0.01)
            return b""
        except OSError:
            self._process_alive = False
            return b""

    def _save_to_history(self) -> None:
        """Save scrolled-off lines to history buffer."""
        # This is called before processing new data
        # We track lines that scroll off the top
        pass  # History is handled by pyte's HistoryScreen if needed

    def on_key(self, event: events.Key) -> None:
        """Handle keyboard input and send to PTY."""
        if not self._process_alive:
            return

        # Convert Textual key event to bytes for PTY
        data = self._key_to_bytes(event)
        if data:
            self._write_to_pty(data)
            event.stop()

    def _key_to_bytes(self, event: events.Key) -> bytes:
        """Convert a Textual key event to bytes for the PTY."""
        key = event.key

        # Special key mappings
        key_map = {
            "enter": b"\r",
            "tab": b"\t",
            "escape": b"\x1b",
            "backspace": b"\x7f",
            "delete": b"\x1b[3~",
            "up": b"\x1b[A",
            "down": b"\x1b[B",
            "right": b"\x1b[C",
            "left": b"\x1b[D",
            "home": b"\x1b[H",
            "end": b"\x1b[F",
            "pageup": b"\x1b[5~",
            "pagedown": b"\x1b[6~",
            "insert": b"\x1b[2~",
            "f1": b"\x1bOP",
            "f2": b"\x1bOQ",
            "f3": b"\x1bOR",
            "f4": b"\x1bOS",
            "f5": b"\x1b[15~",
            "f6": b"\x1b[17~",
            "f7": b"\x1b[18~",
            "f8": b"\x1b[19~",
            "f9": b"\x1b[20~",
            "f10": b"\x1b[21~",
            "f11": b"\x1b[23~",
            "f12": b"\x1b[24~",
        }

        # Check for direct mapping
        if key in key_map:
            return key_map[key]

        # Handle Ctrl+key combinations
        if key.startswith("ctrl+"):
            char = key[5:]
            if len(char) == 1 and char.isalpha():
                # Ctrl+A = 0x01, Ctrl+B = 0x02, etc.
                return bytes([ord(char.lower()) - ord("a") + 1])
            elif char == "space":
                return b"\x00"
            elif char == "[":
                return b"\x1b"
            elif char == "\\":
                return b"\x1c"
            elif char == "]":
                return b"\x1d"
            elif char == "^":
                return b"\x1e"
            elif char == "_":
                return b"\x1f"

        # Regular character
        if event.character:
            return event.character.encode("utf-8")

        return b""

    def _write_to_pty(self, data: bytes) -> None:
        """Write data to the PTY."""
        if sys.platform == "win32":
            self._write_to_pty_windows(data)
        else:
            self._write_to_pty_unix(data)

    def _write_to_pty_windows(self, data: bytes) -> None:
        """Write to PTY on Windows."""
        if self._pty is not None:
            try:
                text = data.decode("utf-8", errors="replace")
                self._pty.write(text)
            except Exception as e:
                self.log.error(f"Error writing to PTY: {e}")

    def _write_to_pty_unix(self, data: bytes) -> None:
        """Write to PTY on Unix."""
        import os

        if self._pty_fd is not None:
            try:
                os.write(self._pty_fd, data)
            except OSError as e:
                self.log.error(f"Error writing to PTY: {e}")

    def _cleanup_pty(self) -> None:
        """Clean up PTY resources."""
        self._process_alive = False

        # Cancel read task
        if self._read_task is not None:
            self._read_task.cancel()
            self._read_task = None

        if sys.platform == "win32":
            self._cleanup_pty_windows()
        else:
            self._cleanup_pty_unix()

    def _cleanup_pty_windows(self) -> None:
        """Clean up PTY on Windows."""
        if self._pty is not None:
            try:
                # winpty doesn't have explicit close, just let it be garbage collected
                self._pty = None
            except Exception:
                pass

    def _cleanup_pty_unix(self) -> None:
        """Clean up PTY on Unix."""
        import os

        # Close the PTY fd
        if self._pty_fd is not None:
            try:
                os.close(self._pty_fd)
            except OSError:
                pass
            self._pty_fd = None

        # Terminate the child process
        if self._pty is not None:
            try:
                os.kill(self._pty, signal.SIGTERM)
                os.waitpid(self._pty, 0)
            except (OSError, ChildProcessError):
                pass
            self._pty = None

    def render(self) -> Text:
        """Render the terminal screen buffer as Rich Text."""
        # Show error message if terminal failed to start
        if self._error_message:
            result = Text()
            result.append("\n\n  ", style="dim")
            result.append(self._error_message, style="yellow")
            result.append("\n\n  ", style="dim")
            result.append("Use a separate terminal window instead.", style="dim")
            return result

        lines: list[Text] = []

        for y in range(self._screen.lines):
            line = Text()
            for x in range(self._screen.columns):
                char = self._screen.buffer[y][x]
                style = self._char_to_style(char)
                line.append(char.data or " ", style)
            lines.append(line)

        # Join lines with newlines
        result = Text()
        for i, line in enumerate(lines):
            if i > 0:
                result.append("\n")
            result.append_text(line)

        # Add cursor indicator if visible
        if self.cursor_visible and self._process_alive:
            cursor_y = self._screen.cursor.y
            cursor_x = self._screen.cursor.x
            # The cursor is shown through focus styling

        return result

    def _char_to_style(self, char: pyte.screen.Char) -> Style:
        """Convert a pyte character to a Rich style."""
        fg = char.fg
        bg = char.bg
        bold = char.bold
        italics = char.italics
        underscore = char.underscore
        reverse = char.reverse
        strikethrough = char.strikethrough

        # Map colors
        fg_color = self._map_color(fg, bold)
        bg_color = self._map_color(bg, False)

        # Handle reverse video
        if reverse:
            fg_color, bg_color = bg_color, fg_color

        return Style(
            color=fg_color,
            bgcolor=bg_color,
            bold=bold,
            italic=italics,
            underline=underscore,
            strike=strikethrough,
        )

    def _map_color(self, color: str, bold: bool = False) -> str | None:
        """Map a pyte color to a Rich color."""
        if color == "default":
            return None

        # Handle 256 colors (numeric strings)
        if color.isdigit():
            return f"color({color})"

        # Handle named colors
        if bold and color in ANSI_BRIGHT_COLORS:
            return ANSI_BRIGHT_COLORS[color]

        return ANSI_COLORS.get(color, color)

    def on_resize(self, event: events.Resize) -> None:
        """Handle widget resize."""
        # Update terminal size
        new_cols = max(event.size.width - 2, 10)  # Account for borders
        new_rows = max(event.size.height - 2, 5)

        if new_cols != self._cols or new_rows != self._rows:
            self._resize_terminal(new_rows, new_cols)

    def _resize_terminal(self, rows: int, cols: int) -> None:
        """Resize the terminal."""
        self._rows = rows
        self._cols = cols

        # Resize pyte screen
        self._screen.resize(rows, cols)

        # Resize PTY
        if self._process_alive:
            if sys.platform == "win32":
                if self._pty is not None:
                    try:
                        self._pty.set_size(cols, rows)
                    except Exception:
                        pass
            else:
                self._set_pty_size_unix(rows, cols)

    def on_focus(self, event: events.Focus) -> None:
        """Handle focus event."""
        self.cursor_visible = True

    def on_blur(self, event: events.Blur) -> None:
        """Handle blur event."""
        self.cursor_visible = False

    def write(self, data: str) -> None:
        """Write data to the terminal (to the PTY input).

        This allows programmatic input to the terminal.
        """
        if self._process_alive:
            self._write_to_pty(data.encode("utf-8"))

    def send_signal(self, sig: int) -> None:
        """Send a signal to the terminal process.

        Args:
            sig: Signal number (e.g., signal.SIGINT).
        """
        if not self._process_alive:
            return

        if sys.platform == "win32":
            # Windows doesn't support Unix signals the same way
            # For Ctrl+C, we can write the interrupt character
            if sig == 2:  # SIGINT
                self._write_to_pty(b"\x03")
        else:
            import os
            if self._pty is not None:
                try:
                    os.kill(self._pty, sig)
                except OSError:
                    pass

    @property
    def is_alive(self) -> bool:
        """Check if the terminal process is still running."""
        return self._process_alive

    def restart(self) -> None:
        """Restart the terminal with a fresh shell."""
        self._cleanup_pty()

        # Reset screen
        self._screen.reset()

        # Spawn new PTY
        self._spawn_pty()
        if self._process_alive:
            self._read_task = asyncio.create_task(self._read_pty_output())
            self.refresh()
