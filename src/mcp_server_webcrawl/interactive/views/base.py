import re
import curses

from abc import abstractmethod
from typing import TYPE_CHECKING

from mcp_server_webcrawl import __name__ as module_name, __version__ as module_version
from mcp_server_webcrawl.interactive.ui import ThemeDefinition, ViewBounds
from mcp_server_webcrawl.models.resources import ResourceResult
from mcp_server_webcrawl.interactive.ui import safe_addstr

if TYPE_CHECKING:
    from mcp_server_webcrawl.interactive.session import InteractiveSession

REGEX_DISPLAY_URL_CLEAN = re.compile(r"^https?://|/$")
OUTER_WIDTH_RIGHT_MARGIN = 1

LAYOUT_FOOTER_SEPARATOR = " | "
LAYOUT_FOOTER_SEPARATOR_LENGTH = len(LAYOUT_FOOTER_SEPARATOR)
MIN_TERMINAL_HEIGHT = 8
MIN_TERMINAL_WIDTH = 40
CONTENT_MARGIN = 4

class BaseCursesView:
    """
    Base class for all views with common interface.
    """

    def __init__(self, session: 'InteractiveSession'):
        self.session = session
        self.bounds = ViewBounds(x=0, y=0, width=0, height=0)
        self._focused = False
        self._selected_index: int = 0

    @property
    def focused(self) -> bool:
        return self._focused

    def set_bounds(self, bounds: ViewBounds):
        """
        Set the rendering bounds for this view.
        
        Args:
            bounds: The ViewBounds object defining the drawing area
        """
        self.bounds = bounds

    def set_focused(self, focused: bool):
        """
        Set the focus state for this view.
        
        Args:
            focused: True if this view should be focused, False otherwise
        """
        self._focused = focused

    @abstractmethod
    def render(self, stdscr: curses.window) -> None:
        """
        Render the view within its bounds.
        
        Args:
            stdscr: The curses window to render on
        """
        pass

    @abstractmethod
    def handle_input(self, key: int) -> bool:
        """
        Handle input. Return True if consumed, False to pass through.
        
        Args:
            key: The input key code
            
        Returns:
            bool: True if input was consumed, False to pass through
        """
        pass

    def focusable(self) -> bool:
        """
        Return True if this view can receive focus.
        
        Returns:
            bool: True if this view can receive focus
        """
        return True

    def draw_outer_footer(self, stdscr: curses.window, text: str) -> None:
        """
        Draw context-sensitive help footer with pipe-separated items.
        
        Args:
            stdscr: The curses window to draw on
            text: The footer text to display (pipe-separated items)
        """
        height, width = stdscr.getmaxyx()
        footer_line: int = height - 1
        footer_line_text: str = BaseCursesView._get_full_width_line(stdscr)
        outer_theme_pair: int = self.session.get_theme_color_pair(ThemeDefinition.HEADER_OUTER)

        safe_addstr(stdscr, footer_line, 0, footer_line_text, outer_theme_pair)
        items = [item.strip() for item in text.split(LAYOUT_FOOTER_SEPARATOR)]
        available_width = width - 4 - 2  # 4 for right margin, 2 for left padding

        display_text: str = ""
        test_text: str = ""
        test_text_length: int = 0
        for i in range(len(items)):
            test_text = LAYOUT_FOOTER_SEPARATOR.join(items[:i+1])
            test_text_length = len(test_text)
            if test_text_length <= available_width:
                display_text = test_text
            else:
                break

         # doesn't fit indicator
        display_text_length: int = len(display_text)
        if test_text_length > available_width:
            display_text += f"{(width - display_text_length - 5) * ' '} »"

        if display_text:
            outer_header_theme_pair: int = self.session.get_theme_color_pair(ThemeDefinition.HEADER_OUTER)
            safe_addstr(stdscr, footer_line, 1, display_text, outer_header_theme_pair)

    def draw_outer_header(self, stdscr: curses.window) -> None:
        """
        Draw the inner header for this view section.
        
        Args:
            stdscr: The curses window to draw on
        """
        _, width = stdscr.getmaxyx()
        style: int = self.session.get_theme_color_pair(ThemeDefinition.HEADER_OUTER)

        full_width_line: str = BaseCursesView._get_full_width_line(stdscr)
        header_label_text: str = f"{module_name} --interactive"
        header_version_text: str = f"v{module_version}"
        header_version_x: int = max(0, width - len(header_version_text) - 2)

        safe_addstr(stdscr, 0, 0, full_width_line, style)
        if len(header_label_text) < width - 2:
            safe_addstr(stdscr, 0, 1, header_label_text, style)

        if header_version_x > len(header_label_text) + 3:
            safe_addstr(stdscr, 0, header_version_x, header_version_text, style)

    def draw_inner_footer(self, stdscr: curses.window, bounds: ViewBounds, text: str) -> None:
        """
        Draw context-sensitive help footer.
        
        Args:
            stdscr: The curses window to draw on
            bounds: The view bounds defining the drawing area
            text: The footer text to display
        """
        footer_y: int = bounds.y + bounds.height - 1
        line_of_whitespace: str = self._get_bounded_line()
        display_text: str = text or ""
        display_text_max: int = len(line_of_whitespace) - 2
        if len(display_text) > display_text_max:
            display_text = f"{display_text[:display_text_max - 1]}…"

        line: str = f" {display_text}".ljust(len(line_of_whitespace))
        safe_addstr(stdscr, footer_y, bounds.x, line, self._get_inner_header_style())

    def draw_inner_header(self, stdscr: curses.window, bounds: ViewBounds, text: str) -> None:
        """
        Draw the application header with module name and version.
        
        Args:
            stdscr: The curses window to draw on
            bounds: The view bounds defining the drawing area
            text: The header text to display
        """

        line_of_whitespace: str = self._get_bounded_line()
        display_text: str = text or ""
        max_text_width: int = len(line_of_whitespace) - 2
        if len(display_text) > max_text_width:
            display_text = f"{display_text[:max_text_width - 1]}…"

        line: str = f" {display_text}".ljust(len(line_of_whitespace))
        safe_addstr(stdscr, bounds.y, bounds.x, line, self._get_inner_header_style())


    @staticmethod
    def _get_full_width_line(stdscr: curses.window) -> str:
        """
        Get a line that fills the terminal width.
        
        Args:
            stdscr: The curses window to get dimensions from
            
        Returns:
            str: A string of spaces filling the terminal width
        """
        _, width = stdscr.getmaxyx()
        return " " * (width - OUTER_WIDTH_RIGHT_MARGIN)

    @staticmethod
    def url_for_display(url: str) -> str:
        """
        Remove protocol prefix and trailing slash from URL for display.
        
        Args:
            url: The URL to clean for display
            
        Returns:
            str: The cleaned URL without protocol and trailing slash
        """
        return REGEX_DISPLAY_URL_CLEAN.sub("", url)

    @staticmethod
    def humanized_bytes(result: ResourceResult) -> str:
        """
        Convert resource size to human-readable format (B, KB, MB).
        
        Args:
            result: The ResourceResult containing size information
            
        Returns:
            str: Human-readable size string (e.g., "1.5MB", "512KB", "128B")
        """
        display: str = ""
        if result is not None:
            size: int = result.size
            if isinstance(size, int):
                if size >= 1024 * 1024:
                    display = f"{size/(1024*1024):.1f}MB"
                elif size >= 1024:
                    display = f"{size/1024:.1f}KB"
                else:
                    display = f"{size}B"
        return display

    def _get_inner_header_style(self) -> int:
        """
        Get the appropriate header style based on focus state.
        
        Returns:
            int: The theme color pair for the header
        """
        if self._focused == True:
            return self.session.get_theme_color_pair(ThemeDefinition.HEADER_ACTIVE)
        else:
            return self.session.get_theme_color_pair(ThemeDefinition.HEADER_INACTIVE)

    def _get_input_style(self) -> int:
        """
        Get the appropriate input style based on focus and selection state.
        
        Returns:
            int: The style attributes for input rendering
        """
        if self._focused and self._selected_index == 0:
            return curses.A_REVERSE
        else:
            return self.session.get_theme_color_pair(ThemeDefinition.INACTIVE_QUERY)

    def _get_bounded_line(self) -> str:
        """
        Get a line of spaces that fits within the view bounds.
        
        Returns:
            str: A string of spaces matching the view width
        """
        return " " * self.bounds.width

    def _renderable(self, stdscr: curses.window) -> bool:
        """
        Check if the view can be rendered within the current terminal bounds.
        
        Args:
            stdscr: The curses window to check dimensions against
            
        Returns:
            bool: True if the view can be rendered, False otherwise
        """
        terminal_height, terminal_width = stdscr.getmaxyx()
        if self.bounds.y >= terminal_height or self.bounds.x >= terminal_width or self.bounds.width <= 0 or self.bounds.height <= 0:
            return False
        return True
