import curses
import textwrap

from dataclasses import dataclass, field
from typing import Optional

from mcp_server_webcrawl.interactive.actions import Action, OpenDocument
from mcp_server_webcrawl.interactive.highlights import HighlightProcessor, HighlightSpan
from mcp_server_webcrawl.interactive.search import SearchResults
from mcp_server_webcrawl.interactive.ui import Theme, ThemeDefinition, ViewBounds, safe_addstr, truncate
from mcp_server_webcrawl.interactive.views.base import BaseCursesView, humanized_bytes
from mcp_server_webcrawl.models.resources import ResourceResult

SEARCH_RESULT_SNIPPET_MARGIN: int = 6
SEARCH_RESULT_SNIPPET_MAX_LINES: int = 6

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
    A snippet processed once: clean text, highlight spans, and the wrapped lines
    paired with their start offset into clean_text. The offsets are recorded at wrap
    time so highlight mapping is exact rather than inferred from whitespace probing.
    """
    clean_text: str
    highlights: list[HighlightSpan]
    wrapped_lines: list[str]
    line_offsets: list[int]

    @property
    def visible_line_count(self) -> int:
        """Wrapped lines, capped at the snippet display limit."""
        return min(len(self.wrapped_lines), SEARCH_RESULT_SNIPPET_MAX_LINES)


@dataclass
class ResultRow:
    """One result's place in the virtual line space: its starting line and height."""
    result: ResourceResult
    index: int
    start_line: int
    snippet: Optional[SnippetData]

    @property
    def height(self) -> int:
        """One line for the URL, plus any visible snippet lines."""
        return 1 + (self.snippet.visible_line_count if self.snippet else 0)


class SearchResultsView(BaseCursesView):
    """
    Renders a page of search results with snippets.

    Holds only what it draws: the results page, the offset they were fetched at, and
    a `searching` flag the owning screen sets each frame. Selecting a result yields an
    OpenDocument action rather than fetching the document itself.
    """

    def __init__(self, theme: Theme):
        super().__init__(theme)
        self.searching: bool = False
        self.__results: list[ResourceResult] = []
        self.__results_total: int = 0
        self.__offset: int = 0
        self.__results_indexer_status: str = ""
        self.__results_indexer_processed: int = 0
        self.__results_indexer_duration: float = 0
        self.__scroll_offset: int = 0
        self.__snippet_cache: dict[tuple[int, int], SnippetData] = {}

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
        self.__offset = 0
        self._selected_index = 0
        self.__scroll_offset = 0
        self.__snippet_cache.clear()

    def update(self, payload: SearchResults) -> None:
        """
        Replace the displayed results from a finished search and reset selection.
        """
        self.__results = payload.results
        self.__results_total = payload.total
        self.__offset = payload.offset
        self.__results_indexer_status = payload.index_status
        self.__results_indexer_processed = payload.index_processed
        self.__results_indexer_duration = payload.index_duration
        self._selected_index = 0
        self.__scroll_offset = 0
        self.__snippet_cache.clear()

    def draw_inner_footer(self, stdscr: curses.window, bounds: ViewBounds, text: str) -> None:
        """
        Footer: page range on the left, indexing info on the right.
        """
        footer_y = bounds.y + bounds.height - 1
        style = self._get_inner_header_style()
        safe_addstr(stdscr, footer_y, bounds.x, self._get_bounded_line(), style)

        max_width = bounds.width - LAYOUT_FOOTER_MARGIN

        left_text = ""
        if self.__results:
            start = self.__offset + 1
            end = self.__offset + len(self.__results)
            left_text = truncate(f"Displaying {start:,}-{end:,} of {self.__results_total:,}", max_width // 2)
            safe_addstr(stdscr, footer_y, bounds.x + 1, left_text, style)

        if self.__results_indexer_processed > 0:
            right_text = f"{self.__results_indexer_processed:,} Indexed ({self.__results_indexer_duration:.2f}s)"
            if len(right_text) <= max_width:
                min_x = bounds.x + 1 + (len(left_text) + LAYOUT_FOOTER_TEXT_SPACING if left_text else 0)
                right_x = max(min_x, bounds.x + bounds.width - len(right_text) - 1)
                if right_x + len(right_text) < bounds.x + bounds.width:
                    safe_addstr(stdscr, footer_y, right_x, right_text, style)

    def draw_inner_header(self, stdscr: curses.window, bounds: ViewBounds, text: str) -> None:
        """
        Header: results count on the left.
        """
        style = self._get_inner_header_style()
        safe_addstr(stdscr, bounds.y, bounds.x, self._get_bounded_line(), style)

        if self.__results and not self.searching:
            left_text = f"Results ({self.__results_total:,} Found)"
        else:
            left_text = "Results:"

        left_text = truncate(left_text, (bounds.width - LAYOUT_FOOTER_MARGIN) // 2)
        safe_addstr(stdscr, bounds.y, bounds.x + 1, left_text, style)

    def get_selected_result(self) -> Optional[ResourceResult]:
        """
        The currently selected result, or None.
        """
        if 0 <= self._selected_index < len(self.__results):
            return self.__results[self._selected_index]
        return None

    def handle_input(self, key: int) -> Optional[Action]:
        """
        UP/DOWN select; ENTER opens the selected document. Paging (LEFT/RIGHT) is
        handled by the owning screen, which holds the form's pagination.
        """
        if not self._focused or not self.__results:
            return None

        if key in (ord('\n'), ord('\r')):
            return self.__open_selected()
        if key == curses.KEY_UP:
            self.__move_selection(-1)
        elif key == curses.KEY_DOWN:
            self.__move_selection(1)

        return None

    def render(self, stdscr: curses.window) -> None:
        """
        Render the results content (header/footer are drawn by the screen).
        """
        if not self._renderable(stdscr) or self.bounds.height <= LAYOUT_HEADER_FOOTER_HEIGHT:
            return

        y_current = self.bounds.y + 1

        message = self.__status_message()
        if message:
            safe_addstr(stdscr, y_current, LAYOUT_STATUS_MESSAGE_X_OFFSET, message, curses.A_DIM)
        else:
            self.__render_results_list(stdscr, y_current)

    def __status_message(self) -> str:
        """
        The placeholder line to show in place of results, or "" when results exist.
        """
        if self.searching:
            return "Searching…"
        if not self.__results:
            indexing = self.__results_indexer_status in ("idle", "indexing", "")
            return "Indexing…" if indexing else "No results found."
        return ""

    def __open_selected(self) -> Optional[Action]:
        """
        Request the document view for the selected result.
        """
        result = self.get_selected_result()
        if not result or not result.id:
            return None
        return OpenDocument(result)

    def __snippet_for(self, result: ResourceResult) -> Optional[SnippetData]:
        """
        Processed snippet for a result, or None if it has none. Cached per (result id,
        snippet width) so textwrap runs once per result until the pane resizes.
        """
        raw = result.get_extra("snippets")
        if not raw or not raw.strip():
            return None

        key = (id(result), self.bounds.width)
        cached = self.__snippet_cache.get(key)
        if cached is None:
            cached = self.__process_snippet(raw)
            self.__snippet_cache[key] = cached
        return cached

    def __layout(self) -> list[ResultRow]:
        """
        The single source of truth for vertical layout: every result paired with the
        virtual line it starts on and its processed snippet. Both scrolling and drawing
        read from this, so they cannot disagree about where a result sits.
        """
        rows: list[ResultRow] = []
        line = 0
        for index, result in enumerate(self.__results):
            row = ResultRow(result, index, line, self.__snippet_for(result))
            rows.append(row)
            line += row.height
        return rows

    def __process_snippet(self, snippet_text: str) -> SnippetData:
        """
        Process raw snippet text into clean text, highlight spans, wrapped lines, and
        the start offset of each wrapped line within clean_text.
        """
        clean_text, highlights = HighlightProcessor.extract_snippet_highlights(snippet_text)

        snippet_width = self.bounds.width - (SEARCH_RESULT_SNIPPET_MARGIN * 2)
        wrapped_lines = textwrap.fill(
            clean_text,
            width=snippet_width,
            expand_tabs=True,
            replace_whitespace=True,
            break_long_words=True,
            break_on_hyphens=True,
        ).split("\n")

        # Recover each line's offset by walking clean_text forward; this is exact
        # regardless of how much whitespace textwrap collapsed at each break.
        line_offsets: list[int] = []
        cursor = 0
        for line_text in wrapped_lines:
            stripped = line_text.strip()
            found = clean_text.find(stripped, cursor) if stripped else cursor
            offset = found if found != -1 else cursor
            line_offsets.append(offset)
            cursor = offset + len(stripped)

        return SnippetData(clean_text, highlights, wrapped_lines, line_offsets)

    def __render_results_list(self, stdscr: curses.window, start_y: int) -> None:
        """
        Draw the visible slice of the layout, respecting the scroll offset.
        """
        y_max = self.bounds.y + self.bounds.height

        for row in self.__layout():
            if row.start_line + row.height <= self.__scroll_offset:
                continue  # entirely scrolled past
            y = start_y + (row.start_line - self.__scroll_offset)
            if y >= y_max:
                break

            if y >= start_y:
                self.__render_result_line(stdscr, row, y)

            if row.snippet:
                self.__render_snippet(stdscr, row, start_y, y_max)

    def __render_result_line(self, stdscr: curses.window, row: ResultRow, y: int) -> None:
        """
        Draw a single result's header line: number, URL, and right-aligned metadata.
        """
        result = row.result
        is_selected = self._focused and row.index == self._selected_index
        selected_style = curses.A_REVERSE if is_selected else curses.A_NORMAL
        result_num = f"{self.__offset + row.index + 1:02d}. "

        metadata_parts: list[tuple[str, int]] = []
        if result.type.value:
            metadata_parts.append((f"{f'[{result.type.value}]':>{TYPE_FIELD_WIDTH}}", curses.A_NORMAL))
        size_text = humanized_bytes(result.size)
        if size_text and size_text != "0B":
            metadata_parts.append((f"{size_text:>{SIZE_FIELD_WIDTH}}", curses.A_NORMAL))
        metadata_parts.append((str(result.status), self.__status_style(result.status)))

        line_x = LAYOUT_RESULT_LINE_MARGIN
        available_width = min(self.bounds.width - LAYOUT_RESULT_WIDTH_BUFFER, self.bounds.width - line_x)
        metadata_text = "  ".join(text for text, _ in metadata_parts)
        url = result.url or "No URL"

        if metadata_parts:
            url = truncate(url, available_width - len(result_num) - len(metadata_text) - URL_PADDING_BUFFER)
            head = f"{result_num}{url}"
            safe_addstr(stdscr, y, line_x, head, selected_style)

            x = line_x + len(head)
            line_end = line_x + available_width
            padding = available_width - len(head) - len(metadata_text)
            if padding > 0 and x < line_end:
                safe_addstr(stdscr, y, x, " " * padding, curses.A_NORMAL)
                x += padding

            for part_text, part_style in metadata_parts:
                if x < line_end:
                    safe_addstr(stdscr, y, x, part_text, part_style)
                    x += len(part_text) + LAYOUT_RESULT_METADATA_SPACING
        else:
            url = truncate(url, available_width - len(result_num))
            safe_addstr(stdscr, y, line_x, f"{result_num}{url}"[:available_width], selected_style)

    def __render_snippet(self, stdscr: curses.window, row: ResultRow, start_y: int, y_max: int) -> None:
        """
        Draw a result's wrapped snippet lines with highlighting, clipping any lines
        that fall above the scroll window or below the pane.
        """
        snippet = row.snippet
        default_style = self.theme.color(ThemeDefinition.SNIPPET_DEFAULT)
        highlight_style = self.theme.color(ThemeDefinition.SNIPPET_HIGHLIGHT)
        max_width = self.bounds.width - SEARCH_RESULT_SNIPPET_MARGIN - LAYOUT_RESULT_WIDTH_BUFFER

        for i in range(snippet.visible_line_count):
            # +1: the snippet's first line sits one below the result's header line.
            y = start_y + (row.start_line + 1 + i - self.__scroll_offset)
            if y < start_y:
                continue
            if y >= y_max:
                break

            line_text = snippet.wrapped_lines[i]
            if not line_text.strip():
                continue

            line_start = snippet.line_offsets[i]
            line_end = line_start + len(line_text)
            local_highlights = [
                HighlightSpan(
                    start=max(0, h.start - line_start),
                    end=min(len(line_text), h.end - line_start),
                    text=line_text[max(0, h.start - line_start):min(len(line_text), h.end - line_start)],
                )
                for h in snippet.highlights
                if h.start < line_end and h.end > line_start
            ]

            HighlightProcessor.render_text_with_highlights(
                stdscr, line_text, local_highlights,
                SEARCH_RESULT_SNIPPET_MARGIN, y, max_width,
                default_style, highlight_style,
            )

    @staticmethod
    def __status_style_for(status: int) -> Optional[ThemeDefinition]:
        if status >= HTTP_ERROR_THRESHOLD:
            return ThemeDefinition.HTTP_ERROR
        if status >= HTTP_WARN_THRESHOLD:
            return ThemeDefinition.HTTP_WARN
        return None

    def __status_style(self, status: int) -> int:
        """
        Curses style for an HTTP status code (error/warn themed, else normal).
        """
        definition = self.__status_style_for(status)
        return self.theme.color(definition) if definition is not None else curses.A_NORMAL

    def __move_selection(self, delta: int) -> None:
        """
        Move the selection by delta, clamped to the result list, then rescroll.
        """
        new_index = self._selected_index + delta
        if 0 <= new_index < len(self.__results):
            self._selected_index = new_index
            self.__ensure_visible()

    def __ensure_visible(self) -> None:
        """
        Scroll the minimum amount needed to bring the selected result fully into view.
        """
        layout = self.__layout()
        if not (0 <= self._selected_index < len(layout)):
            return

        row = layout[self._selected_index]
        visible_height = self.bounds.height - LAYOUT_HEADER_FOOTER_HEIGHT
        selected_end = row.start_line + row.height - 1

        if row.start_line < self.__scroll_offset:
            self.__scroll_offset = row.start_line
        elif selected_end >= self.__scroll_offset + visible_height:
            self.__scroll_offset = max(0, selected_end - visible_height + 1)
