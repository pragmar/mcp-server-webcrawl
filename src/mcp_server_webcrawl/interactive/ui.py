import curses

from enum import Enum, auto
from typing import NamedTuple, Optional, Tuple

from mcp_server_webcrawl.crawlers import VALID_CRAWLER_CHOICES

SITE_COLUMN_WIDTH = 18

LAYOUT_GRID_COLUMN_SPACING = 2
LAYOUT_CONSTRAINED_SITES_PER_COLUMN = 3
LAYOUT_SITES_GRID_OFFSET = 6

DEFAULT_GROUP_WIDTH = 12

INPUT_BOX_BRACKET_WIDTH = 2
CURSOR_SCROLL_THRESHOLD = 5

class DocumentMode(Enum):
    MARKDOWN = auto()
    RAW = auto()
    HEADERS = auto()

class NavigationDirection(Enum):
    UP = auto()
    DOWN = auto()
    LEFT = auto()
    RIGHT = auto()

class ScrollDirection(Enum):
    UP = auto()
    DOWN = auto()

class SearchFilterType(Enum):
    ANY = 0
    PAGES = 1

class ThemeDefinition(Enum):
    # https://www.ditig.com/256-colors-cheat-sheet
    DOCUMENT_MODE = (1, curses.COLOR_BLUE, 51)
    HEADER_ACTIVE = (2, curses.COLOR_WHITE, 17)
    HEADER_INACTIVE = (3, curses.COLOR_WHITE, 233)
    HEADER_OUTER = (4, curses.COLOR_WHITE, 235)
    HELP_LINK = (5, curses.COLOR_WHITE, 27)
    HTTP_ERROR = (6, curses.COLOR_WHITE, 88)
    HTTP_WARN = (7, curses.COLOR_WHITE, 130)
    INACTIVE_QUERY = (8, 245, 237)
    SNIPPET_DEFAULT = (9, 243, curses.A_DIM)
    SNIPPET_HIGHLIGHT = (10, 232, 51)
    UI_ERROR = (11, curses.COLOR_WHITE, 88)

class UiFocusable(Enum):
    UNDEFINED = auto()
    SEARCH_FORM = auto()
    SEARCH_RESULTS = auto()

class UiState(Enum):
    UNDEFINED = auto()
    REQUIREMENTS = auto()
    SEARCH_INIT = auto()
    SEARCH_RESULTS = auto()
    DOCUMENT = auto()
    HELP = auto()

def safe_addstr(stdscr: curses.window, y: int, x: int, text: str, style: int = curses.A_NORMAL) -> None:
    """
    Safe addstr that handles screen edge errors.
    """
    try:
        stdscr.addstr(y, x, text, style)
    except curses.error:
        pass

class InputRadio:
    def __init__(self, group, name: str, label: str, index: int, states: list = None):
        """
        Radio input with 2-3 possible states (e.g., on/off or state1/state2/off)
        
        Args:
            group: The InputRadioGroup this radio belongs to
            name: The form radio group name
            label: The form radio label  
            index: The current state index
            states: List of InputRadioState objects defining each possible state            
        """
        # used like so states_radio = InputRadio(groupname, label, index, states=InputRadioGroup.get_filters())
        if states is None:
            states = []
        assert states, "states must be provided and non-empty"
        assert 0 <= index < len(states), f"index {index} out of range for {len(states)} states"

        self.name = name
        self.label = label
        self.index = index
        self._states = states
        self._group = group


    @property
    def current_state(self):
        """
        Get the current state
        """
        return self._states[self.index]

    @property
    def display_label(self) -> str:
        """
        Get the current display label
        """
        return self.current_state.label

    @property
    def value(self) -> str:
        """
        Get the current value
        """
        return self.current_state.value

    def next_state(self) -> None:
        """
        Cycle to the next state
        """
        # clear group for single-selection radios
        if self._group.name in ["filter", "site", "crawler"]:
            self._group.clear()

        if self._group.name == "sort":
            if self.index == 0:         # inactive " " -> active ascending "+"
                self._group.clear()
                self.index = 1
            elif self.index == 1:       # ascending "+" -> descending "-"
                self.index = 2
            elif self.index == 2:       # descending "-" -> ascending "+"
                self.index = 1
        else:
            # standard cycling for other radios
            self.index = (self.index + 1) % len(self._states)

    def render(self, stdscr: curses.window, y: int, x: int, field_index: int, max_width: int = None, focused: bool = False) -> None:
        """
        Render a single radio option.
        """

        radio_symbol = self.display_label
        display_text = self.label
        if max_width and len(display_text) > max_width:
            display_text = display_text[:max_width - 1] + "…"

        line = f"({radio_symbol}) {display_text}"
        style = curses.A_REVERSE if focused else curses.A_NORMAL

        try:
            safe_addstr(stdscr, y, x, line, style)
        except curses.error:
            pass  # screen edge

    def set_state(self, index: int) -> None:
        """
        Set the current state by index
        """
        if 0 <= index < len(self._states):
            self.index = index
        else:
            raise IndexError(f"State index {index} out of range")

    def set_states(self, states: list) -> None:
        """
        Set the current state by index
        """
        self._states = states

    def __str__(self) -> str:
        return f"{self.label}: {self.display_label} ({self.value})"

class InputRadioGroup:
    """
    Radio group with navigation and layout management capabilities.
    """
    def __init__(self, name: str, sites: list = None):
        """
        Radio input group with layout and navigation support.
        
        Args:
            name: The form radio group name ("filter", "sort", "site", or "crawler")
            sites: List of SiteResult objects, required only for "site" group type
        """
        sites = sites if sites is not None else []
        self.name: str = name
        self.label: str = name
        self.__selected_index: int = 0

        # layout configuration
        self.__available_width: int = 0
        self.__available_height: int = 0
        self.__is_constrained: bool = False
        self.__sites_per_column: int = 0
        self.__max_columns: int = 0

        self.radios: list[InputRadio] = []

        group_config = {
            "filter": (self.__load_filters, "Filter:"),
            "site": (lambda: self.__load_sites(sites), "Sites:"),
            "sort": (self.__load_sorts, "Sorts:"),
            "crawler": (self.__load_crawlers, "Crawlers:"),
        }

        if self.name in group_config:
            data_loader, label = group_config[self.name]
            self.label = label
            data_loader()
        else:
            raise Exception(f"Unsupported radio option: {self.name}")

        if self.radios:
            self.radios[0].next_state()

    @property
    def value(self) -> str:
        for radio in self.radios:
            if radio.value == "on" or radio.display_label in ["+", "-"]:  # selected state
                if self.name == "filter":
                    return "html" if radio.label == "HTML" else ""
                elif self.name == "sort":
                    if radio.display_label == "+":
                        return f"+{radio.label}"
                    elif radio.display_label == "-":
                        return f"-{radio.label}"
                    return ""
                elif self.name == "site":
                    return radio.label  # or site ID/URL however you want to identify it
                elif self.name == "crawler":
                    return radio.label
        return ""

    def calculate_group_width(self) -> int:
        """
        Calculate the display width needed for a radio group.
        """
        if not self.radios:
            return DEFAULT_GROUP_WIDTH
        return max(len(radio.label) for radio in self.radios)

    def clear(self) -> None:
        for r in self.radios:
            r.index = 0

    def set_layout_constraints(self, available_width: int, available_height: int, is_constrained: bool = False) -> None:
        """
        Set layout constraints for grid-based groups (like sites).
        
        Args:
            available_width: Available horizontal space
            available_height: Available vertical space  
            is_constrained: Whether layout is constrained (affects sites per column)
        """
        self.__available_width = available_width
        self.__available_height = available_height
        self.__is_constrained = is_constrained

        if self.name == "site":
            self.__calculate_grid_layout()

    def get_grid_position(self, radio_index: int) -> Tuple[int, int]:
        """
        Convert linear radio index to grid position.
        Only applies to site groups; other groups return (radio_index, 0).
        
        Args:
            radio_index: Linear index in radios list
            
        Returns:
            tuple: (row, column) position in grid layout
        """
        if self.name != "site" or self.__sites_per_column == 0:
            return (radio_index, 0)

        row = radio_index % self.__sites_per_column
        col = radio_index // self.__sites_per_column
        return (row, col)

    def get_index_from_grid(self, row: int, col: int) -> Optional[int]:
        """
        Convert grid position to linear radio index.
        Only works for site groups; returns None for other group types.
    
        Args:
            row: Row in grid (0-based)
            col: Column in grid (0-based)
    
        Returns:
            Linear index if position exists within grid bounds, None otherwise
        """
        if self.name != "site":
            return row if 0 <= row < len(self.radios) else None
#
        if self.__sites_per_column == 0:
            return None
#
        radio_index = col * self.__sites_per_column + row
        if (0 <= radio_index < len(self.radios) and
            radio_index < self.__sites_per_column * self.__max_columns):
            return radio_index
        return None

    def navigate_left(self, current_radio_index: int) -> Optional[int]:
        """
        Navigate left within this group's layout.
        
        Args:
            current_radio_index: Current position in radios list
            
        Returns:
            New radio index if navigation successful, None if should exit group
        """
        if self.name != "site":
            # don't support horizontal navigation
            return None

        current_row, current_col = self.get_grid_position(current_radio_index)

        if current_col > 0:
            # to previous column, same row
            return self.get_index_from_grid(current_row, current_col - 1)
        else:
            # at leftmost column, signal exit to parent
            return None

    def navigate_right(self, current_radio_index: int) -> Optional[int]:
        """
        Navigate right within this group's layout.
        
        Args:
            current_radio_index: Current position in radios list
            
        Returns:
            New radio index if navigation successful, None if should exit group
        """
        if self.name != "site":
            # don't support horizontal navigation
            return None

        current_row, current_col = self.get_grid_position(current_radio_index)
        new_index = self.get_index_from_grid(current_row, current_col + 1)
        return new_index  # if invalid/out of bounds

    def navigate_to_row(self, target_row: int, from_column: int = 0) -> Optional[int]:
        """
        Navigate to a specific row from an external column position.
        """
        if self.name != "site":
            return target_row if 0 <= target_row < len(self.radios) else None

        if self.__sites_per_column == 0:
            return target_row if 0 <= target_row < len(self.radios) else None

        return self.get_index_from_grid(target_row, from_column)

    def get_row_from_index(self, radio_index: int) -> int:
        """
        Get the row number for navigation between groups.
        
        Args:
            radio_index: Linear index in radios list
            
        Returns:
            Row number for inter-group navigation
        """
        if self.name != "site":
            return radio_index

        row, _ = self.get_grid_position(radio_index)
        return row

    def __calculate_grid_layout(self) -> None:
        """
        Calculate grid layout parameters for sites group.
        """
        if self.name != "site":
            return

        self.__sites_per_column = (LAYOUT_CONSTRAINED_SITES_PER_COLUMN if self.__is_constrained
                                 else min(self.__available_height - LAYOUT_SITES_GRID_OFFSET, len(self.radios)))

        if self.__available_width > SITE_COLUMN_WIDTH:
            self.__max_columns = max(1, self.__available_width // (SITE_COLUMN_WIDTH + LAYOUT_GRID_COLUMN_SPACING))
        else:
            self.__max_columns = 1

    def __display_url(self, url: str) -> str:
        return url.split("://")[-1].rstrip("/")

    def __get_on_off_state(self) -> list:
        return [
            InputRadioState(" ", ""),
            InputRadioState("●", "on")
        ]

    def __load_crawlers(self) -> None:
        # "archivebox", "httrack", "interrobot", "katana", "siteone", "warc", "wget"
        self.radios = [
            InputRadio(self, "crawler", label, 0, self.__get_on_off_state())
            for label in VALID_CRAWLER_CHOICES
        ]

    def __load_filters(self) -> None:
        self.radios = [
            InputRadio(self, "filter", "HTML", 0, self.__get_on_off_state()),
            InputRadio(self, "filter", "any", 0, self.__get_on_off_state())
        ]

    def __load_sites(self, sites: list) -> None:
        site_labels = [self.__display_url(s.urls[0]) if s.urls else "unknown" for s in sites]
        self.radios = [
            InputRadio(self, "site", label, 0, self.__get_on_off_state())
            for label in site_labels
        ]

    def __load_sorts(self) -> None:
        sort_states = [
            InputRadioState(" ", ""),
            InputRadioState("+", "+"),
            InputRadioState("-", "-")
        ]

        sort_labels = ["URL", "status", "size"]

        self.radios = [
            InputRadio(self, "sort", label, 0, sort_states.copy())
            for label in sort_labels
        ]

class InputRadioState(NamedTuple):
    label: str  # "●", " ", "-", "+"
    value: str  # "", "+url", "-sort"

class InputText:
    """
    A reusable text input field with cursor management, rendering, and input handling.
    Consolidates the common text input functionality used across the application.
    """

    def __init__(self, initial_value: str = "", max_length: int = None, label: str = ""):
        """
        Initialize the text input field.
        
        Args:
            initial_value: Starting text value
            max_length: Maximum allowed text length (None for unlimited)
            label: Display label for the field
        """
        self.value: str = initial_value
        self.cursor_pos: int = len(initial_value)
        self.max_length: int = max_length
        self.label: str = label

        self._last_display_cache: Optional[tuple] = None
        self._last_value_hash: int = 0

    def backspace(self) -> None:
        """
        Remove the character before the cursor.
        """
        if self.cursor_pos > 0:
            self.value = self.value[:self.cursor_pos - 1] + self.value[self.cursor_pos:]
            self.cursor_pos -= 1

    def clear(self) -> None:
        """
        Clear all text and reset cursor.
        """
        self.value = ""
        self.cursor_pos = 0

    def delete(self) -> None:
        """
        Remove the character at the cursor position.
        """
        if self.cursor_pos < len(self.value):
            self.value = self.value[:self.cursor_pos] + self.value[self.cursor_pos + 1:]

    def end(self) -> None:
        """
        Move cursor to the end of the text.
        """
        self.cursor_pos = len(self.value)

    def handle_input(self, key: int) -> bool:
        """
        Handle keyboard input for the text field.
        
        Args:
            key: The curses key code
            
        Returns:
            bool: True if the input was handled, False otherwise
        """
        handlers: dict[int, callable] = {
            curses.KEY_LEFT: self.move_cursor_left,
            curses.KEY_RIGHT: self.move_cursor_right,
            curses.KEY_HOME: self.home,
            curses.KEY_END: self.end,
            curses.KEY_BACKSPACE: self.backspace,
            127: self.backspace,  # alternative backspace
            8: self.backspace,    # alternative backspace
            curses.KEY_DC: self.delete,
        }

        handler = handlers.get(key)
        if handler:
            handler()
            return True

        if 32 <= key <= 126:  # printable characters
            char: str = chr(key)
            self.insert_char(char)
            return True

        return False

    def home(self) -> None:
        """
        Move cursor to the beginning of the text.
        """
        self.cursor_pos = 0

    def insert_char(self, char: str) -> None:
        """
        Insert a character at the current cursor position.
        """
        sanitized = self.__sanitize_input(char)
        if sanitized is None:
            return

        if self.max_length is not None and len(self.value) >= self.max_length:
            return

        self.value = self.value[:self.cursor_pos] + char + self.value[self.cursor_pos:]
        self.cursor_pos += 1

    def is_empty(self) -> bool:
        """
        Check if the text field is empty.
        """
        return len(self.value.strip()) == 0

    def move_cursor_left(self) -> None:
        """
        Move cursor one position to the left.
        """
        if self.cursor_pos > 0:
            self.cursor_pos -= 1

    def move_cursor_right(self) -> None:
        """
        Move cursor one position to the right.
        """
        if self.cursor_pos < len(self.value):
            self.cursor_pos += 1

    def render(self, stdscr: curses.window, y: int, x: int, width: int,
               focused: bool = False, style: int = None) -> None:
        """
        Render the text input field with box, text, and cursor.
        
        Args:
            stdscr: The curses window
            y: Y position to render at
            x: X position to render at  
            width: Total width of the input box
            focused: Whether this field has focus (shows cursor)
            style: Curses style attributes to apply
        """

        # account for [ ] brackets
        inner_width = max(1, width - INPUT_BOX_BRACKET_WIDTH)
        display_text, display_cursor_pos = self.__calculate_display_text_and_cursor(inner_width)
        box_content = f"[{display_text.ljust(inner_width)}]"
        if style is None:
            style = curses.A_REVERSE if focused else curses.A_NORMAL

        safe_addstr(stdscr, y, x, box_content, style)
        if focused:
            self.__render_cursor(stdscr, y, x, display_text, display_cursor_pos, inner_width)

    def set_value(self, new_value: str) -> None:
        """
        Set the text value and adjust cursor if needed.
        """
        self.value = new_value
        # cursor doesn't go beyond text length
        self.cursor_pos = min(self.cursor_pos, len(self.value))

    def __sanitize_input(self, char: str) -> Optional[str]:
        """
        Sanitize input character, return None if should be rejected
        """
        # strip control characters
        if ord(char) < 32 or ord(char) == 127:
            return None
        # add more checks here as needed
        return char

    def __render_cursor(self, stdscr: curses.window, y: int, x: int,
                      display_text: str, display_cursor_pos: int, inner_width: int) -> None:
        """
        Render the cursor at the appropriate position.
        
        Args:
            stdscr: The curses window
            y: Y position of the input box
            x: X position of the input box
            display_text: The currently displayed text
            display_cursor_pos: Where the cursor appears in the displayed text
            inner_width: Available width inside the box
        """

        try:
            if display_cursor_pos < len(display_text) and display_cursor_pos < inner_width:
                cursor_x = x + 1 + display_cursor_pos
                # highlight the character under cursor instead of just reversing
                char_under_cursor = display_text[display_cursor_pos]
                safe_addstr(stdscr, y, cursor_x, char_under_cursor, curses.A_REVERSE | curses.A_BOLD)
            elif display_cursor_pos >= 0 and x + 1 + display_cursor_pos < x + 1 + inner_width:
                # cursor at end - underscore
                cursor_x = x + 1 + display_cursor_pos
                safe_addstr(stdscr, y, cursor_x, '_', curses.A_REVERSE | curses.A_BOLD)
        except curses.error:
            pass


    def __calculate_display_text_and_cursor(self, inner_width: int) -> tuple[str, int]:
        """
        Calculate what portion of text to display and where the cursor should appear.
        Handles horizontal scrolling for long text.
        
        Args:
            inner_width: Available width inside the input box
            
        Returns:
            tuple: (display_text, display_cursor_position)
        """
        current_hash = hash((self.value, self.cursor_pos, inner_width))
        if current_hash == self._last_value_hash and self._last_display_cache:
            return self._last_display_cache

        if len(self.value) <= inner_width:
            # text fits entirely
            return self.value, self.cursor_pos

        # text is longer than available space, scroll
        if self.cursor_pos >= inner_width - CURSOR_SCROLL_THRESHOLD:
            start_pos = max(0, len(self.value) - inner_width)
            display_text = self.value[start_pos:]
            display_cursor_pos = self.cursor_pos - start_pos
        else:
            display_text = self.value[:inner_width]
            display_cursor_pos = min(self.cursor_pos, inner_width)

        return display_text, display_cursor_pos

class ViewBounds:
    def __init__(self, x: int = 0, y: int = 0, width: int = 0, height: int = 0):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
