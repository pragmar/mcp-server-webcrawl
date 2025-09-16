import curses

from typing import TYPE_CHECKING

from mcp_server_webcrawl.interactive.ui import (
    UiState, InputRadio, InputRadioGroup, InputText,
    ThemeDefinition, NavigationDirection, safe_addstr
)
from mcp_server_webcrawl.interactive.views.base import BaseCursesView
from mcp_server_webcrawl.models.sites import SiteResult
from mcp_server_webcrawl.interactive.ui import safe_addstr

if TYPE_CHECKING:
    from mcp_server_webcrawl.interactive.session import InteractiveSession

LAYOUT_QUERY_MAX_WIDTH = 50
LAYOUT_QUERY_MARGIN = 11
LAYOUT_QUERY_OFFSET = 9
LAYOUT_FILTER_COLUMN_PADDING = 8
LAYOUT_SORT_COLUMN_PADDING = 6
LAYOUT_FILTER_TO_SORT_SPACING = 8
LAYOUT_SORT_TO_SITES_SPACING = 6
LAYOUT_SITE_COLUMN_WIDTH = 18
LAYOUT_SITE_COLUMN_SPACING = 2
LAYOUT_CONSTRAINED_SITES_PER_COLUMN = 3
LAYOUT_SITES_VERTICAL_OFFSET = 6
LAYOUT_SITES_MIN_WIDTH_REQUIREMENT = 10
LAYOUT_TRUNCATED_LABEL_MAX_LENGTH = 12
LAYOUT_OVERFLOW_INDICATOR_MARGIN = 2

class SearchFormView(BaseCursesView):
    """
    Handles search form state and rendering.
    Takes over all the form_* properties and methods from session.
    """

    def __init__(self, session: 'InteractiveSession', sites: list[SiteResult]):
        """
        Initialize the search form view.
        
        Args:
            session: The interactive session instance
            sites: List of available sites for selection
        """
        super().__init__(session)
        self.__search_attempted: bool = False
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
    def limit(self) -> str:
        return self.__limit

    @property
    def offset(self) -> str:
        return self.__offset

    @property
    def query(self) -> str:
        return self.__query_input.value

    @property
    def sort(self) -> str:
        return self.__sort_group.value.lower() if self.__sort_group.value is not None else "+url"

    def clear_query(self) -> None:
        """
        Clear only the query, preserve selections (was session method).
        """
        self.__search_attempted = False
        self.__query_input.clear()
        self._selected_index = 0

    def focus(self):
        """
        Set focus on this view.
        """
        self._focused = True

    def get_selected_sites(self) -> list[SiteResult]:
        return self.__sites_selected.copy()

    def handle_input(self, key: int) -> bool:
        """
        Handle keyboard input and trigger search when state changes.
        
        Args:
            key: The curses key code from user input
            
        Returns:
            bool: True if the input was handled, False otherwise
        """

        handlers: dict[int, callable] = {
            curses.KEY_UP: lambda: self.__navigate_form_selection(NavigationDirection.UP),
            curses.KEY_DOWN: lambda: self.__navigate_form_selection(NavigationDirection.DOWN),
            curses.KEY_LEFT: self.__handle_left_arrow,
            curses.KEY_RIGHT: self.__handle_right_arrow,
            ord(' '): self.__handle_spacebar,
            ord('\n'): self.__handle_enter,
            ord('\r'): self.__handle_enter,
        }

        handler = handlers.get(key)
        if handler:
            handler()
            return True

        if self._selected_index == 0:
            if self.__query_input.handle_input(key):
                self.session.searchman.autosearch()
                return True

        return False

    def page_next(self, total_results: int) -> bool:
        """
        Navigate to next page.
        
        Args:
            total_results: Total number of search results available
            
        Returns:
            bool: True if page was changed, False otherwise
        """
        if self.__offset + self.__limit < total_results:
            self.__offset += self.__limit
            return True
        return False

    def page_previous(self) -> bool:
        """
        Navigate to previous page.
        
        Returns:
            bool: True if page was changed, False otherwise
        """
        if self.__offset >= self.__limit:
            self.__offset -= self.__limit
            return True
        return False

    def _truncate_label(self, label: str, max_length: int = LAYOUT_TRUNCATED_LABEL_MAX_LENGTH) -> str:
        """
        Truncate label to max_length, replacing last char with ellipsis if needed.
        
        Args:
            label: The label text to truncate
            max_length: Maximum allowed length for the label
            
        Returns:
            str: The truncated label with ellipsis if needed
        """
        if len(label) <= max_length:
            return label
        return label[:max_length - 1] + "…"

    def render(self, stdscr: curses.window) -> None:
        """
        Render the search form with multi-column sites layout.
        """
        xb: int = self.bounds.x
        yb: int = self.bounds.y
        y_current: int = yb + 2  # y start
        y_max: int = yb + self.bounds.height

        if not self._renderable(stdscr):
            return

        safe_addstr(stdscr, y_current, xb + 2, "Query:")

        box_width = min(LAYOUT_QUERY_MAX_WIDTH, self.bounds.width - LAYOUT_QUERY_MARGIN)
        is_query_selected = (self._focused and self._selected_index == 0)

        self.__query_input.render(stdscr, y_current, xb + LAYOUT_QUERY_OFFSET, box_width,
                focused=is_query_selected, style=self._get_input_style())

        y_current += 2
        if y_current >= y_max:
            return

        # radio column layout - calculated positions based on content width
        filter_column_width = self.__filter_group.calculate_group_width() + LAYOUT_FILTER_COLUMN_PADDING
        sort_column_width = self.__sort_group.calculate_group_width() + LAYOUT_SORT_COLUMN_PADDING
        sort_start_x = filter_column_width + LAYOUT_FILTER_TO_SORT_SPACING
        sites_start_x = sort_start_x + sort_column_width + LAYOUT_SORT_TO_SITES_SPACING

        safe_addstr(stdscr, y_current, xb + 2, self.__filter_group.label)
        safe_addstr(stdscr, y_current, xb + sort_start_x, self.__sort_group.label)
        if sites_start_x + LAYOUT_SITES_MIN_WIDTH_REQUIREMENT < self.bounds.width:
            safe_addstr(stdscr, y_current, xb + sites_start_x, self.__sites_group.label)
            if not self.__sites:
                error_style = self.session.get_theme_color_pair(ThemeDefinition.UI_ERROR)
                safe_addstr(stdscr, y_current + 1, xb + sites_start_x, "No sites available", error_style)

        y_current += 1

        available_width = self.bounds.width - sites_start_x - 4
        is_constrained = self.session.ui_state == UiState.SEARCH_RESULTS
        sites_per_column = (LAYOUT_CONSTRAINED_SITES_PER_COLUMN if is_constrained
                           else min(self.bounds.height - LAYOUT_SITES_VERTICAL_OFFSET, len(self.__sites_group.radios)))
        max_columns = (max(1, available_width // (LAYOUT_SITE_COLUMN_WIDTH + LAYOUT_SITE_COLUMN_SPACING))
                      if available_width > LAYOUT_SITE_COLUMN_WIDTH else 1)
        total_visible_sites = max_columns * sites_per_column
        overflow_count = max(0, len(self.__sites_group.radios) - total_visible_sites)
        max_rows = max(len(self.__filter_group.radios), len(self.__sort_group.radios), sites_per_column)

        for i in range(max_rows):

            if y_current >= y_max:
                return

            # filter radios
            if i < len(self.__filter_group.radios):
                filter_radio: InputRadio = self.__filter_group.radios[i]
                field_index: int = 1 + i
                is_selected: bool = self._selected_index == field_index
                filter_radio.render(stdscr, y_current, xb + 2, field_index, 100, is_selected)

            # sorts radios
            if i < len(self.__sort_group.radios):
                sort_radio: InputRadio = self.__sort_group.radios[i]
                field_index: int = 1 + len(self.__filter_group.radios) + i
                is_selected: bool = self._selected_index == field_index
                sort_radio.render(stdscr, y_current, xb + sort_start_x, field_index, 100, is_selected)

            # sites radios - multiple columns
            if sites_start_x + LAYOUT_SITES_MIN_WIDTH_REQUIREMENT < self.bounds.width:
                for col in range(max_columns):
                    site_index = col * sites_per_column + i
                    if site_index < len(self.__sites_group.radios) and site_index < total_visible_sites:
                        site_radio: InputRadio = self.__sites_group.radios[site_index]
                        field_index: int = 1 + len(self.__sort_group.radios) + len(self.__filter_group.radios) + site_index
                        is_selected: bool = self._selected_index == field_index
                        col_x = sites_start_x + col * (LAYOUT_SITE_COLUMN_WIDTH + LAYOUT_SITE_COLUMN_SPACING)
                        original_label = site_radio.label
                        site_radio.label = self._truncate_label(original_label)
                        site_radio.render(stdscr, y_current, xb + col_x, field_index, LAYOUT_TRUNCATED_LABEL_MAX_LENGTH, is_selected)
                        site_radio.label = original_label  # restore original label

            # overflow indicator on last row, right-aligned
            if (overflow_count > 0 and i == sites_per_column - 1 and
                sites_start_x + LAYOUT_SITES_MIN_WIDTH_REQUIREMENT < self.bounds.width):
                overflow_text: str = f"+{overflow_count} more"
                overflow_x: int = self.bounds.width - len(overflow_text) - LAYOUT_OVERFLOW_INDICATOR_MARGIN
                try:
                    safe_addstr(stdscr, y_current, overflow_x, overflow_text, curses.A_DIM)
                except curses.error:
                    pass

            y_current += 1

    def set_search_attempted(self) -> None:
        """
        Set attempted to True.
        """
        self.__search_attempted = True

    def unfocus(self):
        """
        Remove focus from this view.
        """
        self._focused = False

    def _calculate_group_width(self, group: InputRadioGroup) -> int:
        """
        Calculate the display width needed for a radio group.
        
        Args:
            group: The radio group to calculate width for
            
        Returns:
            int: The minimum width needed to display the group
        """
        if not group.radios:
            return 20
        return max(len(radio.label) for radio in group.radios)

    def __handle_enter(self) -> None:
        """
        Handle ENTER key - only toggles radio buttons, doesn't affect query field.
        """

        if self._selected_index == 0:  # query field
            self.session.searchman.autosearch()
        else:  # radios
            self.__handle_radio_toggle()
            if self.session.ui_state != UiState.SEARCH_INIT:
                self.session.searchman.autosearch(immediate=True)


    def __handle_radio_toggle(self) -> None:
        """
        Handle radio button toggles for filters and sites.
        """
        filter_index_start: int = 1
        sorts_index_start: int = filter_index_start + len(self.__filter_group.radios)
        sites_index_start: int = sorts_index_start + len(self.__sort_group.radios)

        if self._selected_index >= filter_index_start and self._selected_index < sorts_index_start:
            filter_index = self._selected_index - filter_index_start
            filter_input: InputRadio = self.__filter_group.radios[filter_index]
            filter_input.next_state()
        elif self._selected_index >= sorts_index_start and self._selected_index < sites_index_start:
            sort_index = self._selected_index - sorts_index_start
            sort_input: InputRadio = self.__sort_group.radios[sort_index]
            sort_input.next_state()
        elif self._selected_index >= sites_index_start:
            site_index = self._selected_index - sites_index_start
            if site_index < len(self.__sites) and site_index < len(self.__sites_group.radios):
                site_input: InputRadio = self.__sites_group.radios[site_index]
                site_input.next_state()
                self.__sites_selected = [self.__sites[site_index]]

    def __handle_horizontal_arrow(self, direction: NavigationDirection) -> None:
        """
        Handle left/right arrow navigation using group helpers.
        
        Args:
            direction: The navigation direction (LEFT or RIGHT)
        """
        if self.session.ui_state is None:
            return

        # query handles self
        if self._selected_index == 0:
            if direction == NavigationDirection.LEFT:
                self.__query_input.move_cursor_left()
            else:
                self.__query_input.move_cursor_right()
            return

        # try navigation within current group first
        current_group, group_index = self.__get_current_group_and_index()
        if current_group:
            if direction == NavigationDirection.LEFT:
                new_group_index = current_group.navigate_left(group_index)
            else:
                new_group_index = current_group.navigate_right(group_index)

            if new_group_index is not None:
                self._selected_index = self.__convert_to_absolute_index(current_group, new_group_index)
                return

        # group can't handle it try xgroup navigation
        self.__navigate_between_groups(direction)

    def __handle_left_arrow(self) -> None:
        """
        Handle left arrow key navigation.
        """
        self.__handle_horizontal_arrow(NavigationDirection.LEFT)

    def __handle_right_arrow(self) -> None:
        """
        Handle right arrow key navigation.
        """
        self.__handle_horizontal_arrow(NavigationDirection.RIGHT)

    def __get_field_boundaries(self) -> tuple[int, int, int]:
        """
        Get start indices for each field group.
        
        Returns:
            tuple: (filter_start, sorts_start, sites_start) indices
        """
        filter_start = 1
        sorts_start = filter_start + len(self.__filter_group.radios)
        sites_start = sorts_start + len(self.__sort_group.radios)
        return filter_start, sorts_start, sites_start

    def __get_current_group_and_index(self) -> tuple[InputRadioGroup, int]:
        """
        Get the current group and relative index within that group.
        
        Returns:
            tuple: (current_group, group_relative_index)
        """
        filter_start, sorts_start, sites_start = self.__get_field_boundaries()

        if self._selected_index < sorts_start:
            return self.__filter_group, self._selected_index - filter_start
        elif self._selected_index < sites_start:
            return self.__sort_group, self._selected_index - sorts_start
        else:
            return self.__sites_group, self._selected_index - sites_start

    def __convert_to_absolute_index(self, group: InputRadioGroup, group_index: int) -> int:
        """
        Convert group-relative index back to absolute selection index.
        
        Args:
            group: The radio group containing the index
            group_index: The index within the group
            
        Returns:
            int: The absolute selection index
        """
        filter_start, sorts_start, sites_start = self.__get_field_boundaries()
        group_start_map = {
            "filter": filter_start,
            "sort": sorts_start,
            "site": sites_start,
        }
        return group_start_map[group.name] + group_index

    def __navigate_between_groups(self, direction: NavigationDirection) -> None:
        """
        Handle navigation between different radio groups.
        
        Args:
            direction: The navigation direction (LEFT or RIGHT)
        """
        current_group, group_index = self.__get_current_group_and_index()
        current_row = current_group.get_row_from_index(group_index)
        group_map = {
            (NavigationDirection.LEFT, "site"): self.__sort_group,
            (NavigationDirection.LEFT, "sort"): self.__filter_group,
            (NavigationDirection.RIGHT, "filter"): self.__sort_group,
            (NavigationDirection.RIGHT, "sort"): self.__sites_group,
        }
        target_group = group_map.get((direction, current_group.name))
        if target_group:
            new_index = target_group.navigate_to_row(current_row)
            if new_index is not None:
                self._selected_index = self.__convert_to_absolute_index(target_group, new_index)

    def __handle_spacebar(self) -> None:
        """
        Handle spacebar for toggles. Updated for new field order: Query, Filters, Sites.
        """
        if self._selected_index == 0:               # query field
            self.__query_input.insert_char(" ")
            self.session.searchman.autosearch()
        else:                                       # radios
            self.__handle_radio_toggle()
            if self.session.ui_state != UiState.SEARCH_INIT:
                self.session.searchman.autosearch()

    def __navigate_form_selection(self, direction: NavigationDirection) -> None:
        """
        Navigate between form fields. Updated for new field order: Query, Filters, Sites.

        Args:
            direction: The navigation direction (UP or DOWN)
        """
        # query(0), filters(1-2), sorts(3-5), sites(...)
        last_field_index = 5 + len(self.__sites)
        if direction == NavigationDirection.UP:
            if self._selected_index == 0:
                self._selected_index = last_field_index
            else:
                self._selected_index -= 1
        elif direction == NavigationDirection.DOWN:
            if self._selected_index == last_field_index:
                self._selected_index = 0
            else:
                self._selected_index += 1
