import curses
import textwrap

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from mcp_server_webcrawl.interactive.ui import DocumentMode, ThemeDefinition, ViewBounds
from mcp_server_webcrawl.interactive.views.base import BaseCursesView, CONTENT_MARGIN
from mcp_server_webcrawl.interactive.highlights import HighlightProcessor, HighlightSpan
from mcp_server_webcrawl.models.resources import ResourceResult
from mcp_server_webcrawl.interactive.ui import safe_addstr
if TYPE_CHECKING:
    from mcp_server_webcrawl.interactive.session import InteractiveSession

DOCUMENT_MODE_NEXT: dict[DocumentMode, DocumentMode] = {
    DocumentMode.MARKDOWN: DocumentMode.RAW,
    DocumentMode.RAW: DocumentMode.HEADERS,
    DocumentMode.HEADERS: DocumentMode.MARKDOWN
}

@dataclass
class DocumentLineData:
    """
    Container for processed document line data with highlights.
    """
    original_line: str
    clean_text: str
    highlights: list[HighlightSpan]


class SearchDocumentView(BaseCursesView):
    """
    Document viewer with markdown/raw/headers modes, scrolling support, and search highlighting.
    """

    def __init__(self, session: 'InteractiveSession'):
        """
        Initialize the document view.
        
        Args:
            session: The interactive session instance
        """
        super().__init__(session)
        self.__document: Optional[ResourceResult] = None
        self.__scroll_offset: int = 0
        self.__document_mode: DocumentMode = DocumentMode.MARKDOWN
        self.__cached_content_lines: Optional[list[str]] = None
        self.__cached_mode: Optional[DocumentMode] = None
        self.__cached_query: Optional[str] = None
        self.__search_terms: list[str] = []

    @property
    def document_mode(self) -> DocumentMode:
        return self.__document_mode

    @property
    def scroll_offset(self) -> int:
        return self.__scroll_offset

    @property
    def url(self) -> str:
        return self.__document.url if self.__document else ""

    def clear(self) -> None:
        """
        Clear the document.
        """
        self.__document = None
        self.__scroll_offset = 0
        self.__invalidate_cache()

    def draw_inner_footer(self, stdscr: curses.window, bounds: ViewBounds, text: str) -> None:
        """
        Draw document footer with scroll position and mode switcher.
        
        Args:
            stdscr: The curses window to draw on
            bounds: The view bounds defining the drawing area
            text: The footer text to display
        """
        if not self.__document:
            super().draw_inner_footer(stdscr, bounds, text)
            return

        style: int = self._get_inner_header_style()
        footer_y: int = bounds.y + bounds.height - 1

        terminal_height: int
        terminal_height, _ = stdscr.getmaxyx()
        if footer_y >= terminal_height:
            return

        content_lines: list[str] = self.__get_content_lines()
        content_height: int = max(0, bounds.height - 4)
        total_lines: int = len(content_lines)
        showing_start: int = self.__scroll_offset + 1
        showing_end: int = min(total_lines, self.__scroll_offset + content_height)
        left_info: str = f"Viewing lines {showing_start}-{showing_end} of {total_lines}"
        modes: list[tuple[str, DocumentMode]] = [
            (" MD ", DocumentMode.MARKDOWN),
            (" RAW ", DocumentMode.RAW),
            (" HDR ", DocumentMode.HEADERS)
        ]

        mode_buttons_width: int = sum(len(mode_name) for mode_name, _ in modes)

        mode_start_x: int = bounds.width - mode_buttons_width - 1
        document_mode_style: int = self.session.get_theme_color_pair(ThemeDefinition.DOCUMENT_MODE)
        safe_addstr(stdscr, footer_y, 0, self._get_bounded_line(), style)
        safe_addstr(stdscr, footer_y, 1, left_info, style)
        if mode_start_x > len(left_info) + 3:
            current_x: int = mode_start_x
            for mode_name, mode_enum in modes:
                is_current: bool = self.__document_mode == mode_enum
                mode_style: int = document_mode_style if is_current else style
                if current_x + len(mode_name) <= bounds.width:
                    safe_addstr(stdscr, footer_y, current_x, mode_name, mode_style)
                current_x += len(mode_name)

    def handle_input(self, key: int) -> bool:
        """
        Handle document navigation input.
        
        Args:
            key: The curses key code from user input
            
        Returns:
            bool: True if the input was handled, False otherwise
        """
        if not self._focused or not self.__document:
            return False

        handlers: dict[int, callable] = {
            curses.KEY_UP: self.__scroll_up,
            curses.KEY_DOWN: self.__scroll_down,
            curses.KEY_LEFT: self.__jump_to_previous_highlight,
            curses.KEY_RIGHT: self.__jump_to_next_highlight,
            curses.KEY_PPAGE: lambda: self.__scroll_page_up(max(1, self.bounds.height - 4)),
            curses.KEY_NPAGE: lambda: self.__scroll_page_down(max(1, self.bounds.height - 4)),
            curses.KEY_HOME: self.__scroll_to_top,
            curses.KEY_END: self.__scroll_to_bottom,
            ord('\t'): self.__cycle_mode,
        }

        handler = handlers.get(key)
        if handler:
            handler()
            return True

        return False

    def render(self, stdscr: curses.window) -> None:
        """
        Render the document view within bounds with search highlighting.
        
        Args:
            stdscr: The curses window to draw on
        """
        if not self._renderable(stdscr):
            return
        if not self.__document:
            self.__render_no_document(stdscr)
            return

        xb: int = self.bounds.x
        yb: int = self.bounds.y
        y_current: int = yb + 2
        y_max: int = yb + self.bounds.height

        content_height: int = max(0, self.bounds.height - 4)
        content_width: int = self.bounds.width - 4
        content_lines: list[str] = self.__get_content_lines()
        visible_lines: list[str] = content_lines[self.__scroll_offset: self.__scroll_offset + content_height]

        self.__update_search_terms()

        for i, line in enumerate(visible_lines):
            line_y: int = y_current + i
            if line_y >= self.bounds.height:
                break

            if self.__search_terms and line.strip():
                self.__render_line_with_highlights(stdscr, line, line_y, 2, content_width)
            else:
                display_line: str = line[:content_width] if len(line) > content_width else line
                safe_addstr(stdscr, line_y, 2, display_line)

    def update(self, document: ResourceResult) -> None:
        """
        Update the document and reset scroll position.
        
        Args:
            document: The resource result document to display
        """
        self.__document = document
        self.__scroll_offset = 0
        self.__invalidate_cache()

    def __calculate_max_scroll(self) -> int:
        """
        Calculate maximum scroll offset based on content and view size.
        
        Returns:
            int: The maximum scroll offset value
        """
        if not self.__document:
            return 0

        content_lines: list[str] = self.__get_content_lines()
        content_height: int = max(0, self.bounds.height - 4)

        return max(0, len(content_lines) - content_height)

    def __cycle_mode(self) -> None:
        """
        Cycle to the next document mode.
        """
        self.__document_mode = DOCUMENT_MODE_NEXT.get(
            self.__document_mode,
            DocumentMode.MARKDOWN
        )
        self.__scroll_offset = 0
        self.__invalidate_cache()

    def __get_content_lines(self) -> list[str]:
        """
        Get content lines based on current mode with caching.
        
        Returns:
            list[str]: The content lines for the current document mode
        """
        current_query: str = self.session.searchform.query if hasattr(self.session, 'searchform') else ""

        if (self.__cached_content_lines is not None and
            self.__cached_mode == self.__document_mode and
            self.__cached_query == current_query):
            return self.__cached_content_lines

        if not self.__document:
            return []

        content_lines: list[str]
        if self.__document_mode == DocumentMode.MARKDOWN:
            content_lines = self.__get_markdown_lines()
        elif self.__document_mode == DocumentMode.RAW:
            content_lines = self.__get_raw_lines()
        elif self.__document_mode == DocumentMode.HEADERS:
            content_lines = self.__get_header_lines()
        else:
            content_lines = ["Unknown document mode"]

        self.__cached_content_lines = content_lines
        self.__cached_mode = self.__document_mode
        self.__cached_query = current_query

        return content_lines

    def __get_header_lines(self) -> list[str]:
        """
        Get headers with proper wrapping.
        
        Returns:
            list[str]: The wrapped header lines
        """
        if not self.__document.headers:
            return ["No headers available for this resource."]

        return self.__wrap_text_content(self.__document.headers)

    def __get_markdown_lines(self) -> list[str]:
        """
        Get markdown content with proper wrapping.
        
        Returns:
            list[str]: The wrapped markdown content lines
        """
        raw_markdown: str = self.__document.get_extra("markdown")
        if not raw_markdown:
            return ["", "Markdown unavailable for this resource."]

        return self.__wrap_text_content(raw_markdown)

    def __get_raw_lines(self) -> list[str]:
        """
        Get raw content with proper wrapping.
        
        Returns:
            list[str]: The wrapped raw content lines
        """
        if not self.__document.content:
            return ["No raw content available for this resource."]

        return self.__wrap_text_content(self.__document.content.strip())

    def __invalidate_cache(self) -> None:
        """
        Invalidate cached content lines.
        """
        self.__cached_content_lines = None
        self.__cached_mode = None
        self.__cached_query = None

    def __jump_to_next_highlight(self) -> None:
        """
        Jump to next highlight, positioning it at line 5 of screen.
        """
        if not self.__search_terms:
            return

        content_lines: list[str] = self.__get_content_lines()
        current_line: int = self.__scroll_offset + 3

        for line_num in range(current_line + 1, len(content_lines)):
            highlights: list[HighlightSpan] = HighlightProcessor.find_highlights_in_text(
                content_lines[line_num],
                self.__search_terms
            )
            if highlights:
                self.__scroll_offset = max(0, line_num - 3)
                return

        for line_num in range(0, current_line + 1):
            highlights: list[HighlightSpan] = HighlightProcessor.find_highlights_in_text(
                content_lines[line_num],
                self.__search_terms
            )
            if highlights:
                self.__scroll_offset = max(0, line_num - 3)
                return

    def __jump_to_previous_highlight(self) -> None:
        """
        Jump to previous highlight, positioning it at line 5 of screen.
        """
        if not self.__search_terms:
            return

        content_lines: list[str] = self.__get_content_lines()
        current_line: int = self.__scroll_offset + 3

        for line_num in range(current_line - 1, -1, -1):
            highlights: list[HighlightSpan] = HighlightProcessor.find_highlights_in_text(
                content_lines[line_num],
                self.__search_terms
            )
            if highlights:
                self.__scroll_offset = max(0, line_num - 3)
                return

        for line_num in range(len(content_lines) - 1, current_line - 1, -1):
            highlights: list[HighlightSpan] = HighlightProcessor.find_highlights_in_text(
                content_lines[line_num],
                self.__search_terms
            )
            if highlights:
                self.__scroll_offset = max(0, line_num - 3)
                return

    def __render_line_with_highlights(self, stdscr: curses.window, line: str, y: int, x: int, max_width: int) -> None:
        """
        Render a line with search term highlighting using the shared utility.
        
        Args:
            stdscr: The curses window to draw on
            line: The text line to render
            y: Y position to render at
            x: X position to render at
            max_width: Maximum width for rendering
        """
        if not line.strip():
            return

        highlights: list[HighlightSpan] = HighlightProcessor.find_highlights_in_text(line, self.__search_terms)
        normal_style: int = curses.A_NORMAL
        highlight_style: int = self.session.get_theme_color_pair(ThemeDefinition.SNIPPET_HIGHLIGHT)
        HighlightProcessor.render_text_with_highlights(
            stdscr, line, highlights, x, y, max_width, normal_style, highlight_style
        )

    def __render_no_document(self, stdscr: curses.window) -> None:
        """
        Render message when no document is loaded.
        
        Args:
            stdscr: The curses window to draw on
        """
        x: int = self.bounds.x
        y: int = self.bounds.y
        width: int = self.bounds.width
        height: int = self.bounds.height

        if height > 2 and width > 20:
            safe_addstr(stdscr, y + 2, x + 2, "No document loaded.", curses.A_DIM)

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

    def __update_search_terms(self) -> None:
        """
        Update search terms from current search form query using shared utility.
        """
        if hasattr(self.session, 'searchform') and self.session.searchform:
            query: str = self.session.searchform.query
            self.__search_terms = HighlightProcessor.extract_search_terms(query)
        else:
            self.__search_terms = []

    def __wrap_text_content(self, raw_text: str) -> list[str]:
        """
        Wrap text content for display with proper line handling.
        
        Args:
            raw_text: The raw text content to wrap
            
        Returns:
            list[str]: The wrapped text lines
        """
        if not raw_text:
            return []

        content_width: int = max(20, self.bounds.width - CONTENT_MARGIN)
        wrapped_lines: list[str] = []
        text_lines: list[str] = raw_text.split("\n")

        for line in text_lines:
            if not line.strip():
                wrapped_lines.append("")
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

        return wrapped_lines
