import curses
import sys
import traceback

from typing import Optional

from mcp_server_webcrawl.interactive.actions import (
    Action, ApplyConfig, OpenDocument, Quit, RunSearch, Transition,
)
from mcp_server_webcrawl.interactive.config import AppConfig
from mcp_server_webcrawl.interactive.screens import (
    DocumentScreen, HelpScreen, RequirementsScreen, Screen,
    SearchInitScreen, SearchResultsScreen,
)
from mcp_server_webcrawl.interactive.search import SearchManager, SearchResults
from mcp_server_webcrawl.interactive.ui import (
    DebugLog, Layout, Theme, UiFocusable, UiState,
)
from mcp_server_webcrawl.interactive.views.base import draw_outer_footer, draw_outer_header
from mcp_server_webcrawl.interactive.views.document import SearchDocumentView
from mcp_server_webcrawl.interactive.views.help import HelpView
from mcp_server_webcrawl.interactive.views.requirements import RequirementsView
from mcp_server_webcrawl.interactive.views.results import SearchResultsView
from mcp_server_webcrawl.interactive.views.searchform import SearchFormView
from mcp_server_webcrawl.models.resources import ResourceResult

# can be as low as 1, 50 feels a little laggy
CURSES_TIMEOUT_MS = 25
LAYOUT_MIN_HEIGHT_FOR_HELP = 2

class InteractiveSession:
    """
    Coordinator for the interactive TUI.

    Holds the long-lived collaborators (theme, debug overlay, search manager) and the
    view instances, wires them into one Screen per UiState, then runs a single
    render → read-key → route → apply loop. Screens return Actions describing intent;
    this class is the only place that performs them (state transitions, searches,
    document fetches, reconfiguration).
    """

    def __init__(self, crawler: str, datasrc: str):
        self.__theme: Theme = Theme()
        self.__debug: DebugLog = DebugLog()
        self.__running: bool = True

        self.__ui_state: UiState = UiState.REQUIREMENTS
        self.__crawler = None
        self.__searchman: Optional[SearchManager] = None

        # leaf views that only depend on the theme; the search form is rebuilt per config
        self.__results: SearchResultsView = SearchResultsView(self.__theme)
        self.__document: SearchDocumentView = SearchDocumentView(self.__theme)
        self.__help: HelpView = HelpView(self.__theme)
        self.__requirements: RequirementsView = RequirementsView(self.__theme, crawler, datasrc)
        self.__searchform: SearchFormView = SearchFormView(self.__theme, [])

        self.__screens: dict[UiState, Screen] = {}
        self.__results_screen: Optional[SearchResultsScreen] = None

        self.configure(AppConfig.load(crawler, datasrc))

    def run(self) -> None:
        """
        Launch the curses application and clean up the search worker on exit.
        """
        try:
            curses.wrapper(self.__curses_main)
        except KeyboardInterrupt:
            pass  # clean exit, ctrl+c
        except Exception as ex:
            print(f"--interactive failure: {ex}\n{traceback.format_exc()}", file=sys.stderr)
        finally:
            if self.__searchman is not None:
                self.__searchman.cleanup()

    def configure(self, config: AppConfig) -> None:
        """
        Adopt a crawler/datasrc pairing: rebuild the search form and worker against it,
        rewire the screens, and land on the search form (or requirements if not ready).
        """
        if self.__searchman is not None:
            self.__searchman.cleanup()

        self.__crawler = config.crawler
        self.__searchform = SearchFormView(self.__theme, config.sites)
        self.__searchman = SearchManager(config.crawler, self.__on_results) if config.ready else None

        self.__results.clear()
        self.__document.clear()
        self.__build_screens()

        if config.ready:
            self.__transition(UiState.SEARCH_INIT, UiFocusable.SEARCH_FORM)
        else:
            self.__transition(UiState.REQUIREMENTS, None)

    def __build_screens(self) -> None:
        """
        (Re)create the screen registry around the current view instances.
        """
        self.__results_screen = SearchResultsScreen(self.__searchform, self.__results, self.__searchman)
        self.__screens = {
            UiState.REQUIREMENTS: RequirementsScreen(self.__requirements),
            UiState.SEARCH_INIT: SearchInitScreen(self.__searchform),
            UiState.SEARCH_RESULTS: self.__results_screen,
            UiState.DOCUMENT: DocumentScreen(self.__document),
            UiState.HELP: HelpScreen(self.__help),
        }

    def __on_results(self, payload: SearchResults) -> None:
        """
        Receive a finished search page on the main thread (via check_pending).
        """
        self.__results.update(payload)

    def __curses_main(self, stdscr: curses.window) -> None:
        """
        Initialize the curses environment, then run the main loop.
        """
        if curses.COLORS < 256:
            stdscr.addstr(0, 0, "--interactive mode requires a 256-color (or better) terminal")
            stdscr.refresh()
            stdscr.getch()  # wait for keypress
            sys.exit(1)

        curses.start_color()
        self.__theme.init_curses()
        curses.curs_set(0)  # hide cursor, otherwise blinks at edge of last write
        self.__interactive_loop(stdscr)

    def __interactive_loop(self, stdscr: curses.window) -> None:
        """
        Render the active screen, read a key, route it to the screen, apply the Action.
        """
        try:
            stdscr.timeout(CURSES_TIMEOUT_MS)

            while self.__running:
                if self.__searchman is not None:
                    self.__searchman.check_pending()

                stdscr.clear()
                height, width = stdscr.getmaxyx()
                layout = Layout(width, height)
                screen: Screen = self.__screens[self.__ui_state]

                screen.render(stdscr, layout)

                if height > LAYOUT_MIN_HEIGHT_FOR_HELP:
                    draw_outer_header(stdscr, self.__theme)
                    draw_outer_footer(stdscr, self.__theme, screen.footer())

                self.__debug.render(stdscr, self.__theme)
                stdscr.refresh()

                key: int = stdscr.getch()
                if key == -1:  # timeout
                    continue

                action: Optional[Action] = screen.handle_input(key)
                if action is not None:
                    self.__apply(action)

        except Exception as ex:
            print(f"--interactive failure - {ex}\n{traceback.format_exc()}")
        finally:
            stdscr.timeout(-1)

    def __apply(self, action: Action) -> None:
        """
        Perform a screen's requested intent.
        """
        if isinstance(action, Quit):
            self.__running = False
        elif isinstance(action, Transition):
            self.__transition(action.state, action.focus)
        elif isinstance(action, RunSearch):
            self.__run_search(action.immediate)
        elif isinstance(action, OpenDocument):
            self.__open_document(action.result)
        elif isinstance(action, ApplyConfig):
            self.configure(action.config)

    def __transition(self, state: UiState, focus: Optional[UiFocusable]) -> None:
        """
        Switch screens. Entering the search form resets the query; entering the results
        pane hands the requested focus to that screen.
        """
        self.__ui_state = state
        if state == UiState.SEARCH_INIT:
            self.__searchform.clear_query()
        elif state == UiState.SEARCH_RESULTS and self.__results_screen is not None:
            self.__results_screen.set_focus(focus)

    def __run_search(self, immediate: bool) -> None:
        """
        Snapshot the form and dispatch a search, moving into the results pane the first
        time a search runs from the standalone form.
        """
        if self.__searchman is None:
            return
        if self.__ui_state == UiState.SEARCH_INIT:
            self.__transition(UiState.SEARCH_RESULTS, UiFocusable.SEARCH_FORM)
        self.__searchman.search(self.__searchform.build_request(), immediate=immediate)

    def __open_document(self, result: ResourceResult) -> None:
        """
        Fetch the full resource for a search hit and show it in the document reader.
        """
        if self.__crawler is None or not result.id:
            return

        site_ids: list[int] = [site.id for site in self.__searchform.get_selected_sites()]
        try:
            api = self.__crawler.get_resources_api(
                sites=site_ids if site_ids else None,
                query=f"id: {result.id}",
                offset=0,
                limit=1,
                fields=["headers", "content", "status", "size"],
                extras=["markdown"],
            )
            documents: list[ResourceResult] = api.get_results() if api is not None else []
        except Exception as ex:
            self.__debug.add(f"Error loading document: {ex}")
            return

        if documents:
            self.__document.update(documents[0], self.__searchform.query)
            self.__transition(UiState.DOCUMENT, None)
