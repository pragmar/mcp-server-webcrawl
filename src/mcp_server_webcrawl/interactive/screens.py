import curses

from typing import Optional

from mcp_server_webcrawl.interactive.actions import (
    Action, Quit, RunSearch, Transition,
)
from mcp_server_webcrawl.interactive.search import SearchManager
from mcp_server_webcrawl.interactive.ui import Layout, UiFocusable, UiState
from mcp_server_webcrawl.interactive.views.base import BaseCursesView
from mcp_server_webcrawl.interactive.views.document import SearchDocumentView
from mcp_server_webcrawl.interactive.views.help import HelpView
from mcp_server_webcrawl.interactive.views.requirements import RequirementsView
from mcp_server_webcrawl.interactive.views.results import SearchResultsView
from mcp_server_webcrawl.interactive.views.searchform import SearchFormView

KEY_ESC: int = 27
KEY_TAB: int = ord("\t")
KEY_ENTER: tuple[int, int] = (ord("\n"), ord("\r"))

class Screen:
    """
    A full-screen mode: it draws the views for one UiState and turns keystrokes into
    Actions for the session to apply. Screens own layout/focus details for their state;
    the session owns the transitions between them.
    """

    def footer(self) -> str:
        """
        Context-sensitive help shown in the outer footer chrome.
        """
        return "↑↓: Navigate | ESC: Exit"

    def render(self, stdscr: curses.window, layout: Layout) -> None:
        raise NotImplementedError

    def handle_input(self, key: int) -> Optional[Action]:
        raise NotImplementedError

    @staticmethod
    def _display_url(sites: list) -> str:
        """
        The display URL of the first selected site, or empty when none.
        """
        if sites and sites[0].urls:
            return BaseCursesView.url_for_display(sites[0].urls[0])
        return ""


class RequirementsScreen(Screen):
    """
    Crawler/datasrc configuration. ENTER on a valid datasrc yields ApplyConfig;
    ESC quits. F1 is deliberately inert here so the user can't leave a half-configured
    app for the help screen.
    """

    def __init__(self, requirements: RequirementsView):
        self.__requirements = requirements

    def footer(self) -> str:
        return "ENTER: Load Interface | ↑↓: Navigate| ESC: Exit"

    def render(self, stdscr: curses.window, layout: Layout) -> None:
        inner = layout.inner()
        self.__requirements.set_focused(True)
        self.__requirements.set_bounds(inner)
        self.__requirements.draw_inner_header(stdscr, inner, "Requirements:")
        self.__requirements.render(stdscr)
        self.__requirements.draw_inner_footer(stdscr, inner, "Waiting on input")

    def handle_input(self, key: int) -> Optional[Action]:
        if key == KEY_ESC:
            return Quit()
        return self.__requirements.handle_input(key)


class SearchInitScreen(Screen):
    """
    The standalone search form before any search has run. Editing the query (or
    submitting) yields RunSearch; F1 opens help; ESC quits.
    """

    def __init__(self, searchform: SearchFormView):
        self.__searchform = searchform

    def footer(self) -> str:
        return "ENTER: Search | ↑↓: Navigate | F1: Search Help | ESC: Exit"

    def render(self, stdscr: curses.window, layout: Layout) -> None:
        inner = layout.inner()
        self.__searchform.live = False
        self.__searchform.set_focused(True)
        self.__searchform.set_bounds(inner)
        self.__searchform.draw_inner_header(stdscr, inner, "Search:")
        self.__searchform.render(stdscr)
        display_url = self._display_url(self.__searchform.get_selected_sites())
        self.__searchform.draw_inner_footer(stdscr, inner, f"Searching {display_url}")

    def handle_input(self, key: int) -> Optional[Action]:
        if key == KEY_ESC:
            return Quit()
        if key == curses.KEY_F1:
            return Transition(UiState.HELP)
        return self.__searchform.handle_input(key)


class SearchResultsScreen(Screen):
    """
    The dual-pane search form over results. Owns the form/results focus toggle (TAB)
    and result paging (←→ when the results pane is focused), translating both into the
    appropriate view input or a fresh RunSearch.
    """

    def __init__(self, searchform: SearchFormView, results: SearchResultsView, searchman: SearchManager):
        self.__searchform = searchform
        self.__results = results
        self.__searchman = searchman
        self.__focus: UiFocusable = UiFocusable.SEARCH_FORM

    def set_focus(self, focus: UiFocusable) -> None:
        """
        Set which pane (form or results) receives input and renders focused.
        """
        self.__focus = focus if focus is not None else UiFocusable.SEARCH_FORM

    @property
    def __form_focused(self) -> bool:
        return self.__focus == UiFocusable.SEARCH_FORM

    def footer(self) -> str:
        enter_label = "Search" if self.__form_focused else "View Document"
        tab_label = "Results" if self.__form_focused else "Search Form"
        page_label = "" if self.__form_focused else " | ←→ Page Results"
        return f"ENTER: {enter_label} | ↑↓: Navigate{page_label} | TAB: {tab_label} | ESC: New Search"

    def render(self, stdscr: curses.window, layout: Layout) -> None:
        split_top = layout.split_top()
        split_bottom = layout.split_bottom()

        self.__searchform.live = True
        self.__searchform.set_focused(self.__form_focused)
        self.__results.set_focused(not self.__form_focused)
        self.__results.searching = self.__searchman.is_searching()

        display_url = self._display_url(self.__searchform.get_selected_sites())
        self.__searchform.set_bounds(split_top)
        self.__searchform.draw_inner_header(stdscr, split_top, "Search:")
        self.__searchform.render(stdscr)
        self.__searchform.draw_inner_footer(stdscr, split_top, f"Searching {display_url}")

        self.__results.set_bounds(split_bottom)
        self.__results.draw_inner_header(stdscr, split_bottom, "")
        self.__results.render(stdscr)
        self.__results.draw_inner_footer(stdscr, split_bottom, "")

    def handle_input(self, key: int) -> Optional[Action]:
        if key == KEY_ESC:
            return Transition(UiState.SEARCH_INIT, UiFocusable.SEARCH_FORM)
        if key == curses.KEY_F1:
            return Transition(UiState.HELP)
        if key == KEY_TAB:
            self.__focus = (UiFocusable.SEARCH_RESULTS if self.__form_focused
                            else UiFocusable.SEARCH_FORM)
            return None

        if self.__form_focused:
            return self.__searchform.handle_input(key)

        if key == curses.KEY_LEFT:
            return RunSearch(immediate=True) if self.__searchform.page_previous() else None
        if key == curses.KEY_RIGHT:
            paged = self.__searchform.page_next(self.__results.results_total)
            return RunSearch(immediate=True) if paged else None

        return self.__results.handle_input(key)


class DocumentScreen(Screen):
    """
    The single-document reader. Scroll/mode keys are consumed by the view; ESC returns
    to the results list and F1 opens help.
    """

    def __init__(self, document: SearchDocumentView):
        self.__document = document

    def footer(self) -> str:
        return "↑↓: Scroll | PgUp/PgDn: Page | Home/End: Top/Bot | TAB: Mode | ESC: Back"

    def render(self, stdscr: curses.window, layout: Layout) -> None:
        inner = layout.inner()
        self.__document.set_focused(True)
        self.__document.set_bounds(inner)
        display_url = BaseCursesView.url_for_display(self.__document.url)
        self.__document.draw_inner_header(stdscr, inner, f"URL: {display_url}")
        self.__document.render(stdscr)
        self.__document.draw_inner_footer(stdscr, inner, "")

    def handle_input(self, key: int) -> Optional[Action]:
        if key == KEY_ESC:
            return Transition(UiState.SEARCH_RESULTS, UiFocusable.SEARCH_RESULTS)
        if key == curses.KEY_F1:
            return Transition(UiState.HELP)
        return self.__document.handle_input(key)


class HelpScreen(Screen):
    """
    Scrollable search-syntax help. ESC returns to a fresh search form.
    """

    def __init__(self, help_view: HelpView):
        self.__help = help_view

    def footer(self) -> str:
        return "↑↓: Scroll | PgUp/PgDn: Page | Home/End: Top/Bot | ESC: Back"

    def render(self, stdscr: curses.window, layout: Layout) -> None:
        inner = layout.inner()
        self.__help.set_bounds(inner)
        self.__help.draw_inner_header(stdscr, inner, "Search Help:")
        self.__help.render(stdscr)
        self.__help.draw_inner_footer(stdscr, inner, "ESC to Exit Help")

    def handle_input(self, key: int) -> Optional[Action]:
        if key == KEY_ESC:
            return Transition(UiState.SEARCH_INIT, UiFocusable.SEARCH_FORM)
        return self.__help.handle_input(key)
