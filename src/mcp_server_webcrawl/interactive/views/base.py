import re
import curses

from abc import ABC, abstractmethod
from typing import Optional

from mcp_server_webcrawl import __name__ as module_name, __version__ as module_version
from mcp_server_webcrawl.interactive.actions import Action
from mcp_server_webcrawl.interactive.ui import (
    OUTER_WIDTH_RIGHT_MARGIN, Theme, ThemeDefinition, ViewBounds, safe_addstr, truncate,
)

REGEX_DISPLAY_URL_CLEAN = re.compile(r"^https?://|/$")

LAYOUT_FOOTER_SEPARATOR = " | "
MIN_TERMINAL_HEIGHT = 8
MIN_TERMINAL_WIDTH = 40
CONTENT_MARGIN = 4

# horizontal room a band reserves: one space of left padding, one of right.
BAND_TEXT_MARGIN = 2

_BYTES_PER_KB = 1024
_BYTES_PER_MB = 1024 * 1024


def humanized_bytes(size: Optional[int]) -> str:
    """
    Format a byte count as B / KB / MB. Returns "" for None or non-int input.
    """
    if not isinstance(size, int):
        return ""
    if size >= _BYTES_PER_MB:
        return f"{size / _BYTES_PER_MB:.1f}MB"
    if size >= _BYTES_PER_KB:
        return f"{size / _BYTES_PER_KB:.1f}KB"
    return f"{size}B"


def full_width_line(stdscr: curses.window) -> str:
    """
    A run of spaces filling the terminal width (minus the outer margin).
    """
    _, width = stdscr.getmaxyx()
    return " " * (width - OUTER_WIDTH_RIGHT_MARGIN)


def draw_outer_header(stdscr: curses.window, theme: Theme) -> None:
    """
    Top chrome row: module name on the left, version on the right.
    """
    _, width = stdscr.getmaxyx()
    style = theme.color(ThemeDefinition.HEADER_OUTER)

    label = f"{module_name} --interactive"
    version = f"v{module_version}"
    version_x = max(0, width - len(version) - 2)

    safe_addstr(stdscr, 0, 0, full_width_line(stdscr), style)
    if len(label) < width - 2:
        safe_addstr(stdscr, 0, 1, label, style)
    if version_x > len(label) + 3:
        safe_addstr(stdscr, 0, version_x, version, style)


def draw_outer_footer(stdscr: curses.window, theme: Theme, text: str) -> None:
    """
    Bottom chrome row: pipe-separated, context-sensitive help, truncated with a
    » indicator when it overflows.
    """
    height, width = stdscr.getmaxyx()
    footer_line = height - 1
    style = theme.color(ThemeDefinition.HEADER_OUTER)

    safe_addstr(stdscr, footer_line, 0, full_width_line(stdscr), style)

    items = [item.strip() for item in text.split(LAYOUT_FOOTER_SEPARATOR)]
    available_width = width - CONTENT_MARGIN - BAND_TEXT_MARGIN

    # keep the longest leading run of items that still fits
    display_text = ""
    overflowed = False
    for i in range(len(items)):
        candidate = LAYOUT_FOOTER_SEPARATOR.join(items[:i + 1])
        if len(candidate) <= available_width:
            display_text = candidate
        else:
            overflowed = True
            break

    if overflowed:
        pad = max(0, width - len(display_text) - 5)
        display_text += f"{' ' * pad} »"

    if display_text:
        safe_addstr(stdscr, footer_line, 1, display_text, style)


class BaseCursesView(ABC):
    """
    Base class for the renderable views. A view draws into its bounds and translates
    keystrokes into Actions (or None when a key is consumed with no app-level effect).
    It depends on a Theme for colors and never reaches into the session.
    """

    def __init__(self, theme: Theme):
        self.theme = theme
        self.bounds = ViewBounds(x=0, y=0, width=0, height=0)
        self._focused = False
        self._selected_index: int = 0

    @property
    def focused(self) -> bool:
        return self._focused

    def set_bounds(self, bounds: ViewBounds) -> None:
        """
        Set the rendering bounds for this view.
        """
        self.bounds = bounds

    def set_focused(self, focused: bool) -> None:
        """
        Set the focus state for this view.
        """
        self._focused = focused

    @abstractmethod
    def render(self, stdscr: curses.window) -> None:
        """
        Render the view within its bounds.
        """

    @abstractmethod
    def handle_input(self, key: int) -> Optional[Action]:
        """
        Handle a keystroke. Return an Action to request an app-level effect or None.
        """

    def draw_inner_header(self, stdscr: curses.window, bounds: ViewBounds, text: str) -> None:
        """
        Draw a single-line header band at the top of the given bounds.
        """
        self._draw_band(stdscr, bounds, bounds.y, text)

    def draw_inner_footer(self, stdscr: curses.window, bounds: ViewBounds, text: str) -> None:
        """
        Draw a single-line footer band at the bottom of the given bounds.
        """
        self._draw_band(stdscr, bounds, bounds.y + bounds.height - 1, text)

    def _draw_band(self, stdscr: curses.window, bounds: ViewBounds, y: int, text: str) -> None:
        """
        Draw one header/footer band: a full-width run in the band style with the text
        left-padded one space and truncated (with an ellipsis) to fit. Header and
        footer differ only in which row `y` they land on.
        """
        width = bounds.width
        label = truncate(text or "", width - BAND_TEXT_MARGIN)
        line = f" {label}".ljust(width)
        safe_addstr(stdscr, y, bounds.x, line, self._get_inner_header_style())

    @staticmethod
    def url_for_display(url: str) -> str:
        """
        Strip protocol prefix and trailing slash from a URL for display.
        """
        return REGEX_DISPLAY_URL_CLEAN.sub("", url)

    def _get_inner_header_style(self) -> int:
        """
        Header band style, brighter when this view is focused.
        """
        definition = ThemeDefinition.HEADER_ACTIVE if self._focused else ThemeDefinition.HEADER_INACTIVE
        return self.theme.color(definition)

    def _get_input_style(self, selected: bool) -> int:
        """
        Input field style: reversed when the field is the focused selection, else the
        inactive-query color. Callers pass whether the field in question is selected,
        rather than the base assuming a fixed field index.
        """
        if self._focused and selected:
            return curses.A_REVERSE
        return self.theme.color(ThemeDefinition.INACTIVE_QUERY)

    def _get_bounded_line(self) -> str:
        """
        A run of spaces matching this view's width.
        """
        return " " * self.bounds.width

    def _renderable(self, stdscr: curses.window) -> bool:
        """
        True when this view's bounds fall within the current terminal.
        """
        terminal_height, terminal_width = stdscr.getmaxyx()
        return not (
            self.bounds.y >= terminal_height
            or self.bounds.x >= terminal_width
            or self.bounds.width <= 0
            or self.bounds.height <= 0
        )
