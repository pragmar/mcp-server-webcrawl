import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor, Future
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from mcp_server_webcrawl.crawlers.base.crawler import BaseJsonApi
from mcp_server_webcrawl.interactive.ui import UiFocusable, UiState
from mcp_server_webcrawl.models.resources import ResourceResult

if TYPE_CHECKING:
    from mcp_server_webcrawl.interactive.session import InteractiveSession

SEARCH_DEBOUNCE_DELAY_SECONDS = 0.2
SEARCH_RESULT_LIMIT: int = 10

class SearchManager:
    """
    Manages search operations including async search and debouncing.
    Works with session's controlled interface - never touches private state directly.
    """

    def __init__(self, session: 'InteractiveSession'):
        self.__session: 'InteractiveSession' = session
        self.__search_last_state_hash: str = ""
        self.__search_timer: Optional[threading.Timer] = None
        self.__executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="SearchManager")
        self.__search_lock: threading.RLock = threading.RLock()
        self.__search_in_progress: bool = False
        self.__active_search_future: Optional[Future] = None
        self.__pending_results: Optional[list[ResourceResult]] = None
        self.__pending_indexer_status: str = ""
        self.__pending_indexer_processed: int = 0
        self.__pending_indexer_duration: float = 0
        self.__pending_total: int = 0

    def autosearch(self, immediate: bool = False) -> None:
        """
        Trigger search with optional immediate execution.
        
        Args:
            immediate: If True, execute search synchronously without debouncing.
                    If False, use debounced async execution (default).
        """
        current_state_hash: str = self.__get_input_hash()

        if not immediate and current_state_hash == self.__search_last_state_hash:
            return

        self.__search_last_state_hash = current_state_hash
        self.cancel_pending()

        if immediate:
            self.__execute_search_immediate()
        else:
            self.__search_timer = threading.Timer(SEARCH_DEBOUNCE_DELAY_SECONDS, self.__execute_debounced_search)
            self.__search_timer.start()

    def cancel_pending(self) -> None:
        """
        Cancel any pending search timer.
        """
        if self.__search_timer is not None:
            self.__search_timer.cancel()
            self.__search_timer = None

        with self.__search_lock:
            if self.__active_search_future is not None:
                self.__active_search_future.cancel()
                self.__active_search_future = None

    def check_pending(self) -> None:
        """
        Check if there are pending search results and update the UI.
        """
        with self.__search_lock:
            if self.__pending_results is not None:
                self.__session.results.update(self.__pending_results, self.__pending_total, self.__pending_indexer_status,
                        self.__pending_indexer_processed, self.__pending_indexer_duration)
                self.__pending_results = None
                self.__pending_total = 0
                self.__pending_indexer_processed = 0
                self.__pending_indexer_duration = 0

    def cleanup(self) -> None:
        """
        Clean up any pending operations.
        """
        self.cancel_pending()
        self.__executor.shutdown(wait=True)

    def has_pending(self) -> bool:
        """
        Check if there's a pending debounced search.
        """
        return self.__search_timer is not None

    def is_searching(self) -> bool:
        """
        Check if a search is currently in progress or on a timer.
        """
        with self.__search_lock:
            return self.__search_in_progress or self.__search_timer is not None

    def __background_search(self) -> None:
        """
        Execute search in background thread and store results.
        """
        with self.__search_lock:
            self.__search_in_progress = True

        self.__session.searchform.set_search_attempted()
        results, total_results, index_status, index_processed_count, index_duration_value = self.__execute_search_query()
        self.__set_pending_results(results, total_results, index_status, index_processed_count, index_duration_value, False)

    def __build_search_query(self, base_query: str) -> str:
        """
        Build the final search query with filter applied (if present).        
        """
        if self.__session.searchform.filter == "html":
            if base_query.strip():
                return f"(type: html) AND {base_query}"
            else:
                return "type: html"
        else:
            return base_query

    def __execute_debounced_search(self) -> None:
        """
        Execute search after debounce delay in separate thread.
        """
        current_state_hash: str = self.__get_input_hash()
        if current_state_hash != self.__search_last_state_hash:
            return

        # show split view on results
        if self.__session.ui_focused == UiFocusable.SEARCH_RESULTS:
            self.__session.set_ui_state(UiState.SEARCH_RESULTS, UiFocusable.SEARCH_RESULTS)
        else:
            self.__session.set_ui_state(UiState.SEARCH_RESULTS, UiFocusable.SEARCH_FORM)

        self.__search_timer = None
        with self.__search_lock:
            self.__active_search_future = self.__executor.submit(self.__background_search)

    def __execute_search_immediate(self) -> None:
        """
        Execute search immediately on main thread (for ENTER key).
        """
        self.__session.searchform.set_search_attempted()

        self.__set_pending_results(None, 0, "", -1, -1, False)
        self.__session.results.clear()
        results, total_results, index_status, index_processed_count, index_duration_value = self.__execute_search_query()
        self.__set_pending_results(results, total_results, index_status, index_processed_count, index_duration_value, False)

    def __execute_search_query(self) -> tuple[list[ResourceResult], int, str, int, float]:
        """
        Centralized search execution logic shared by both sync and async paths.
        
        Returns:
            tuple: (results, total_results, index_status, index_processed_count, index_duration_value)
        """
        api: BaseJsonApi | None = self.__get_results(offset=self.__session.searchform.offset)

        if api is None:
            return [], 0, 0, 0

        results: list[ResourceResult] = api.get_results()
        total_results: int = api.total

        index_status: str = ""
        index_processed_count: int = -1
        index_duration_value: float = -1

        if api.meta_index is not None:
            if "status" in api.meta_index:
                index_status = api.meta_index["status"]
            if "processed" in api.meta_index:
                index_processed_count = api.meta_index["processed"]

            if "duration" in api.meta_index:
                index_duration_string: str = api.meta_index["duration"] or ""
                if index_duration_string:
                    try:
                        dt: datetime = datetime.strptime(index_duration_string, "%H:%M:%S.%f")
                        index_duration_value = dt.hour * 3600 + dt.minute * 60 + dt.second + dt.microsecond / 1000000
                    except ValueError:
                        index_duration_value = 0

        return results, total_results, index_status, index_processed_count, index_duration_value

    def __get_input_hash(self) -> str:
        """
        Generate a hash representing the complete current search state.
        """
        query: str = self.__session.searchform.query.strip()
        selected_sites = self.__session.searchform.get_selected_sites()
        selected_sites_ids: list[int] = [s.id for s in selected_sites]
        filter: str = str(self.__session.searchform.filter)
        sort: str = str(self.__session.searchform.sort)
        offset: int = self.__session.searchform.offset
        limit: int = self.__session.searchform.limit
        search_state: str = f"{query}|{selected_sites_ids}|{filter}|{offset}|{limit}|{sort}"
        return hashlib.md5(search_state.encode()).hexdigest()

    def __get_results(self, offset: int = 0) -> BaseJsonApi | None:
        """
        Execute search with given offset and return API response object.
        Centralizes the API call logic used by both sync and async search paths.
        
        Args:
            offset: Starting position for search results pagination
            
        Returns:
            BaseJsonApi: API response object containing search results and metadata
        """
        selected_site_ids: list[int] = self.__get_selected_site_ids()

        query: str = self.__build_search_query(self.__session.searchform.query)
        sort: str = self.__session.searchform.sort
        query_api: BaseJsonApi = self.__session.crawler.get_resources_api(
            sites=selected_site_ids if selected_site_ids else None,
            query=query,
            fields=["size", "status"],
            offset=offset,
            limit=SEARCH_RESULT_LIMIT,
            extras=["snippets"],
            sort=sort
        )

        return query_api

    def __get_selected_site_ids(self) -> list[int]:
        """
        Get list of selected site IDs using property access.
        """
        selected_sites = self.__session.searchform.get_selected_sites()
        return [site.id for site in selected_sites]

    def __set_pending_results(self, results, total_results, index_status, index_processed_count, index_duration_value, search_in_progress) -> None:
        try:
            with self.__search_lock:
                self.__pending_results = results
                self.__pending_total = total_results
                self.__pending_indexer_status = index_status
                self.__pending_indexer_processed = index_processed_count
                self.__pending_indexer_duration = index_duration_value
                self.__search_in_progress = search_in_progress

        except Exception as ex:
            with self.__search_lock:
                self.__session.results.clear()
                self.__search_in_progress = False
