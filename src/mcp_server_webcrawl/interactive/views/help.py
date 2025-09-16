import curses
import textwrap

from typing import TYPE_CHECKING

from mcp_server_webcrawl.interactive.views.base import CONTENT_MARGIN
from mcp_server_webcrawl.interactive.views.base import BaseCursesView
from mcp_server_webcrawl.interactive.ui import ThemeDefinition
from mcp_server_webcrawl.interactive.ui import safe_addstr
if TYPE_CHECKING:
    from mcp_server_webcrawl.interactive.session import InteractiveSession

INTERROBOT_LINK: str = "<https://interro.bot>"
HELP_CONTENT: str = """Boolean Search Syntax

The query engine supports field-specific (`field: value`) searches and complex boolean expressions. Fulltext is supported as a combination of the url, content, and headers fields.

Example Queries

| Query Example                | Description                           |
|------------------------------|---------------------------------------|
| privacy                      | Fulltext single keyword match         |
| "privacy policy"             | Fulltext exact phrase match           |
| boundar*                     | Fulltext wildcard (boundary,          |
|                              | boundaries, etc.)                     |
| id: 12345                    | Match specific resource by ID         |
| url: example.com/dir         | URL contains example.com/dir          |
| type: html                   | HTML pages only                       |
| status: 200                  | HTTP status equals 200                |
| status: >=400                | HTTP status >= 400                    |
| content: h1                  | Content contains h1                   |
| headers: text/xml            | Headers contain text/xml              |
| privacy AND policy           | Fulltext matches both terms           |
| privacy OR policy            | Fulltext matches either term          |
| policy NOT privacy           | Policy but not privacy                |
| (login OR signin) AND form   | Login/signin with form                |
| type: html AND status: 200   | HTML pages with HTTP success          |

Field Reference

`id`: Resource identifier (integer)
- Example: id: 12345

`url`: URL field matching
- Supports partial matches and wildcards
- Example: `url: example.com/about`
- Example: `url: *.pdf`

`type`: Resource type filtering
- Common types: html, img, script, style, font, audio, video, pdf, doc
- Example: `type: html`
- Example: `type: img`

`status`: HTTP status code
- Supports exact matches and comparisons
- Example: `status: 200`
- Example: `status: >=400`
- Example: `status: <300`

`content`: Full-text search within resource content
- Searches the actual content/body of resources
- Example: `content: "user login"`
- Example: `content: javascript`

`headers`: HTTP response headers search
- Searches within response headers
- Example: `headers: application/json`
- Example: `headers: gzip`

Boolean Operators

`AND`: Both terms must be present
- Example: `privacy AND policy`
- Example: `type: html AND status: 200`

`OR`: Either term can be present
- Example: `login OR signin`
- Example: `type: img OR type: video`

`NOT`: Exclude documents containing the term
- Example: `policy NOT privacy`
- Example: `type: html NOT status: 404`

`Parentheses`: Group expressions
- Example: `(login OR signin) AND (form OR page)`
- Example: `type: html AND (status: 200 OR status: 301)`

Wildcards

`Suffix wildcard` (*): Matches terms starting with the prefix
- Example: `admin*` matches admin, administrator, administration
- Example: `java*` matches java, javascript, javadoc

Tips

- Use quotes for exact phrase matching: `"privacy policy"`
- Combine field searches with fulltext: `type: html AND privacy`
- Use wildcards for partial matches: `admin*`
- Group complex expressions with parentheses
- Field names are case-sensitive, values are case-insensitive
- Whitespace around operators is optional: `A AND B` = `A AND B`

If you enjoy mcp-server-webcrawl --interactive, you will almost assuredly appreciate InterroBot crawler and analyzer <https://interro.bot>, by the same developer."""


class HelpView(BaseCursesView):
    """
    Interactive help view displaying scrollable documentation.
    """

    def __init__(self, session: 'InteractiveSession'):
        """
        Initialize the help view.
        
        Args:
            session: The interactive session instance
        """
        super().__init__(session)
        self._focused = True
        self.__scroll_offset: int = 0
        self.__cached_content_lines: list[str] | None = None

    def draw_inner_footer(self, stdscr: curses.window, bounds, text: str) -> None:
        """
        Draw footer with scroll position information.
        
        Args:
            stdscr: The curses window to draw on
            bounds: The view bounds defining the drawing area
            text: The footer text to display
        """
        if not self._focused:
            super().draw_inner_footer(stdscr, bounds, text)
            return

        content_lines: list[str] = self.__get_content_lines()
        content_height: int = max(0, bounds.height - 4)
        total_lines: int = len(content_lines)

        if total_lines == 0:
            super().draw_inner_footer(stdscr, bounds, text)
            return

        showing_start: int = self.__scroll_offset + 1
        showing_end: int = min(total_lines, self.__scroll_offset + content_height)

        footer_text: str = f"Viewing lines {showing_start}-{showing_end} of {total_lines}"

        footer_y: int = bounds.y + bounds.height - 1
        try:
            safe_addstr(stdscr, footer_y, 0, self._get_bounded_line(), self._get_inner_header_style())
            safe_addstr(stdscr, footer_y, 1, footer_text, self._get_inner_header_style())
        except curses.error:
            pass

    def handle_input(self, key: int) -> bool:
        """
        Handle document navigation input.
        
        Args:
            key: The curses key code from user input
            
        Returns:
            bool: True if the input was handled, False otherwise
        """
        if not self._focused:
            return False

        handlers: dict[int, callable] = {
            curses.KEY_UP: self.__scroll_up,
            curses.KEY_DOWN: self.__scroll_down,
            curses.KEY_PPAGE: lambda: self.__scroll_page_up(max(1, self.bounds.height - 4)),
            curses.KEY_NPAGE: lambda: self.__scroll_page_down(max(1, self.bounds.height - 4)),
            curses.KEY_HOME: self.__scroll_to_top,
            curses.KEY_END: self.__scroll_to_bottom,
        }

        handler = handlers.get(key)
        if handler:
            handler()
            return True

        return False

    def render(self, stdscr: curses.window) -> None:
        """
        Render the help content as a scrollable document.
        
        Args:
            stdscr: The curses window to draw on
        """
        if not self._renderable(stdscr):
            return

        y_current: int = self.bounds.y + 2
        y_max: int = self.bounds.y + self.bounds.height - 1
        content_height: int = max(0, self.bounds.height - 4)
        content_width: int = self.bounds.width - 4
        content_lines: list[str] = self.__get_content_lines()
        visible_lines: list[str] = content_lines[self.__scroll_offset: self.__scroll_offset + content_height]

        for i, line in enumerate(visible_lines):

            line_y: int = y_current + i
            if line_y >= y_max:
                break

            display_line: str = line[:content_width] if len(line) > content_width else line
            display_line_is_bold: bool = line.startswith('##') or (line.startswith('**') and line.endswith('**') and len(line) > 4)
            default_line_style = curses.A_BOLD if display_line_is_bold else curses.A_NORMAL
            if INTERROBOT_LINK in line:
                link_index = line.index(INTERROBOT_LINK)
                safe_addstr(stdscr, line_y, 2, display_line, curses.A_NORMAL)
                safe_addstr(stdscr, line_y, 2 + link_index, INTERROBOT_LINK, self.session.get_theme_color_pair(ThemeDefinition.HELP_LINK))
            else:
                safe_addstr(stdscr, line_y, 2, display_line, default_line_style)

    def __calculate_max_scroll(self) -> int:
        """
        Calculate maximum scroll offset based on content and view size.
        
        Returns:
            int: The maximum scroll offset value
        """
        content_lines: list[str] = self.__get_content_lines()
        content_height: int = max(0, self.bounds.height - 4)
        return max(0, len(content_lines) - content_height)

    def __get_content_lines(self) -> list[str]:
        """
        Get wrapped content lines with caching.
        
        Returns:
            list[str]: The wrapped and cached content lines
        """
        if self.__cached_content_lines is not None:
            return self.__cached_content_lines

        content_width: int = max(20, self.bounds.width - CONTENT_MARGIN)
        wrapped_lines: list[str] = []
        text_lines: list[str] = HELP_CONTENT.split("\n")
        for line in text_lines:
            if not line.strip():
                wrapped_lines.append("")
            else:
                if (line.startswith('|') or
                    line.startswith('##') or
                    (line.startswith('**') and line.endswith('**'))):
                    wrapped_lines.append(line.rstrip())
                else:
                    wrapped: str = textwrap.fill(
                        line.rstrip(),
                        width=content_width,
                        expand_tabs=True,
                        replace_whitespace=False,
                        break_long_words=True,
                        break_on_hyphens=True
                    )
                    wrapped_lines.extend(wrapped.split("\n"))

        self.__cached_content_lines = wrapped_lines
        return wrapped_lines

    def __scroll_down(self, lines: int = 1) -> None:
        """
        Scroll down by specified number of lines.
        
        Args:
            lines: Number of lines to scroll down
        """
        max_scroll: int = self.__calculate_max_scroll()
        self.__scroll_offset = min(max_scroll, self.__scroll_offset + lines)

    def __scroll_page_down(self, page_size: int = 10) -> None:
        """
        Scroll down by page.
        
        Args:
            page_size: Number of lines to scroll for a page
        """
        self.__scroll_down(page_size)

    def __scroll_page_up(self, page_size: int = 10) -> None:
        """
        Scroll up by page.
        
        Args:
            page_size: Number of lines to scroll for a page
        """
        self.__scroll_up(page_size)

    def __scroll_to_bottom(self) -> None:
        """
        Scroll to bottom of document.
        """
        self.__scroll_offset = self.__calculate_max_scroll()

    def __scroll_to_top(self) -> None:
        """
        Scroll to top of document.
        """
        self.__scroll_offset = 0

    def __scroll_up(self, lines: int = 1) -> None:
        """
        Scroll up by specified number of lines.
        
        Args:
            lines: Number of lines to scroll up
        """
        self.__scroll_offset = max(0, self.__scroll_offset - lines)
