import hashlib
import threading

from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from mcp_server_webcrawl.crawlers.base.crawler import BaseCrawler, BaseJsonApi
from mcp_server_webcrawl.models.resources import ResourceResult

SEARCH_DEBOUNCE_DELAY_SECONDS = 0.2
SEARCH_RESULT_LIMIT: int = 10

@dataclass(frozen=True)
class SearchRequest:
    """
    An immutable snapshot of everything needed to run one search.

    The search form builds this; the manager consumes it. Because it is frozen and
    self-contained, the manager never has to reach back into form/session state, and
    two requests can be compared for equality to debounce no-op re-searches.
    """
    query: str
    site_ids: tuple[int, ...]
    filter: str
    sort: str
    offset: int
    limit: int

    def cache_key(self) -> str:
        """
        Stable hash of the request, used to skip redundant searches.
        """
        raw = f"{self.query}|{list(self.site_ids)}|{self.filter}|{self.offset}|{self.limit}|{self.sort}"
        return hashlib.md5(raw.encode()).hexdigest()

    def to_query(self) -> str:
        """
        Apply the HTML filter to the user's query, producing the engine query string.
        """
        if self.filter == "html":
            return f"(type: html) AND {self.query}" if self.query.strip() else "type: html"
        return self.query

@dataclass
class SearchResults:
    """
    The outcome of a search: the page of results plus indexer metadata. Carries the
    offset it was fetched at so the results view can render absolute positions
    without reaching back into the form.
    """
    results: list[ResourceResult] = field(default_factory=list)
    total: int = 0
    offset: int = 0
    index_status: str = ""
    index_processed: int = -1
    index_duration: float = -1.0

    @classmethod
    def empty(cls) -> "SearchResults":
        return cls()

class SearchManager:
    """
    Runs searches against a single crawler, with debouncing and a background worker.

    Collaborators are narrow and explicit: a crawler to query and an on_results
    callback to deliver finished pages. It knows nothing about the session, the form,
    or UI state. Results are buffered and handed back on the main thread via
    check_pending so curses stays single-threaded.
    """

    def __init__(self, crawler: BaseCrawler, on_results: Callable[[SearchResults], None]):
        self.__crawler: BaseCrawler = crawler
        self.__on_results: Callable[[SearchResults], None] = on_results
        self.__last_key: str = ""
        self.__timer: Optional[threading.Timer] = None
        self.__executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="SearchManager")
        self.__lock: threading.RLock = threading.RLock()
        self.__in_progress: bool = False
        self.__future: Optional[Future] = None
        self.__pending: Optional[SearchResults] = None

    def search(self, request: SearchRequest, immediate: bool = False) -> None:
        """
        Run a search. Immediate searches (ENTER) run synchronously; otherwise the
        search is debounced and run on a worker thread. Redundant debounced searches
        (same request as last time) are skipped.
        """
        key = request.cache_key()
        if not immediate and key == self.__last_key:
            return

        self.__last_key = key
        self.cancel_pending()

        if immediate:
            self.__run(request)
        else:
            self.__timer = threading.Timer(SEARCH_DEBOUNCE_DELAY_SECONDS, self.__run_debounced, args=(request, key))
            self.__timer.start()

    def cancel_pending(self) -> None:
        """
        Cancel any pending debounce timer and in-flight future.
        """
        if self.__timer is not None:
            self.__timer.cancel()
            self.__timer = None
        with self.__lock:
            if self.__future is not None:
                self.__future.cancel()
                self.__future = None

    def check_pending(self) -> None:
        """
        Deliver any finished results to on_results. Call from the main loop.
        """
        with self.__lock:
            pending = self.__pending
            self.__pending = None
        if pending is not None:
            self.__on_results(pending)

    def cleanup(self) -> None:
        """
        Cancel work and shut down the worker pool.
        """
        self.cancel_pending()
        self.__executor.shutdown(wait=True)

    def is_searching(self) -> bool:
        """
        True while a search is debouncing or running.
        """
        with self.__lock:
            return self.__in_progress or self.__timer is not None

    def __run_debounced(self, request: SearchRequest, key: str) -> None:
        if key != self.__last_key:
            return
        self.__timer = None
        with self.__lock:
            self.__future = self.__executor.submit(self.__run, request)

    def __run(self, request: SearchRequest) -> None:
        with self.__lock:
            self.__in_progress = True
        results = self.__execute(request)
        with self.__lock:
            self.__pending = results
            self.__in_progress = False
            self.__future = None

    def __execute(self, request: SearchRequest) -> SearchResults:
        """
        Perform the API call and normalize the response into SearchResults.
        """
        try:
            api: Optional[BaseJsonApi] = self.__crawler.get_resources_api(
                sites=list(request.site_ids) if request.site_ids else None,
                query=request.to_query(),
                fields=["size", "status"],
                offset=request.offset,
                limit=SEARCH_RESULT_LIMIT,
                extras=["snippets"],
                sort=request.sort,
            )
        except Exception:
            return SearchResults.empty()

        if api is None:
            return SearchResults.empty()

        return SearchResults(
            results=api.get_results(),
            total=api.total,
            offset=request.offset,
            index_status=self.__index_status(api),
            index_processed=self.__index_processed(api),
            index_duration=self.__index_duration(api),
        )

    @staticmethod
    def __index_status(api: BaseJsonApi) -> str:
        if api.meta_index is not None and "status" in api.meta_index:
            return api.meta_index["status"]
        return ""

    @staticmethod
    def __index_processed(api: BaseJsonApi) -> int:
        if api.meta_index is not None and "processed" in api.meta_index:
            return api.meta_index["processed"]
        return -1

    @staticmethod
    def __index_duration(api: BaseJsonApi) -> float:
        if api.meta_index is None or "duration" not in api.meta_index:
            return -1.0
        raw = api.meta_index["duration"] or ""
        if not raw:
            return -1.0
        try:
            dt = datetime.strptime(raw, "%H:%M:%S.%f")
            return dt.hour * 3600 + dt.minute * 60 + dt.second + dt.microsecond / 1000000
        except ValueError:
            return 0.0
