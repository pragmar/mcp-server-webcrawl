import curses

from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable, Optional

from mcp_server_webcrawl.interactive.actions import Action, RunSearch
from mcp_server_webcrawl.interactive.search import SearchRequest
from mcp_server_webcrawl.interactive.ui import (
    InputRadio, InputRadioGroup, InputText, NavigationDirection,
    Theme, ThemeDefinition, safe_addstr, truncate,
)
from mcp_server_webcrawl.interactive.views.base import BaseCursesView
from mcp_server_webcrawl.models.sites import SiteResult

LAYOUT_QUERY_MAX_WIDTH = 50
LAYOUT_QUERY_MARGIN = 11
LAYOUT_QUERY_OFFSET = 9
LAYOUT_FILTER_COLUMN_PADDING = 8
LAYOUT_SORT_COLUMN_PADDING = 6
LAYOUT_FILTER_TO_SORT_SPACING = 8
LAYOUT_SORT_TO_SITES_SPACING = 6
LAYOUT_SITE_COLUMN_WIDTH = 22
LAYOUT_SITE_COLUMN_SPACING = 2
LAYOUT_SITES_VERTICAL_OFFSET = 6
LAYOUT_SITES_MIN_WIDTH_REQUIREMENT = 16
LAYOUT_CONSTRAINED_SITES_PER_COLUMN = 3
LAYOUT_TRUNCATED_LABEL_MAX_LENGTH = 18
LAYOUT_OVERFLOW_INDICATOR_MARGIN = 2

# index 0 is always the query field; radios are numbered from 1.
QUERY_INDEX = 0


class FieldKind(Enum):
    QUERY = auto()
    FILTER = auto()
    SORT = auto()
    SITE = auto()


@dataclass(frozen=True)
class FieldRef:
    """What a selection index points at: which group, and the offset within it."""
    kind: FieldKind
    offset: int  # 0 for QUERY; index into the group's radios otherwise


class FieldLayout:
    """
    Single source of truth for the search form's field model.

    Owns three things that were previously re-derived in three places:
      1. the index scheme (index -> what it is), via resolve()
      2. the navigation grid (index -> row/col and back)
      3. movement in all four directions

    Grid shape (col, then rows):
        query(0)                spans the top row
        filter0  sort0  site0  site3  site6
        filter1  sort1  site1  site4  site7
                 sort2  site2  site5  site8+

    `linear_down`: when True (form-only view) DOWN/UP step linearly through every
    field instead of moving within the grid, matching the old SEARCH_INIT behavior.
    """

    def __init__(self, filter_count: int, sort_count: int, site_count: int,
            sites_per_column: int, linear_down: bool):
        self.__linear_down = linear_down
        self.__filter_count = filter_count
        self.__sort_count = sort_count
        self.__site_count = site_count

        # index -> FieldRef, and the two grid maps, all built once together so the
        # scheme can never disagree with itself.
        self.__refs: dict[int, FieldRef] = {QUERY_INDEX: FieldRef(FieldKind.QUERY, 0)}
        self.__grid: dict[tuple[int, int], int] = {}
        self.__reverse: dict[int, tuple[int, int]] = {}

        # query spans columns 0-2 on row 0
        for col in range(3):
            self.__grid[(0, col)] = QUERY_INDEX
        self.__reverse[QUERY_INDEX] = (0, 0)

        index = 1
        for kind, count, col in (
            (FieldKind.FILTER, filter_count, 0),
            (FieldKind.SORT, sort_count, 1),
        ):
            for offset in range(count):
                self.__place(index, 1 + offset, col, FieldRef(kind, offset))
                index += 1

        for offset in range(site_count):
            row = 1 + (offset % sites_per_column)
            col = 2 + (offset // sites_per_column)
            self.__place(index, row, col, FieldRef(FieldKind.SITE, offset))
            index += 1

        self.__last_index = index - 1

    def __place(self, index: int, row: int, col: int, ref: FieldRef) -> None:
        self.__grid[(row, col)] = index
        self.__reverse[index] = (row, col)
        self.__refs[index] = ref

    @property
    def last_index(self) -> int:
        return self.__last_index

    def resolve(self, index: int) -> Optional[FieldRef]:
        """What does this selection index point at? None if out of range."""
        return self.__refs.get(index)

    def index_of(self, kind: FieldKind, offset: int) -> Optional[int]:
        """Inverse of resolve(): find the index for a given group field."""
        for idx, ref in self.__refs.items():
            if ref.kind == kind and ref.offset == offset:
                return idx
        return None

    def __cols_in_row(self, row: int) -> list[int]:
        return sorted(c for (r, c) in self.__grid if r == row)

    def left(self, index: int) -> Optional[int]:
        pos = self.__reverse.get(index)
        if pos is None:
            return None
        row, col = pos
        for c in range(col - 1, -1, -1):
            if (row, c) in self.__grid:
                return self.__grid[(row, c)]
        cols = self.__cols_in_row(row)  # wrap to rightmost
        return self.__grid[(row, cols[-1])] if cols and cols[-1] != col else None

    def right(self, index: int) -> Optional[int]:
        pos = self.__reverse.get(index)
        if pos is None:
            return None
        row, col = pos
        candidates = [c for c in self.__cols_in_row(row) if c > col]
        if candidates:
            return self.__grid[(row, candidates[0])]
        cols = self.__cols_in_row(row)  # wrap to leftmost
        return self.__grid[(row, cols[0])] if cols and cols[0] != col else None

    def up(self, index: int) -> Optional[int]:
        if self.__linear_down:
            return self.__last_index if index == QUERY_INDEX else index - 1
        pos = self.__reverse.get(index)
        if pos is None:
            return None
        row, col = pos
        if row == 0:
            return None
        if row == 1:
            return QUERY_INDEX
        return self.__grid.get((row - 1, col))

    def down(self, index: int) -> Optional[int]:
        if self.__linear_down:
            return QUERY_INDEX if index == self.__last_index else index + 1
        pos = self.__reverse.get(index)
        if pos is None:
            return None
        row, col = pos
        return self.__grid.get((row + 1, col))


class SearchFormView(BaseCursesView):
    """
    The search form: query field plus filter/sort/site radio groups.

    Owns its own pagination (offset/limit) and produces a SearchRequest on demand.
    Input is translated to RunSearch actions instead of poking a search manager. The
    `live` flag (set by whichever screen is showing the form) controls both the
    constrained results-pane layout and whether radio toggles trigger live searches.
    """

    def __init__(self, theme: Theme, sites: list[SiteResult]):
        super().__init__(theme)
        self.live: bool = False
        self.__sites: list[SiteResult] = sites
        self.__sites_selected: list[SiteResult] = []
        self.__query_input = InputText(initial_value="", label="Query")
        self.__limit = 10
        self.__offset = 0

        if sites:
            self.__sites_selected.append(self.__sites[0])

        self.__filter_group: InputRadioGroup = InputRadioGroup("filter")
        self.__sort_group: InputRadioGroup = InputRadioGroup("sort")
        self.__sites_group: InputRadioGroup = InputRadioGroup("site", sites=self.__sites)

    @property
    def filter(self) -> str:
        return self.__filter_group.value

    @property
    def limit(self) -> int:
        return self.__limit

    @property
    def offset(self) -> int:
        return self.__offset

    @property
    def query(self) -> str:
        return self.__query_input.value

    @property
    def sort(self) -> str:
        return self.__sort_group.value.lower() if self.__sort_group.value is not None else "+url"

    def build_request(self) -> SearchRequest:
        """
        Snapshot the current form state into an immutable SearchRequest.
        """
        return SearchRequest(
            query=self.query,
            site_ids=tuple(site.id for site in self.__sites_selected),
            filter=self.filter,
            sort=self.sort,
            offset=self.__offset,
            limit=self.__limit,
        )

    def clear_query(self) -> None:
        """
        Clear the query and reset pagination, preserving radio selections.
        """
        self.__query_input.clear()
        self._selected_index = 0
        self.__offset = 0

    def get_selected_sites(self) -> list[SiteResult]:
        return self.__sites_selected.copy()

    def __layout(self) -> FieldLayout:
        """
        Build the field model for the current group sizes and pane state. Cheap to
        rebuild; it changes only when groups or sites_per_column change.
        """
        return FieldLayout(
            filter_count=len(self.__filter_group.radios),
            sort_count=len(self.__sort_group.radios),
            site_count=len(self.__sites_group.radios),
            sites_per_column=self.__get_sites_per_column(),
            linear_down=not self.live,
        )

    def handle_input(self, key: int) -> Optional[Action]:
        """
        Translate a keystroke into a RunSearch action (or None for pure navigation).
        """
        handlers: dict[int, Callable[[], Optional[Action]]] = {
            curses.KEY_UP: lambda: self.__navigate(NavigationDirection.UP),
            curses.KEY_DOWN: lambda: self.__navigate(NavigationDirection.DOWN),
            curses.KEY_LEFT: lambda: self.__navigate(NavigationDirection.LEFT),
            curses.KEY_RIGHT: lambda: self.__navigate(NavigationDirection.RIGHT),
            ord(' '): self.__handle_spacebar,
            ord('\n'): self.__handle_enter,
            ord('\r'): self.__handle_enter,
        }

        handler = handlers.get(key)
        if handler:
            return handler()

        if self._selected_index == QUERY_INDEX and self.__query_input.handle_input(key):
            return RunSearch(immediate=False)

        return None

    def page_next(self, total_results: int) -> bool:
        """
        Advance to the next page if there is one.
        """
        if self.__offset + self.__limit < total_results:
            self.__offset += self.__limit
            return True
        return False

    def page_previous(self) -> bool:
        """
        Go back a page if not already at the start.
        """
        if self.__offset >= self.__limit:
            self.__offset -= self.__limit
            return True
        return False

    def render(self, stdscr: curses.window) -> None:
        """
        Render the search form with multi-column sites layout.
        """
        xb: int = self.bounds.x
        yb: int = self.bounds.y
        y_current: int = yb + 2
        y_max: int = yb + self.bounds.height

        if not self._renderable(stdscr):
            return

        layout = self.__layout()

        safe_addstr(stdscr, y_current, xb + 2, "Query:")

        box_width = min(LAYOUT_QUERY_MAX_WIDTH, self.bounds.width - LAYOUT_QUERY_MARGIN)
        is_query_selected = (self._focused and self._selected_index == QUERY_INDEX)

        self.__query_input.render(stdscr, y_current, xb + LAYOUT_QUERY_OFFSET, box_width,
                focused=is_query_selected, style=self._get_input_style(is_query_selected))

        y_current += 2
        if y_current >= y_max:
            return

        filter_column_width = self.__filter_group.calculate_group_width() + LAYOUT_FILTER_COLUMN_PADDING
        sort_column_width = self.__sort_group.calculate_group_width() + LAYOUT_SORT_COLUMN_PADDING
        sort_start_x = filter_column_width + LAYOUT_FILTER_TO_SORT_SPACING
        sites_start_x = sort_start_x + sort_column_width + LAYOUT_SORT_TO_SITES_SPACING
        sites_visible = sites_start_x + LAYOUT_SITES_MIN_WIDTH_REQUIREMENT < self.bounds.width

        safe_addstr(stdscr, y_current, xb + 2, self.__filter_group.label)
        safe_addstr(stdscr, y_current, xb + sort_start_x, self.__sort_group.label)
        if sites_visible:
            safe_addstr(stdscr, y_current, xb + sites_start_x, self.__sites_group.label)
            if not self.__sites:
                error_style = self.theme.color(ThemeDefinition.UI_ERROR)
                safe_addstr(stdscr, y_current + 1, xb + sites_start_x, "No sites available", error_style)

        y_current += 1

        available_width = self.bounds.width - sites_start_x - 4
        sites_per_column = self.__get_sites_per_column()
        max_columns = (max(1, available_width // (LAYOUT_SITE_COLUMN_WIDTH + LAYOUT_SITE_COLUMN_SPACING))
                      if available_width > LAYOUT_SITE_COLUMN_WIDTH else 1)
        total_visible_sites = max_columns * sites_per_column
        overflow_count = max(0, len(self.__sites_group.radios) - total_visible_sites)
        max_rows = max(len(self.__filter_group.radios), len(self.__sort_group.radios), sites_per_column)

        def render_radio(radio: InputRadio, kind: FieldKind, offset: int, x: int, width: int) -> None:
            field_index = layout.index_of(kind, offset)
            radio.render(stdscr, y_current, x, field_index, width, self._selected_index == field_index)

        for i in range(max_rows):

            if y_current >= y_max:
                return

            if i < len(self.__filter_group.radios):
                render_radio(self.__filter_group.radios[i], FieldKind.FILTER, i, xb + 2, 100)

            if i < len(self.__sort_group.radios):
                render_radio(self.__sort_group.radios[i], FieldKind.SORT, i, xb + sort_start_x, 100)

            if sites_visible:
                for col in range(max_columns):
                    site_index = col * sites_per_column + i
                    if site_index < len(self.__sites_group.radios) and site_index < total_visible_sites:
                        site_radio = self.__sites_group.radios[site_index]
                        col_x = sites_start_x + col * (LAYOUT_SITE_COLUMN_WIDTH + LAYOUT_SITE_COLUMN_SPACING)
                        original_label = site_radio.label
                        site_radio.label = truncate(original_label, LAYOUT_TRUNCATED_LABEL_MAX_LENGTH)
                        render_radio(site_radio, FieldKind.SITE, site_index,
                                xb + col_x, LAYOUT_TRUNCATED_LABEL_MAX_LENGTH)
                        site_radio.label = original_label

            if (overflow_count > 0 and i == sites_per_column - 1 and sites_visible):
                overflow_text: str = f"+{overflow_count} more"
                overflow_x: int = self.bounds.width - len(overflow_text) - LAYOUT_OVERFLOW_INDICATOR_MARGIN
                safe_addstr(stdscr, y_current, overflow_x, overflow_text, curses.A_DIM)

            y_current += 1

    def __get_sites_per_column(self) -> int:
        """
        Rows of sites per column: fixed when constrained (results pane), else as many
        as fit the form pane.
        """
        if self.live:
            return LAYOUT_CONSTRAINED_SITES_PER_COLUMN
        return min(self.bounds.height - LAYOUT_SITES_VERTICAL_OFFSET, len(self.__sites_group.radios))

    def __handle_enter(self) -> Optional[Action]:
        """
        ENTER: search from the query field; toggle a radio otherwise (live-searching
        immediately when the results pane is showing).
        """
        if self._selected_index == QUERY_INDEX:
            return RunSearch(immediate=False)
        self.__handle_radio_toggle()
        return RunSearch(immediate=True) if self.live else None

    def __handle_radio_toggle(self) -> None:
        """
        Toggle the radio under the current selection (filter, sort, or site).
        """
        ref = self.__layout().resolve(self._selected_index)
        if ref is None or ref.kind == FieldKind.QUERY:
            return

        if ref.kind == FieldKind.FILTER:
            self.__filter_group.radios[ref.offset].next_state()
        elif ref.kind == FieldKind.SORT:
            self.__sort_group.radios[ref.offset].next_state()
        elif ref.kind == FieldKind.SITE:
            if ref.offset < len(self.__sites) and ref.offset < len(self.__sites_group.radios):
                self.__sites_group.radios[ref.offset].next_state()
                self.__sites_selected = [self.__sites[ref.offset]]

    def __handle_spacebar(self) -> Optional[Action]:
        """
        SPACE: insert into the query, or toggle a radio (live-searching when showing
        the results pane).
        """
        if self._selected_index == QUERY_INDEX:
            self.__query_input.insert_char(" ")
            return RunSearch(immediate=False)
        self.__handle_radio_toggle()
        return RunSearch(immediate=False) if self.live else None

    def __navigate(self, direction: NavigationDirection) -> None:
        """
        Move the selection. On the query field, LEFT/RIGHT move the text cursor; every
        other movement, on every field, routes through the one FieldLayout grid so
        vertical and horizontal navigation share a single model.
        """
        if self._selected_index == QUERY_INDEX and direction in (
                NavigationDirection.LEFT, NavigationDirection.RIGHT):
            if direction == NavigationDirection.LEFT:
                self.__query_input.move_cursor_left()
            else:
                self.__query_input.move_cursor_right()
            return

        layout = self.__layout()
        move = {
            NavigationDirection.UP: layout.up,
            NavigationDirection.DOWN: layout.down,
            NavigationDirection.LEFT: layout.left,
            NavigationDirection.RIGHT: layout.right,
        }[direction]

        new_index = move(self._selected_index)
        if new_index is not None:
            self._selected_index = new_index