"""Animated spinner widget for loading states.

Uses the official Textual pattern with Rich's Spinner renderable.
See: https://textual.textualize.io/blog/2022/11/24/spinners-and-progress-bars-in-textual/
"""

from typing import Optional

from rich.spinner import Spinner as RichSpinner
from textual.timer import Timer
from textual.widgets import Static


class Spinner(Static):
    """Animated spinner showing loading state.

    Uses Rich's Spinner renderable with 60fps refresh for smooth animation.
    """

    DEFAULT_CSS = """
    Spinner {
        width: 2;
        height: 1;
        content-align: center middle;
    }
    """

    def __init__(
        self,
        style: str = "dots",
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ) -> None:
        self._spinner = RichSpinner(style)
        self._timer: Optional[Timer] = None
        self._is_spinning = False
        super().__init__(id=id, classes=classes)

    def render(self) -> RichSpinner | str:
        """Render spinner or empty space."""
        if self._is_spinning:
            return self._spinner
        return " "

    def start(self) -> None:
        """Start the spinner animation."""
        if self._is_spinning:
            return
        self._is_spinning = True
        # 60fps refresh rate per Textual best practices
        self._timer = self.set_interval(1 / 60, self.refresh)

    def stop(self) -> None:
        """Stop the spinner animation."""
        if not self._is_spinning:
            return
        self._is_spinning = False
        if self._timer:
            self._timer.stop()
            self._timer = None
        self.refresh()

    @property
    def is_spinning(self) -> bool:
        """Check if spinner is currently animating."""
        return self._is_spinning
