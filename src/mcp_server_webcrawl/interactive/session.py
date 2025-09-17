import curses
import sys
import threading
import traceback

from pathlib import Path
from typing import Optional

from mcp_server_webcrawl.crawlers import get_crawler
from mcp_server_webcrawl.crawlers.base.crawler import BaseCrawler, BaseJsonApi
from mcp_server_webcrawl.interactive.search import SearchManager
from mcp_server_webcrawl.interactive.ui import ThemeDefinition, UiState, DocumentMode, UiFocusable, ViewBounds, safe_addstr
from mcp_server_webcrawl.interactive.views.base import BaseCursesView, OUTER_WIDTH_RIGHT_MARGIN
from mcp_server_webcrawl.interactive.views.document import SearchDocumentView
from mcp_server_webcrawl.interactive.views.requirements import RequirementsView
from mcp_server_webcrawl.interactive.views.results import SearchResultsView
from mcp_server_webcrawl.interactive.views.searchform import SearchFormView
from mcp_server_webcrawl.interactive.views.help import HelpView
from mcp_server_webcrawl.models.sites import SiteResult

# can be as low as 1, 50 feels a little laggy
CURSES_TIMEOUT_MS = 25

LAYOUT_CONTENT_START_Y_OFFSET = 1
LAYOUT_CONTENT_END_Y_OFFSET = 1
LAYOUT_SPLIT_PANE_MAX_HEIGHT = 10
LAYOUT_MIN_HEIGHT_FOR_HELP = 2

DEBUG_MAX_LINES = 8
DEBUG_COMPACT_WIDTH_RATIO = 0.4
DEBUG_MIN_COMPACT_WIDTH = 30
DEBUG_COMPACT_THRESHOLD = 5
DEBUG_EXPANDED_MARGIN = 6
DEBUG_EXPANDED_START_X = 3
DEBUG_EXPANDED_BOTTOM_MARGIN = 3
DEBUG_COMPACT_BOTTOM_MARGIN = 2
DEBUG_MIN_START_Y = 1
DEBUG_MIN_START_Y_EXPANDED = 2

SEARCH_DOCUMENT_NEXT_MODE: dict[DocumentMode, DocumentMode] = {
    DocumentMode.MARKDOWN: DocumentMode.RAW,
    DocumentMode.RAW: DocumentMode.HEADERS,
    DocumentMode.HEADERS: DocumentMode.MARKDOWN
}

SEARCH_RESULT_LIMIT: int = 10
TERMINAL_MIN_HEIGHT: int = 8
TERMINAL_MIN_WIDTH: int = 40

class InteractiveSession:
    """
    Main session coordinator that manages the interactive terminal application.
    """

    def __init__(self, crawler: str, datasrc: str):
        """
        Initialize the interactive session with crawler and data source.
        """
        self.__input_crawler: str = crawler
        self.__input_datasrc: str = datasrc
        self.__theme_map: dict[str, int] = {}
        self.__searchman: SearchManager = SearchManager(self)
        self.__ui_state: UiState = UiState.SEARCH_INIT
        self.__ui_focused: UiFocusable = UiFocusable.SEARCH_FORM
        self.__debug: list[str] = []

        self.__view__requirements = RequirementsView(self, crawler, datasrc)
        if self.__view__requirements.validated == True:
            crawl_model = get_crawler(crawler)
            if crawl_model is not None:
                self.__crawler: BaseCrawler = crawl_model(Path(datasrc))
                sites_api: BaseJsonApi = self.__crawler.get_sites_api()
                self.__sites: list[SiteResult] = sites_api.get_results()
            else:
                self.__crawler: BaseCrawler = None
                sites_api: BaseJsonApi = None
                self.__sites: list[SiteResult] = []
        else:
            crawl_model = None
            self.__crawler: BaseCrawler = None
            sites_api: BaseJsonApi = None
            self.__sites: list[SiteResult] = []

        self.__view__results = SearchResultsView(self)
        self.__view__document = SearchDocumentView(self)
        self.__view__searchform = SearchFormView(self, self.__sites)
        self.__view__help = HelpView(self)

        self.set_ui_state(UiState.SEARCH_INIT, UiFocusable.SEARCH_FORM)

    @property
    def ui_state(self) ->  UiState:
        return self.__ui_state

    @property
    def ui_focused(self) ->  UiFocusable:
        return self.__ui_focused

    @property
    def crawler(self) ->  BaseCrawler:
        return self.__crawler

    @property
    def document(self) -> SearchDocumentView:
        return self.__view__document

    @property
    def results(self) -> SearchResultsView:
        return self.__view__results

    @property
    def searchform(self) -> SearchFormView:
        return self.__view__searchform

    @property
    def searchman(self) -> SearchManager:
        return self.__searchman

    @property
    def sites(self) ->  list[SiteResult]:
        return self.__sites.copy()

    def debug_add(self, msg: str) -> None:
        """
        Add line of debug.
        """
        with threading.Lock():
            self.__debug.append(msg)

    def debug_clear(self) -> None:
        """
        Clear debug statements.
        """
        with threading.Lock():
            self.__debug.clear()

    def run(self) -> None:
        """
        Public interface to launch the interactive terminal application.
        """
        try:
            curses.wrapper(self.__curses_main)
        except KeyboardInterrupt:
            pass  # clean exit, ctrl+c
        except Exception as ex:
            print(f"--interactive failure: {ex}\n{traceback.format_exc()}", file=sys.stderr)
        finally:
            self.searchman.cleanup()
            pass

    def set_ui_state(self, state: UiState, focus: Optional[UiFocusable] = None) -> None:
        """
        Transition between UI states cleanly.
        """
        self.__ui_state = state
        if focus is not None:
            self.__ui_focused = focus

        self.__view__results.set_focused(False)
        self.__view__searchform.set_focused(False)
        if state == UiState.SEARCH_INIT or (state == UiState.SEARCH_RESULTS and focus == UiFocusable.SEARCH_FORM):
            self.__view__searchform.set_focused(True)
        elif state == UiState.SEARCH_RESULTS:
            self.__view__results.set_focused(True)

    # used in requirements view to reset with user inputs over cmd args
    def set_init_input_args(self, crawler: str, datasrc: str) -> None:
        self.__input_crawler = crawler
        self.__input_datasrc = datasrc

    def set_init_crawler(self, crawler: BaseCrawler) -> None:
        self.__crawler = crawler

    def set_init_sites(self, sites: str) -> None:
        self.__sites = sites

    # used in requirements to reset app
    def set_init_searchform(self, searchform: BaseCursesView) -> None:
        self.__view__searchform = searchform

    def __get_outer_screen(self, width: int, height: int) -> ViewBounds:
        """
        Get the outer screen bounds for the full terminal.
        """
        return ViewBounds(
            x=0,
            y=0,
            width=width - OUTER_WIDTH_RIGHT_MARGIN,
            height=height
        )

    def __get_inner_screen(self, width: int, height: int) -> ViewBounds:
        """
        Get the inner screen bounds for content area.
        """
        content_start_y = LAYOUT_CONTENT_START_Y_OFFSET
        content_end_y = height - LAYOUT_CONTENT_END_Y_OFFSET
        content_height = content_end_y - content_start_y

        return ViewBounds(
            x=0,
            y=content_start_y,  # after outer header
            width=width - OUTER_WIDTH_RIGHT_MARGIN,
            height=content_height
        )

    def __get_split_top(self, width: int, height: int) -> ViewBounds:
        """
        Get the top split screen bounds for dual-pane layout.
        """
        content_start_y = LAYOUT_CONTENT_START_Y_OFFSET
        content_height = height - 2
        split_top_height = min(LAYOUT_SPLIT_PANE_MAX_HEIGHT, content_height // 2)

        return ViewBounds(
            x=0,
            y=content_start_y,
            width=width - OUTER_WIDTH_RIGHT_MARGIN,
            height=split_top_height
        )

    def __get_split_bottom(self, width: int, height: int) -> ViewBounds:
        """
        Get the bottom split screen bounds for dual-pane layout.
        """
        content_start_y = LAYOUT_CONTENT_START_Y_OFFSET
        content_height = height - 2
        split_top_height = min(LAYOUT_SPLIT_PANE_MAX_HEIGHT, content_height // 2)
        split_bottom_height = content_height - split_top_height

        return ViewBounds(
            x=0,
            y=content_start_y + split_top_height,
            width=width - OUTER_WIDTH_RIGHT_MARGIN,
            height=split_bottom_height
        )

    def __curses_main(self, stdscr: curses.window) -> None:
        """
        Initialize curses environment and start main loop.
        """

        if curses.COLORS < 256:
            # display error in curses, dependable
            stdscr.addstr(0, 0, "--interactive mode requires a 256-color (or better) terminal")
            stdscr.refresh()
            stdscr.getch()  # wait for keypress
            sys.exit(1)

        # initialize curses style pairs
        curses.start_color()
        for theme in ThemeDefinition:
            self.__theme_map[theme.name] = theme.value
            curses.init_pair(*theme.value)

        # hide cursor, otherwise blinks at edge of last write
        curses.curs_set(0)

        # start main loop
        self.__interactive_loop(stdscr)

    def get_theme_color_pair(self, theme: ThemeDefinition) -> int | None:
        if theme.name in self.__theme_map:
            return curses.color_pair(self.__theme_map[theme.name][0])
        else:
            return None

    def __get_help_text(self) -> str:
        """
        Get context-sensitive help text.
        """
        page_results: str = " | ←→ Page Results" if self.ui_focused == UiFocusable.SEARCH_RESULTS else ""
        search_results_enter: str = "Search" if self.__view__searchform.focused else "View Document"
        search_results_tab: str = "Results" if self.__view__searchform.focused else "Search Form"
        footers: dict[UiState, str] = {
            UiState.DOCUMENT: "↑↓: Scroll | PgUp/PgDn: Page | Home/End: Top/Bot | TAB: Mode | ESC: Back",
            UiState.HELP: "↑↓: Scroll | PgUp/PgDn: Page | Home/End: Top/Bot | ESC: Back",
            UiState.REQUIREMENTS: "ENTER: Load Interface | ↑↓: Navigate| ESC: Exit",
            UiState.SEARCH_INIT: "ENTER: Search | ↑↓: Navigate | F1: Search Help | ESC: Exit",
            UiState.SEARCH_RESULTS: f"ENTER: {search_results_enter} | ↑↓: Navigate{page_results} | TAB: {search_results_tab} | ESC: New Search",
        }
        return footers.get(self.__ui_state, "↑↓: Navigate | ESC: Exit")

    def __handle_F1(self) -> None:
        """
        Handle F1 key
        """
        self.set_ui_state(UiState.HELP)

    def __handle_ESC(self) -> None:
        """
        Handle ESC key
        """
        if self.__ui_state == UiState.DOCUMENT:
            self.set_ui_state(UiState.SEARCH_RESULTS, UiFocusable.SEARCH_RESULTS)
        elif self.__ui_state in (UiState.SEARCH_RESULTS, UiState.REQUIREMENTS,  UiState.HELP):
            self.set_ui_state(UiState.SEARCH_INIT, UiFocusable.SEARCH_FORM)
            self.searchform.clear_query()
        elif self.__ui_state == UiState.SEARCH_INIT:
            sys.exit(0)

    def __handle_TAB(self) -> None:
        """
        Handle TAB key
        """
        if self.__ui_state == UiState.SEARCH_RESULTS:
            if self.__ui_focused == UiFocusable.SEARCH_FORM:
                self.set_ui_state(UiState.SEARCH_RESULTS, UiFocusable.SEARCH_RESULTS)
            else:
                self.set_ui_state(UiState.SEARCH_RESULTS, UiFocusable.SEARCH_FORM)

    def __interactive_loop(self, stdscr: curses.window) -> None:
        """
        Main input loop.
        """

        try:
            stdscr.timeout(CURSES_TIMEOUT_MS)

            while True:
                self.searchman.check_pending()

                stdscr.clear()
                height, width = stdscr.getmaxyx()
                selected_sites = self.__view__searchform.get_selected_sites()

                if self.__ui_state == UiState.REQUIREMENTS or self.__view__requirements.validated == False:

                    if not self.__ui_state == UiState.REQUIREMENTS:
                        self.set_ui_state(UiState.REQUIREMENTS)

                    inner_screen = self.__get_inner_screen(width, height)
                    self.__view__requirements.draw_inner_header(stdscr, inner_screen, "Requirements:")
                    self.__view__requirements.set_bounds(inner_screen)
                    self.__view__requirements.render(stdscr)
                    self.__view__requirements.draw_inner_footer(stdscr, inner_screen, f"Waiting on input")

                elif self.__ui_state == UiState.HELP:

                    inner_screen = self.__get_inner_screen(width, height)
                    self.__view__help.draw_inner_header(stdscr, inner_screen, "Search Help:")
                    self.__view__help.set_bounds(inner_screen)
                    self.__view__help.render(stdscr)
                    self.__view__help.draw_inner_footer(stdscr, inner_screen, f"ESC to Exit Help")

                elif self.__ui_state == UiState.SEARCH_RESULTS and selected_sites:

                    inner_screen_split_top = self.__get_split_top(width, height)
                    inner_screen_split_bottom = self.__get_split_bottom(width, height)
                    url: str = selected_sites[0].url if selected_sites else ""
                    display_url: str = BaseCursesView.url_for_display(url)
                    self.__view__searchform.draw_inner_header(stdscr, inner_screen_split_top, "Search:")
                    self.__view__searchform.set_bounds(inner_screen_split_top)
                    self.__view__searchform.render(stdscr)
                    self.__view__searchform.draw_inner_footer(stdscr, inner_screen_split_top, f"Searching {display_url}")
                    self.__view__results.draw_inner_header(stdscr, inner_screen_split_bottom, "")
                    self.__view__results.set_bounds(inner_screen_split_bottom)
                    self.__view__results.render(stdscr)
                    self.__view__results.draw_inner_footer(stdscr, inner_screen_split_bottom, "")

                elif self.__ui_state == UiState.DOCUMENT:

                    inner_screen = self.__get_inner_screen(width, height)
                    url: str = self.__view__document.url if self.__view__document is not None else ""
                    display_url: str = BaseCursesView.url_for_display(url)
                    self.__view__document.set_focused(True)
                    self.__view__document.draw_inner_header(stdscr, inner_screen, f"URL: {display_url}")
                    self.__view__document.set_bounds(inner_screen)
                    self.__view__document.render(stdscr)
                    self.__view__document.draw_inner_footer(stdscr, inner_screen, f"")

                else:

                    # aka self.__ui_state == UiState.SEARCH_INIT
                    inner_screen = self.__get_inner_screen(width, height)
                    self.__view__searchform.draw_inner_header(stdscr, inner_screen, "Search:")
                    selected_sites = self.__view__searchform.get_selected_sites()
                    first_hit = selected_sites[0] if selected_sites else None
                    url: str = first_hit.url if first_hit is not None else ""
                    display_url: str = BaseCursesView.url_for_display(url)
                    self.__view__searchform.set_bounds(inner_screen)
                    self.__view__searchform.render(stdscr)
                    self.__view__searchform.draw_inner_footer(stdscr, inner_screen, f"Searching {display_url}")

                if height > LAYOUT_MIN_HEIGHT_FOR_HELP:
                    help_text = self.__get_help_text()
                    self.__view__searchform.draw_outer_header(stdscr)
                    self.__view__searchform.draw_outer_footer(stdscr, help_text)

                self.__render_debug(stdscr)
                stdscr.refresh()

                key: int = stdscr.getch()
                if key == -1:               # timeout
                    continue
                elif key == ord('\t'):
                    self.__handle_TAB()
                elif key == curses.KEY_F1:
                    self.__handle_F1()
                elif key == 27:             # ESC
                    self.__handle_ESC()

                if self.__view__requirements.validated == False or self.__ui_state == UiState.REQUIREMENTS:
                    if self.__view__requirements.handle_input(key):
                        continue
                elif self.__ui_state == UiState.SEARCH_INIT or (
                        self.__ui_state == UiState.SEARCH_RESULTS
                        and self.__ui_focused == UiFocusable.SEARCH_FORM
                    ):
                    if self.__view__searchform.handle_input(key):
                        continue
                elif self.__ui_state == UiState.SEARCH_RESULTS:
                    if self.__view__results.handle_input(key):
                        continue
                elif self.__ui_state == UiState.DOCUMENT:
                    if self.__view__document.handle_input(key):
                        continue
                elif self.__ui_state == UiState.HELP:
                    if self.__view__help.handle_input(key):
                        continue

        except Exception as ex:
            print(f"--interactive failure - {ex}\n{traceback.format_exc()}")
            pass
        finally:
            stdscr.timeout(-1)

    def __render_debug(self, stdscr: curses.window) -> None:
        """
        Render debug info with adaptive sizing - compact for short messages, expanded for errors.
        """
        height, width = stdscr.getmaxyx()

        with threading.Lock():
            debug_lines = self.__debug[-(DEBUG_MAX_LINES):].copy()

        if not debug_lines:
            return

        max_line_length = max(len(line) for line in debug_lines) if debug_lines else 0
        compact_width = max(int(width * DEBUG_COMPACT_WIDTH_RATIO), DEBUG_MIN_COMPACT_WIDTH)
        use_expanded = max_line_length > compact_width - DEBUG_COMPACT_THRESHOLD

        if use_expanded:
            debug_width: int = width - DEBUG_EXPANDED_MARGIN
            debug_start_x: int = DEBUG_EXPANDED_START_X
            debug_start_y: int = max(DEBUG_MIN_START_Y_EXPANDED, height - len(debug_lines) - DEBUG_EXPANDED_BOTTOM_MARGIN)
        else:
            debug_width: int = compact_width
            debug_start_x: int = width - debug_width - DEBUG_EXPANDED_START_X
            debug_start_y: int = height - len(debug_lines) - DEBUG_COMPACT_BOTTOM_MARGIN

        debug_start_y: int = max(DEBUG_MIN_START_Y, debug_start_y)
        debug_start_x: int = max(0, debug_start_x)

        for i, debug_line in enumerate(debug_lines):
            y_pos: int = debug_start_y + i
            if y_pos >= height - 1:
                break
            if debug_start_x >= 0 and y_pos > 0:
                display_line: str = debug_line[:debug_width]
                safe_addstr(stdscr, y_pos, debug_start_x, display_line, self.get_theme_color_pair(ThemeDefinition.HEADER_ACTIVE))
