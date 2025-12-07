import curses
import os
import traceback

from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING

from mcp_server_webcrawl.crawlers import VALID_CRAWLER_CHOICES, get_crawler
from mcp_server_webcrawl.crawlers.base.api import BaseJsonApi
from mcp_server_webcrawl.crawlers.base.crawler import BaseCrawler
from mcp_server_webcrawl.interactive.ui import InputRadioGroup, InputText, ThemeDefinition, UiState
from mcp_server_webcrawl.interactive.views.base import BaseCursesView
from mcp_server_webcrawl.interactive.ui import safe_addstr
from mcp_server_webcrawl.interactive.views.searchform import SearchFormView

if TYPE_CHECKING:
    from mcp_server_webcrawl.interactive.session import InteractiveSession

LAYOUT_BOX_MAX_WIDTH = 60
LAYOUT_BOX_MARGIN = 8
VALIDATION_HEADER_X_OFFSET = 24
VALIDATION_TEXT_INDENT = 2

class RequirementsFormField(Enum):
    DATASRC = auto()
    CRAWLER = auto()

class RequirementsView(BaseCursesView):
    """
    Interactive requirements view for configuring crawler and data source.
    """

    def __init__(self, session: 'InteractiveSession', crawler: str, datasrc: str):
        """
        Initialize the requirements view.
        
        Args:
            session: The interactive session instance
            crawler: Initial crawler type selection
            datasrc: Initial data source path
        """
        super().__init__(session)
        self.__validated: bool = self.__validate(crawler, datasrc)
        self.__form_selected_field: RequirementsFormField = RequirementsFormField.DATASRC
        self.__form_selected_index: int = 0

        initial_datasrc: str = datasrc if datasrc is not None else self.__get_default_directory()
        self.__datasrc_input: InputText = InputText(initial_value=initial_datasrc, label="Data Source Path")

        self.__crawler_group: InputRadioGroup = InputRadioGroup("crawler")

        if not self.__validated:
            detected_crawler: str | None
            detected_datasrc: str | None
            detected_crawler, detected_datasrc = self.__autosense_crawler_and_datasrc()
            initial_crawler: str = crawler if crawler is not None else detected_crawler
            initial_datasrc = datasrc if datasrc is not None else detected_datasrc
            self.__set_initial_crawler_selection(initial_crawler)
            self.__datasrc_input.set_value(initial_datasrc)
            self._focused: bool = True

    @property
    def validated(self) -> bool:
        return self.__validated

    def handle_input(self, key: int) -> bool:
        """
        Handle keyboard input for requirements form navigation and validation.
        
        Args:
            key: The curses key code from user input
            
        Returns:
            bool: True if the input was handled, False otherwise
        """

        handlers: dict[int, callable] = {
            curses.KEY_UP: self.__navigate_form_selection_up,
            curses.KEY_DOWN: self.__navigate_form_selection_down,
            ord('\t'): self.__handle_tab,
            ord(' '): self.__handle_spacebar,
            ord('\n'): self.__handle_enter,
            ord('\r'): self.__handle_enter,
        }

        handler = handlers.get(key)
        if handler:
            handler()
            return True

        if (self.__form_selected_field == RequirementsFormField.DATASRC and
            self.__form_selected_index == 0):
            return self.__datasrc_input.handle_input(key)

        return False

    def render(self, stdscr: curses.window) -> None:
        """
        Render the requirements form showing crawler selection and datasrc input.
        
        Args:
            stdscr: The curses window to draw on
        """
        xb: int = self.bounds.x
        yb: int = self.bounds.y
        y_current: int = yb + 2
        # y_max: int = yb + self.bounds.height

        safe_addstr(stdscr, y_current, xb + 2, "Data Source Path:", curses.A_BOLD)
        y_current += 1

        box_width: int = min(LAYOUT_BOX_MAX_WIDTH, self.bounds.width - LAYOUT_BOX_MARGIN)
        is_datasrc_selected: bool = (
                self.__form_selected_field == RequirementsFormField.DATASRC
                and self.__form_selected_index == 0
        )
        field_style: int
        if is_datasrc_selected:
            field_style = curses.A_REVERSE
        else:
            field_style = self.session.get_theme_color_pair(ThemeDefinition.INACTIVE_QUERY)

        self.__datasrc_input.render(stdscr, y_current, xb + 4, box_width,
                focused=is_datasrc_selected, style=field_style)

        y_current += 2

        crawler_y_start: int = y_current

        safe_addstr(stdscr, y_current, xb + 2, self.__crawler_group.label, curses.A_BOLD)
        y_current += 1

        for i, radio in enumerate(self.__crawler_group.radios):
            crawler_field_index: int = i + 1
            is_crawler_field_selected: bool = (self.__form_selected_field == RequirementsFormField.CRAWLER and
                    self.__form_selected_index == crawler_field_index)

            radio.render(stdscr, y_current, xb + 4, crawler_field_index, 100, is_crawler_field_selected)
            y_current += 1

        validation_y: int = crawler_y_start

        selected_crawler: str = self.__crawler_group.value
        crawler_valid: bool = selected_crawler in VALID_CRAWLER_CHOICES
        crawler_symbol: str = "🗹" if crawler_valid else "☒"

        crawler_style: int
        if crawler_valid:
            crawler_style = curses.A_NORMAL
        else:
            crawler_style = self.session.get_theme_color_pair(ThemeDefinition.UI_ERROR)

        datasrc_path: str = self.__datasrc_input.value
        datasrc_path_obj: Path = Path(datasrc_path)
        datasrc_exists: bool = datasrc_path_obj.exists()

        datasrc_symbol: str
        datasrc_valid: bool
        if not datasrc_exists:
            datasrc_symbol = "☒"
            datasrc_valid = False
        else:
            is_correct_type: bool
            if selected_crawler in ("interrobot", "warc"):
                is_correct_type = datasrc_path_obj.is_file()
            else:
                is_correct_type = datasrc_path_obj.is_dir()

            datasrc_symbol = "🗹" if is_correct_type else "☒"
            datasrc_valid = is_correct_type

        datasrc_style: int
        if datasrc_valid:
            datasrc_style = curses.A_NORMAL
        else:
            datasrc_style = self.session.get_theme_color_pair(ThemeDefinition.UI_ERROR)

        validation_header: str = "Validation Status:"
        header_x: int = xb + VALIDATION_HEADER_X_OFFSET
        safe_addstr(stdscr, validation_y, header_x, validation_header, curses.A_BOLD)
        validation_y += 1

        validation_word_x: int = header_x
        crawler_text: str = f"{crawler_symbol}  --crawler"
        safe_addstr(stdscr, validation_y, validation_word_x, "  ", curses.A_NORMAL)
        safe_addstr(stdscr, validation_y, validation_word_x + VALIDATION_TEXT_INDENT, crawler_text, crawler_style)
        validation_y += 1

        datasrc_text: str = f"{datasrc_symbol}  --datasrc"
        safe_addstr(stdscr, validation_y, validation_word_x, "  ", curses.A_NORMAL)
        safe_addstr(stdscr, validation_y, validation_word_x + VALIDATION_TEXT_INDENT, datasrc_text, datasrc_style)

    def __autosense_crawler_and_datasrc(self) -> tuple[str, str] | tuple[None, None]:
        """
        Auto-detect crawler type and datasrc based on cwd and parent directory signatures.
        
        Returns:
            tuple: (crawler, datasrc) tuple or (None, None) if no match found
        """
        cwd: Path = Path(os.getcwd()).absolute()

        if list(cwd.glob("*.v2.db")):
            db_file: Path = next(cwd.glob("*.v2.db"))
            return ("interrobot", str(db_file))

        archive_directories: list[Path] = list(cwd.glob("*/archive"))
        if archive_directories:
            for archive_directory in archive_directories:
                timestamp_directories: list[Path] = [d for d in archive_directory.iterdir()
                        if d.is_dir() and d.name.replace('.', '').isdigit()]
                if timestamp_directories:
                    return ("archivebox", str(cwd))

        if list(cwd.glob("*/output.*.txt")):
            return ("siteone", str(cwd))

        if list(cwd.glob("*/hts-log.txt")) or list(cwd.glob("*/*/hts-log.txt")):
            return ("httrack", str(cwd))

        katana_files: list[Path] = list(cwd.glob("*/*/*.txt"))
        for f in katana_files:
            if len(f.stem) == 40 and all(c in '0123456789abcdef' for c in f.stem.lower()):
                return ("katana", str(cwd))

        warc_files: list[Path] = list(cwd.glob("*.warc.gz")) + list(cwd.glob("*.warc"))
        if warc_files:
            return ("warc", str(cwd))

        if list(cwd.glob("*/index.html")):
            return ("wget", str(cwd))

        return ("wget", self.__get_default_directory())

    def __get_default_directory(self) -> str:
        """
        Get the default directory path.
        
        Returns:
            str: The absolute path of the current working directory
        """
        return str(Path(os.getcwd()).absolute())

    def __handle_enter(self) -> None:
        """
        Handle ENTER key to revalidate in datasrc field or toggle in crawler field.
        """
        if self.__form_selected_field == RequirementsFormField.DATASRC:
            selected_crawler: str = self.__crawler_group.value
            self.__validated = self.__validate(selected_crawler, self.__datasrc_input.value)
            self.__update_session()
            if self.__validated:
                self.session.set_ui_state(UiState.SEARCH_INIT)
        elif self.__form_selected_field == RequirementsFormField.CRAWLER:
            crawler_index: int = self.__form_selected_index - 1
            if 0 <= crawler_index < len(self.__crawler_group.radios):
                self.__crawler_group.radios[crawler_index].next_state()

    def __handle_spacebar(self) -> None:
        """
        Handle spacebar to toggle crawler selection or add space to datasrc.
        """
        if self.__form_selected_field == RequirementsFormField.DATASRC:
            self.__datasrc_input.handle_input(ord(" "))
        elif self.__form_selected_field == RequirementsFormField.CRAWLER:
            crawler_index: int = self.__form_selected_index - 1
            if 0 <= crawler_index < len(self.__crawler_group.radios):
                self.__crawler_group.radios[crawler_index].next_state()

    def __handle_tab(self) -> None:
        """
        Handle TAB key to switch between field groups.
        """
        if self.__form_selected_field == RequirementsFormField.DATASRC:
            self.__form_selected_field = RequirementsFormField.CRAWLER
            self.__form_selected_index = 1
        else:
            self.__form_selected_field = RequirementsFormField.DATASRC
            self.__form_selected_index = 0

    def __navigate_form_selection_down(self) -> None:
        """
        Navigate down within current field or switch to next field group.
        """
        if self.__form_selected_field == RequirementsFormField.DATASRC:
            self.__form_selected_field = RequirementsFormField.CRAWLER
            self.__form_selected_index = 1
        elif self.__form_selected_field == RequirementsFormField.CRAWLER:
            if self.__form_selected_index < len(self.__crawler_group.radios):
                self.__form_selected_index += 1
            else:
                self.__form_selected_field = RequirementsFormField.DATASRC
                self.__form_selected_index = 0

    def __navigate_form_selection_up(self) -> None:
        """
        Navigate up within current field or switch to previous field group.
        """
        if self.__form_selected_field == RequirementsFormField.DATASRC:
            self.__form_selected_field = RequirementsFormField.CRAWLER
            self.__form_selected_index = len(self.__crawler_group.radios)
        elif self.__form_selected_field == RequirementsFormField.CRAWLER:
            if self.__form_selected_index > 1:
                self.__form_selected_index -= 1
            else:
                self.__form_selected_field = RequirementsFormField.DATASRC
                self.__form_selected_index = 0

    def __set_initial_crawler_selection(self, initial_crawler: str) -> None:
        """
        Set the initial crawler selection in the radio group.
        
        Args:
            initial_crawler: The crawler type to initially select
        """
        if initial_crawler in VALID_CRAWLER_CHOICES:
            crawler_index: int = VALID_CRAWLER_CHOICES.index(initial_crawler)
            if 0 <= crawler_index < len(self.__crawler_group.radios):
                self.__crawler_group.radios[crawler_index].next_state()

    def __update_session(self) -> None:
        """
        Update the session with current form values.
        """
        # push a new app  configuration into the ui
        selected_crawler: str = self.__crawler_group.value
        self.session.set_init_input_args(selected_crawler, self.__datasrc_input.value)
        if self.__validated:
            try:
                crawl_model: BaseCrawler = get_crawler(selected_crawler)
                crawler: BaseCrawler = crawl_model(Path(self.__datasrc_input.value))
                self.session.set_init_crawler(crawler)
                sites_api: BaseJsonApi = self.session.crawler.get_sites_api()
                self.session.set_init_sites(sites_api.get_results())
                searchform: SearchFormView = SearchFormView(
                    self.session,
                    self.session.sites
                )
                self.session.set_init_searchform(searchform)
            except Exception as ex:
                self.session.debug_add(f"Error initializing crawler: {ex}\n{traceback.format_exc()}")
                self.__validated = False

    def __validate(self, crawler: str, datasrc: str) -> bool:
        """
        Validate crawler and datasrc combination.
        
        Args:
            crawler: The crawler type to validate
            datasrc: The data source path to validate
            
        Returns:
            bool: True if the combination is valid, False otherwise
        """
        if not isinstance(datasrc, str) or not isinstance(crawler, str):
            return False

        crawler_valid: bool = crawler in VALID_CRAWLER_CHOICES

        if datasrc in (None, ""):
            return False

        datasrc_path: Path = Path(datasrc)
        if not datasrc_path.exists():
            return False

        if crawler in ("interrobot", "warc"):
            datasrc_valid = datasrc_path.is_file()
        else:
            datasrc_valid = datasrc_path.is_dir()

        return crawler_valid and datasrc_valid
