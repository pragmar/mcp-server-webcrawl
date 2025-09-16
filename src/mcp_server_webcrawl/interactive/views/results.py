import curses
import textwrap
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from mcp_server_webcrawl.interactive.ui import ThemeDefinition, UiState, ViewBounds
from mcp_server_webcrawl.interactive.views.base import BaseCursesView
from mcp_server_webcrawl.interactive.highlights import HighlightProcessor, HighlightSpan
from mcp_server_webcrawl.models.resources import ResourceResult
from mcp_server_webcrawl.interactive.ui import safe_addstr

if TYPE_CHECKING:
    from mcp_server_webcrawl.interactive.session import InteractiveSession

SEARCH_RESULT_SNIPPET_MARGIN: int = 6
SEARCH_RESULT_SNIPPET_MAX_LINES: int = 6

LAYOUT_ZERO_PAD_THRESHOLD = 10
LAYOUT_RESULT_METADATA_SPACING = 2
LAYOUT_RESULT_LINE_MARGIN = 2
LAYOUT_RESULT_WIDTH_BUFFER = 4
LAYOUT_FOOTER_MARGIN = 2
LAYOUT_FOOTER_TEXT_SPACING = 3
LAYOUT_HEADER_FOOTER_HEIGHT = 2
LAYOUT_STATUS_MESSAGE_X_OFFSET = 2

HTTP_ERROR_THRESHOLD = 500
HTTP_WARN_THRESHOLD = 400

TYPE_FIELD_WIDTH = 7
SIZE_FIELD_WIDTH = 7
URL_PADDING_BUFFER = 3

@dataclass
class SnippetData:
    """
    Container for processed snippet data.
    """
    clean_text: str
    highlights: list[HighlightSpan]
    wrapped_lines: list[str]

    def get_capped_line_count(self) -> int:
        """
        Get the line count capped at maximum allowed snippet lines.
        
        Returns:
            int: The minimum of wrapped lines count and maximum snippet lines
        """
        return min(len(self.wrapped_lines), SEARCH_RESULT_SNIPPET_MAX_LINES)


class SearchResultsView(BaseCursesView):
    """
    A renderable curses view, but takes cues from searchform, which will handle 
    all input on this screen.
    """

    def __init__(self, session: 'InteractiveSession'):
        """
        Initialize the search results view.
        
        Args:
            session: The interactive session instance
        """
        super().__init__(session)
        self.__results: list[ResourceResult] = []
        self.__results_total: int = 0
        self.__results_indexer_processed: int = 0
        self.__results_indexer_duration: float = 0
        self.__scroll_offset: int = 0
        self._focused: bool = False
        self.__displayed_results: int = 0

    @property
    def indexing_time(self) -> float:
        return self.__results_indexer_duration

    @property
    def results(self) -> list[ResourceResult]:
        return self.__results

    @property
    def results_total(self) -> int:
        return self.__results_total

    def clear(self) -> None:
        """
        Clear all results and reset state.
        """
        self.__results = []
        self.__results_total = 0
        self._selected_index = 0
        self.__scroll_offset = 0

    def draw_inner_footer(self, stdscr: curses.window, bounds: ViewBounds, text: str) -> None:
        """
        Draw footer with pagination on left and indexing info on right.
        
        Args:
            stdscr: The curses window to draw on
            bounds: The view bounds defining the drawing area
            text: The footer text to display
        """
        footer_y: int = bounds.y + bounds.height - 1
        safe_addstr(stdscr, footer_y, bounds.x, self._get_bounded_line(), self._get_inner_header_style())

        if not self.__results:
            left_text: str = ""
        else:
            searchform_offset: int = self.session.searchform.offset
            index_start: int = searchform_offset + 1  # 1-based indexing for display
            index_end: int = searchform_offset + len(self.__results)
            left_text = f"Displaying {index_start:,}-{index_end:,} of {self.__results_total:,}"

        if self.__results_indexer_processed > 0:
            duration_seconds: float = self.__results_indexer_duration
            right_text: str = f"{self.__results_indexer_processed:,} Indexed ({duration_seconds:.2f}s)"
        else:
            right_text = ""

        max_width: int = bounds.width - LAYOUT_FOOTER_MARGIN

        if left_text:
            if len(left_text) > max_width // 2:
                left_text = f"{left_text[:max_width // 2 - 1]}…"
            safe_addstr(stdscr, footer_y, bounds.x + 1, left_text, self._get_inner_header_style())

        if right_text:
            right_text_len: int = len(right_text)
            if right_text_len <= max_width:

                # right text doesn't overlap with left text
                min_right_x: int = bounds.x + 1 + len(left_text) + LAYOUT_FOOTER_TEXT_SPACING if left_text else bounds.x + 1
                right_x: int = max(min_right_x, bounds.x + bounds.width - right_text_len - 1)

                # draw if enough space
                if right_x + right_text_len < bounds.x + bounds.width:
                    safe_addstr(stdscr, footer_y, right_x, right_text, self._get_inner_header_style())

    def draw_inner_header(self, stdscr: curses.window, bounds: ViewBounds, text: str) -> None:
        """
        Draw the application header with results count on left and search time on right.
        
        Args:
            stdscr: The curses window to draw on
            bounds: The view bounds defining the drawing area
            text: The header text to display
        """
        header_y: int = bounds.y

        # write out a line, then update it
        safe_addstr(stdscr, header_y, bounds.x, self._get_bounded_line(), self._get_inner_header_style())

        # results count
        if self.__results and not (self.session.searchman.search_in_progress() or self.session.searchman.has_pending_search()):
            left_text: str = f"Results ({self.__results_total:,} Found)"
        else:
            left_text = "Results:"

         # 1 char margin on each side
        max_width: int = bounds.width - LAYOUT_FOOTER_MARGIN

        if left_text:
            if len(left_text) > max_width // 2:  # no more than half
                left_text = f"{left_text[:max_width // 2 - 1]}…"
            safe_addstr(stdscr, header_y, bounds.x + 1, left_text, self._get_inner_header_style())

    def get_selected_result(self) -> Optional[ResourceResult]:
        """
        Get the currently selected search result.
        
        Returns:
            Optional[ResourceResult]: The selected result or None if no valid selection
        """
        if 0 <= self._selected_index < len(self.__results):
            return self.__results[self._selected_index]
        return None

    def handle_input(self, key: int) -> bool:
        """
        Handle keyboard input for results navigation and selection.
        
        Args:
            key: The curses key code from user input
            
        Returns:
            bool: True if the input was handled, False otherwise
        """
        if not self._focused or not self.__results:
            return False

        def handle_page_previous() -> None:
            if self.session.searchform.page_previous():
                self.session.searchman.autosearch()

        def handle_page_next() -> None:
            if self.session.searchform.page_next(self.__results_total):
                self.session.searchman.autosearch()

        handlers: dict[int, callable] = {
            curses.KEY_LEFT: handle_page_previous,
            curses.KEY_RIGHT: handle_page_next,
            curses.KEY_UP: self.__select_previous,
            curses.KEY_DOWN: self.__select_next,
            ord('\n'): self.__handle_document_selection,
            ord('\r'): self.__handle_document_selection,
        }

        handler: Optional[callable] = handlers.get(key)
        if handler:
            handler()
            return True

        return False

    def render(self, stdscr: curses.window) -> None:
        """
        Render only the results content - headers/footers handled by session.
        
        Args:
            stdscr: The curses window to draw on
        """
        if not self._renderable(stdscr):
            return

        xb: int = self.bounds.x
        yb: int = self.bounds.y
        y_current: int = yb + 1

        # create content area excluding header/footer rows
        # header takes row 0, footer takes row height-1, content gets the middle
        if self.bounds.height <= LAYOUT_HEADER_FOOTER_HEIGHT:
            return

        # check if search is in progress
        is_searching: bool = (self.session.searchman.search_in_progress() or
               self.session.searchman.has_pending_search())

        message: str = ""
        if is_searching:
            message = "Searching…"
        elif not self.__results:
            message = "Indexing…" if self.__results_indexer_processed == 0 else "No results found."

        if message != "":
            safe_addstr(stdscr, y_current, LAYOUT_STATUS_MESSAGE_X_OFFSET, message, curses.A_DIM)
        else:
            self.__render_results_list(stdscr, y_current, 0)

    def update(self, results: list[ResourceResult], total: int, indexer_processed: int, indexer_duration: float) -> None:
        """
        Update the search results view with new data and reset selection.
        
        Args:
            results: List of search result resources for current page
            total: Total number of results across all pages
            indexer_processed: Number of resources processed during indexing
            indexer_duration: Time taken for indexing in seconds
        """
        self.__results = results
        self.__results_total = total
        self.__results_indexer_processed = indexer_processed
        self.__results_indexer_duration = indexer_duration
        self._selected_index = 0
        self.__scroll_offset = 0

    def __ensure_visible(self) -> None:
        """
        Ensure selected item is completely visible in viewport with line-by-line scrolling.
        """
        if not self.__results or self._selected_index >= len(self.__results):
            return

        result_line_positions: list[int] = []
        result_line_counts: list[int] = []
        current_line: int = 0

        for result in self.__results:
            result_line_positions.append(current_line)
            lines_for_this_result: int = 1
            current_line += 1

            snippet: Optional[str] = result.get_extra("snippets")
            if snippet and snippet.strip():
                snippet_data: SnippetData = self.__process_snippet(snippet)
                snippet_lines: int = min(len(snippet_data.wrapped_lines), SEARCH_RESULT_SNIPPET_MAX_LINES)
                lines_for_this_result += snippet_lines
                current_line += snippet_lines

            result_line_counts.append(lines_for_this_result)

        selected_start_line: int = result_line_positions[self._selected_index]
        selected_total_lines: int = result_line_counts[self._selected_index]
        selected_end_line: int = selected_start_line + selected_total_lines - 1
        visible_height: int = self.bounds.height - LAYOUT_HEADER_FOOTER_HEIGHT  # account for header/footer

        if selected_start_line < self.__scroll_offset:
            self.__scroll_offset = selected_start_line
        elif selected_end_line >= self.__scroll_offset + visible_height:
            self.__scroll_offset = max(0, selected_end_line - visible_height + 1)
            if self._selected_index + 1 < len(result_line_positions):
                next_result_line: int = result_line_positions[self._selected_index + 1]
                if next_result_line < self.__scroll_offset + visible_height:
                    self.__scroll_offset = min(self.__scroll_offset, next_result_line - visible_height + 1)

    def __handle_document_selection(self) -> None:
        """
        Handle document viewing when ENTER is pressed on a result.
        """
        selected_result: Optional[ResourceResult] = self.get_selected_result()
        if not selected_result or not selected_result.id:
            return

        selected_sites = self.session.searchform.get_selected_sites()
        site_ids: list[int] = [site.id for site in selected_sites] if selected_sites else []

        try:
            query: str = f"id: {selected_result.id}"
            query_api = self.session.crawler.get_resources_api(
                sites=site_ids if site_ids else None,
                query=query,
                offset=0,
                limit=1,
                fields=["headers", "content", "status", "size"],
                extras=["markdown"]
            )
            document_results: list[ResourceResult] = query_api.get_results()

            if document_results:
                self.session.document.update(document_results[0])
                self.session.set_ui_state(UiState.DOCUMENT)

        except Exception:
            pass

    def __process_snippet(self, snippet_text: str) -> SnippetData:
        """
        Process raw snippet text using shared highlight utility.
        
        Args:
            snippet_text: Raw snippet text with highlight markers
            
        Returns:
            SnippetData: Processed data with clean text, highlight positions, and wrapped lines
        """

        clean_text, highlights = HighlightProcessor.extract_snippet_highlights(snippet_text)

        snippet_width: int = self.bounds.width - (SEARCH_RESULT_SNIPPET_MARGIN * 2)
        wrapped_text: str = textwrap.fill(
            clean_text,
            width=snippet_width,
            expand_tabs=True,
            replace_whitespace=True,
            break_long_words=True,
            break_on_hyphens=True,
        )
        wrapped_lines: list[str] = wrapped_text.split("\n")

        return SnippetData(
            clean_text=clean_text,
            highlights=highlights,
            wrapped_lines=wrapped_lines
        )

    def __render_results_list(self, stdscr: curses.window, start_y: int, margin_x: int) -> None:
        """
        Render results with metadata and snippets, respecting scroll offset.
        
        Args:
            stdscr: The curses window to draw on
            start_y: Starting Y position for rendering
            margin_x: Left margin for content
        """

        xb: int = self.bounds.x
        yb: int = self.bounds.y
        y_current: int = start_y
        y_max: int = yb + self.bounds.height
        y_available: int = y_max - start_y
        searchform_offset: int = self.session.searchform.offset
        displayed_results: int = 0

        # for scrolling
        current_line: int = 0

        for result_index in range(len(self.__results)):
            if y_current >= start_y + y_available:
                break

            result: ResourceResult = self.__results[result_index]
            is_selected: bool = self._focused and result_index == self._selected_index
            global_result_num: int = searchform_offset + result_index + 1

            # check if skip due to scrolling
            if current_line < self.__scroll_offset:
                current_line += 1
                snippet: Optional[str] = result.get_extra("snippets")
                if snippet and snippet.strip():
                    snippet_data: SnippetData = self.__process_snippet(snippet)
                    current_line += snippet_data.get_capped_line_count()
                continue

            # leading zero for 01-09, natural 10+
            result_num: str
            if global_result_num < LAYOUT_ZERO_PAD_THRESHOLD:
                result_num = f"{global_result_num:02d}. "
            else:
                result_num = f"{global_result_num}. "

            url: str = result.url or "No URL"
            metadata_parts: list[tuple[str, int]] = []

            # resource type
            if result.type.value:
                type_str: str = f"[{result.type.value}]"
                type_str = f"{type_str:>{TYPE_FIELD_WIDTH}}"
                metadata_parts.append((type_str, curses.A_NORMAL))

            # file size
            humanized_bytes: str = BaseCursesView.humanized_bytes(result)
            if humanized_bytes and humanized_bytes != "0B":
                metadata_parts.append((f"{humanized_bytes:>{SIZE_FIELD_WIDTH}}", curses.A_NORMAL))

            # HTTP status
            status_style = curses.A_NORMAL
            if result.status >= HTTP_ERROR_THRESHOLD:
                status_style = self.session.get_theme_color_pair(ThemeDefinition.HTTP_ERROR)
            elif result.status >= HTTP_WARN_THRESHOLD:
                status_style = self.session.get_theme_color_pair(ThemeDefinition.HTTP_WARN)
            metadata_parts.append((str(result.status), status_style))

            metadata_text: str = "  ".join(part[0] for part in metadata_parts)

            line_x: int = margin_x + LAYOUT_RESULT_LINE_MARGIN
            available_width: int = min(self.bounds.width - LAYOUT_RESULT_WIDTH_BUFFER, self.bounds.width - line_x)
            selected_style: int = curses.A_REVERSE if is_selected else curses.A_NORMAL

            if metadata_parts:
                url_space: int = available_width - len(result_num) - len(metadata_text) - URL_PADDING_BUFFER
                if len(url) > url_space:
                    url = url[:max(0, url_space - 1)] + "…"
                padding: int = available_width - len(result_num) - len(url) - len(metadata_text)

                result_url_part: str = f"{result_num}{url}"
                safe_addstr(stdscr, y_current, line_x, result_url_part, selected_style)

                metadata_start_x: int = line_x + len(result_url_part)
                if padding > 0 and metadata_start_x < line_x + available_width:
                    safe_addstr(stdscr, y_current, metadata_start_x, " " * padding, curses.A_NORMAL)
                    metadata_start_x += padding

                for part_text, part_style in metadata_parts:
                    if metadata_start_x < line_x + available_width:
                        safe_addstr(stdscr, y_current, metadata_start_x, part_text, part_style)
                        metadata_start_x += len(part_text) + LAYOUT_RESULT_METADATA_SPACING
            else:
                url_space = available_width - len(result_num)
                if len(url) > url_space:
                    url = url[:max(0, url_space - 1)] + "…"
                result_line: str = f"{result_num}{url}"
                safe_addstr(stdscr, y_current, line_x, result_line[:available_width], selected_style)

            y_current += 1
            current_line += 1
            displayed_results += 1

            snippet = result.get_extra("snippets")
            if snippet and snippet.strip():
                if y_current < start_y + y_available and y_current < y_max:
                    snippet_data = self.__process_snippet(snippet)
                    snippet_lines: int = min(len(snippet_data.wrapped_lines), SEARCH_RESULT_SNIPPET_MAX_LINES)
                    lines_to_skip: int = max(0, self.__scroll_offset - current_line)

                    if lines_to_skip < snippet_lines:
                        lines_rendered: int = self.__render_snippet_with_highlights(stdscr, snippet_data, y_current)
                        y_current += lines_rendered
                        current_line += snippet_lines
                    else:
                        current_line += snippet_lines

        self.__displayed_results = displayed_results

    def __render_snippet_with_highlights(self, stdscr: curses.window, snippet_data: SnippetData, y: int) -> int:
        """
        Render a snippet using the processed snippet data with proper highlighting.
        
        Args:
            stdscr: The curses window to draw on
            snippet_data: Processed snippet data with highlights
            y: Starting Y position for rendering
            
        Returns:
            int: The number of lines actually rendered
        """
        lines_to_render: int = min(len(snippet_data.wrapped_lines), SEARCH_RESULT_SNIPPET_MAX_LINES)
        lines_rendered: int = 0

        snippet_default_pair: int = self.session.get_theme_color_pair(ThemeDefinition.SNIPPET_DEFAULT)
        snippet_highlight_pair: int = self.session.get_theme_color_pair(ThemeDefinition.SNIPPET_HIGHLIGHT)

        # track character position in the original clean text
        # this allows replacing ** highlights with natural text wrapping
        char_position: int = 0

        for i in range(lines_to_render):
            if i >= len(snippet_data.wrapped_lines):
                break

            line_text: str = snippet_data.wrapped_lines[i]
            if not line_text.strip():
                char_position += len(line_text) + 1  # +1 for newline
                continue

            current_y: int = y + i
            current_x: int = SEARCH_RESULT_SNIPPET_MARGIN
            line_highlights: list[dict[str, int]] = []
            line_end_pos: int = char_position + len(line_text)

            for highlight in snippet_data.highlights:
                if (highlight.start < line_end_pos and highlight.end > char_position):
                    # highlight intersects with current line
                    highlight_start_in_line: int = max(0, highlight.start - char_position)
                    highlight_end_in_line: int = min(len(line_text), highlight.end - char_position)
                    line_highlights.append({
                        "start": highlight_start_in_line,
                        "end": highlight_end_in_line
                    })

            line_highlights.sort(key=lambda x: x["start"])
            pos: int = 0
            max_width: int = self.bounds.width - current_x - LAYOUT_RESULT_WIDTH_BUFFER

            for highlight in line_highlights:
                # text before highlight
                if highlight["start"] > pos:
                    text_before: str = line_text[pos:highlight["start"]]
                    if current_x - SEARCH_RESULT_SNIPPET_MARGIN + len(text_before) <= max_width:
                        safe_addstr(stdscr, current_y, current_x, text_before, snippet_default_pair)
                        current_x += len(text_before)
                    pos = highlight["start"]

                # highlighted text
                highlighted_text: str = line_text[highlight["start"]:highlight["end"]]
                if current_x - SEARCH_RESULT_SNIPPET_MARGIN + len(highlighted_text) <= max_width:
                    safe_addstr(stdscr, current_y, current_x, highlighted_text, snippet_highlight_pair)
                    current_x += len(highlighted_text)
                pos = highlight["end"]

            # remaining
            if pos < len(line_text):
                remaining_text: str = line_text[pos:]
                remaining_width: int = max_width - (current_x - SEARCH_RESULT_SNIPPET_MARGIN)
                if remaining_width > 0:
                    safe_addstr(stdscr, current_y, current_x, remaining_text[:remaining_width], snippet_default_pair)

            # advance by the actual line length
            char_position += len(line_text)

            # add space if there's actually a space in the original text (otherwise hyphen off by one)
            if (char_position < len(snippet_data.clean_text) and
                snippet_data.clean_text[char_position].isspace()):
                char_position += 1

            lines_rendered += 1

        return lines_rendered

    def __select_next(self) -> None:
        """
        Move selection to the next result.
        """
        if self._selected_index < len(self.__results) - 1:
            self._selected_index += 1
            self.__ensure_visible()

    def __select_previous(self) -> None:
        """
        Move selection to the previous result.
        """
        if self._selected_index > 0:
            self._selected_index -= 1
            self.__ensure_visible()
