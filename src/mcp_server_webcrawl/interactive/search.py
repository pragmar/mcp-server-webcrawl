import hashlib
import threading
from datetime import datetime
from typing import Optional, TYPE_CHECKING
from concurrent.futures import ThreadPoolExecutor, Future

from mcp_server_webcrawl.crawlers.base.crawler import BaseJsonApi
from mcp_server_webcrawl.interactive.ui import UiFocusable, UiState
from mcp_server_webcrawl.models.resources import ResourceResult

if TYPE_CHECKING:
    from mcp_server_webcrawl.interactive.session import InteractiveSession

SEARCH_RESULT_LIMIT: int = 10
SEARCH_DEBOUNCE_DELAY_SECONDS = 0.334


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
        self.__search_lock: threading.RLock = threading.RLock()  # prevents deadlock on recursive calls
        self.__search_in_progress: bool = False
        self.__active_search_future: Optional[Future] = None
        self.__pending_results: Optional[list[ResourceResult]] = None
        self.__pending_indexer_processed: int = 0
        self.__pending_indexer_duration: float = 0  # seconds
        self.__pending_total: int = 0

    def autosearch(self) -> None:
        """
        Automatically trigger search if any search parameters have changed with debouncing.
        """
        current_state_hash: str = self.__get_search_input_hash()
        if current_state_hash != self.__search_last_state_hash:
            self.__search_last_state_hash = current_state_hash
            self.cancel_pending_search()
            self.__search_timer = threading.Timer(SEARCH_DEBOUNCE_DELAY_SECONDS, self.__execute_debounced_search)
            self.__search_timer.start()

    def cancel_pending_search(self) -> None:
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

    def check_pending_results(self) -> None:
        """
        Check if there are pending search results and update the UI.
        """
        with self.__search_lock:
            if self.__pending_results is not None:
                # push pending results to the results view
                self.__session.results.update(self.__pending_results, self.__pending_total,
                        self.__pending_indexer_processed, self.__pending_indexer_duration)
                self.__pending_results = None
                self.__pending_total = 0
                self.__pending_indexer_processed = 0
                self.__pending_indexer_duration = 0

    def cleanup(self) -> None:
        """
        Clean up any pending operations.
        """
        self.cancel_pending_search()
        self.__executor.shutdown(wait=True)

    def execute_search(self) -> None:
        """
        Execute search immediately (synchronous for ENTER key).
        """
        self.cancel_pending_search()
        self.__search_last_state_hash = self.__get_search_input_hash()
        self.__session.searchform.set_search_attempted()

        with self.__search_lock:
            self.__pending_results = None
            self.__pending_total = 0
            self.__pending_indexer_processed = 0
            self.__pending_indexer_duration = 0

        self.__session.results.clear()
        if self.__session.searchform.offset > 0:
            self.__session.set_ui_state(UiState.SEARCH_RESULTS, UiFocusable.SEARCH_RESULTS)
        else:
            self.__session.set_ui_state(UiState.SEARCH_RESULTS, UiFocusable.SEARCH_FORM)

        try:
            api: BaseJsonApi = self.__get_search_results(offset=0)
            results: list[ResourceResult] = api.get_results()
            total_results: int = api.total
            index_processed_count: int = api.meta_index["processed"] if "processed" in api.meta_index else 0
            index_processed_duration: float = api.meta_index["duration"] if "duration" in api.meta_index else 0
            self.__session.results.update(results, total_results, index_processed_count, index_processed_duration)
        except Exception:
            self.__session.results.clear()
            self.__session.set_ui_state(UiState.SEARCH_INIT, UiFocusable.SEARCH_FORM)

    def has_pending_search(self) -> bool:
        """Check if there's a pending debounced search."""
        return self.__search_timer is not None

    def reset_search_tracking(self) -> None:
        """
        Reset search tracking state.
        """
        self.cancel_pending_search()
        self.__search_last_state_hash = ""
        self.__pending_results = None
        self.__pending_total = 0
        self.__pending_indexer_processed = 0
        self.__pending_indexer_duration = 0

    def search_in_progress(self) -> bool:
        """
        Check if a search is currently in progress.
        """
        with self.__search_lock:
            return self.__search_in_progress

    def __background_search(self) -> None:
        """
        Execute search in background thread and store results.
        """
        with self.__search_lock:
            self.__search_in_progress = True

        self.__session.searchform.set_search_attempted()
        try:
            api: BaseJsonApi = self.__get_search_results(offset=self.__session.searchform.offset)
            results: list[ResourceResult] = api.get_results()
            total_results: int = api.total
            index_processed_exists: bool = api.meta_index is not None and "processed" in api.meta_index
            index_processed_count: int = api.meta_index["processed"] if index_processed_exists in api.meta_index else 0
            index_duration_exists: bool = api.meta_index is not None and "duration" in api.meta_index
            index_duration_string: str = api.meta_index["duration"] if index_duration_exists else ""

            index_duration_value: float
            if index_duration_string in ("", None):
                index_duration_value = 0
            else:
                dt: datetime = datetime.strptime(index_duration_string, "%H:%M:%S.%f")
                seconds: float = dt.hour * 3600 + dt.minute * 60 + dt.second + dt.microsecond / 1000000
                index_duration_value = seconds

            # search_duration: float = float(api.to_dict()['__meta__']['request']['time'])
            self.__session.results.update(results, total_results, index_processed_count, index_duration_value)

            with self.__search_lock:
                self.__pending_results = results
                self.__pending_total = total_results
                self.__pending_indexer_processed = index_processed_count
                self.__pending_indexer_duration = index_duration_value
                self.__search_in_progress = False

        except Exception as ex:
            with self.__search_lock:
                self.__search_in_progress = False

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

        current_state_hash: str = self.__get_search_input_hash()
        if current_state_hash != self.__search_last_state_hash:
            return # stale

        if self.__session.searchform.offset > 0:
            self.__session.set_ui_state(UiState.SEARCH_RESULTS, UiFocusable.SEARCH_RESULTS)
        else:
            self.__session.set_ui_state(UiState.SEARCH_RESULTS, UiFocusable.SEARCH_FORM)

        self.__search_timer = None
        with self.__search_lock:
            self.__active_search_future = self.__executor.submit(self.__background_search)

    def __get_search_input_hash(self) -> str:
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

    def __get_search_results(self, offset: int = 0) -> BaseJsonApi:
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

    def __get_search_results_and_total(self, offset: int = 0) -> tuple[list[ResourceResult], int]:
        """
        Execute search with given offset and return results and total count.
        Centralizes the API call logic used by both sync and async search paths.
        """
        selected_site_ids: list[int] = self.__get_selected_site_ids()
        query: str = self.__build_search_query(self.__session.searchform.query)
        query_api: BaseJsonApi = self.__session.crawler.get_resources_api(
            sites=selected_site_ids if selected_site_ids else None,
            query=query,
            fields=["size", "status"],
            offset=offset,
            limit=SEARCH_RESULT_LIMIT,
            extras=["snippets"]
        )

        results: list[ResourceResult] = query_api.get_results()
        total_results: int = query_api.total
        return (results, total_results)

    def __get_selected_site_ids(self) -> list[int]:
        """
        Get list of selected site IDs using property access.
        """
        selected_sites = self.__session.searchform.get_selected_sites()
        return [site.id for site in selected_sites]
