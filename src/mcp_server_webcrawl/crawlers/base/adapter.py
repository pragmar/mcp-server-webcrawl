import os
import hashlib
import mimetypes
import re
import sqlite3

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from dataclasses import dataclass
from datetime import timezone
from typing import Final

from mcp_server_webcrawl.models.resources import ResourceResultType
from mcp_server_webcrawl.utils import isoformat_zulu
from mcp_server_webcrawl.utils.logger import get_logger

logger = get_logger()

# in the interest of sane imports (avoiding circulars), indexed constants live here,
# happily, as denizens of adapterville
INDEXED_BINARY_EXTENSIONS: Final[tuple[str, ...]] = (
    ".woff",".woff2",".ttf",".otf",".eot",
    ".jpeg",".jpg",".png",".webp",".gif",".bmp",".tiff",".tif",".svg",".ico",".heic",".heif",
    ".mp3",".wav",".ogg",".flac",".aac",".m4a",".wma",
    ".mp4",".webm",".avi",".mov",".wmv",".mkv",".flv",".m4v",".mpg",".mpeg",
    ".pdf",".doc",".docx",".xls",".xlsx",".ppt",".pptx",
    ".zip",".rar",".7z",".tar",".gz",".bz2",".xz",
    ".exe",".dll",".so",".dylib",".bin",".apk",".app",
    ".swf",".svgz",".dat",".db",".sqlite",".class",".pyc",".o"
)


# files on disk will need default for reassembly {proto}{dir}
# these things are already approximations (perhaps) having passed through wget filtering (--adjust-extension)
# representative of the file on disk, also https is what the LLM is going to guess in all cases
INDEXED_RESOURCE_DEFAULT_PROTOCOL: Final[str] = "https://"
INDEXED_BATCH_SIZE: Final[int] = 256
INDEXED_MAX_WORKERS: Final[int] = min(8, os.cpu_count() or 4)
INDEXED_MAX_FILE_SIZE: Final[int] = 2000000  # 2MB

# max indexing time may need a cli arg to override at some point,
# but for now, this is a fan spinner--just make sure it doesn't run away
INDEXED_MAX_PROCESS_TIME: Final[timedelta] = timedelta(minutes=10)

# maximum indexes held in cache, an index is a unique list[site-ids] argument
INDEXED_MANAGER_CACHE_MAX: Final[int] = 20

INDEXED_SORT_MAPPING: Final[dict[str, tuple[str, str]]] = {
    "+id": ("Id", "ASC"),
    "-id": ("Id", "DESC"),
    "+url": ("Url", "ASC"),
    "-url": ("Url", "DESC"),
    "+status": ("Status", "ASC"),
    "-status": ("Status", "DESC"),
    "?": ("Id", "RANDOM")
}

INDEXED_TYPE_MAPPING: Final[dict[str, ResourceResultType]] = {
    "": ResourceResultType.PAGE,
    ".html": ResourceResultType.PAGE,
    ".htm": ResourceResultType.PAGE,
    ".php": ResourceResultType.PAGE,
    ".asp": ResourceResultType.PAGE,
    ".aspx": ResourceResultType.PAGE,
    ".js": ResourceResultType.SCRIPT,
    ".css": ResourceResultType.CSS,
    ".jpg": ResourceResultType.IMAGE,
    ".jpeg": ResourceResultType.IMAGE,
    ".png": ResourceResultType.IMAGE,
    ".gif": ResourceResultType.IMAGE,
    ".svg": ResourceResultType.IMAGE,
    ".tif": ResourceResultType.IMAGE,
    ".tiff": ResourceResultType.IMAGE,
    ".webp": ResourceResultType.IMAGE,
    ".pdf": ResourceResultType.PDF,
    ".txt": ResourceResultType.TEXT,
    ".xml": ResourceResultType.TEXT,
    ".json": ResourceResultType.TEXT,
    ".doc": ResourceResultType.DOC,
    ".docx": ResourceResultType.DOC,
    ".mov": ResourceResultType.VIDEO,
    ".mp4": ResourceResultType.VIDEO,
    ".mp3": ResourceResultType.AUDIO,
    ".ogg": ResourceResultType.AUDIO,
}

class IndexStatus(Enum):
    UNDEFINED = ""
    IDLE = "idle"
    INDEXING = "indexing"
    PARTIAL = "partial" # incomplete, but stable and searchable (timeout)
    COMPLETE = "complete"
    REMOTE = "remote"
    FAILED = "failed"


@dataclass
class IndexState:
    """Shared state between crawler and manager for indexing progress"""
    status: IndexStatus = IndexStatus.UNDEFINED
    processed: int = 0
    time_start: datetime | None = None
    time_end: datetime | None = None

    def set_status(self, status: IndexStatus):
        if self.status == IndexStatus.UNDEFINED:
            self.time_start = datetime.now(timezone.utc)
            self.processed = 0
            self.time_end = None
        elif status in (IndexStatus.COMPLETE, IndexStatus.PARTIAL):
            if self.time_end is None:
                self.time_end = datetime.now(timezone.utc)
            if status == IndexStatus.PARTIAL:
                logger.info(f"Indexing timeout ({INDEXED_MAX_PROCESS_TIME} minutes) reached. \
                            Index status has been set to PARTIAL, and further indexing halted.")
        self.status = status

    def increment_processed(self):
        self.processed += 1

    @property
    def duration(self) -> str:
        if not self.time_start:
            return "00:00:00.000"
        end = self.time_end or datetime.now(timezone.utc)
        total_seconds = (end - self.time_start).total_seconds()

        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)
        milliseconds = int((total_seconds % 1) * 1000)

        # Format as HH:MM:SS.mmm
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"

    def is_timeout(self) -> bool:
        """Check if the indexing operation has exceeded the timeout threshold"""
        if not self.time_start:
            return False
        return (datetime.now(timezone.utc) - self.time_start) > INDEXED_MAX_PROCESS_TIME

    def to_dict(self) -> dict:
        """Convert the IndexState to a dictionary representation"""
        status = self.status.value if hasattr(self.status, 'value') else self.status
        result = { "status": status }
        if self.status not in (IndexStatus.REMOTE, IndexStatus.UNDEFINED):
            result["processed"] = self.processed
            result["time_start"] = isoformat_zulu(self.time_start) if self.time_start else None
            result["time_end"] = isoformat_zulu(self.time_end) if self.time_end else None
            result["duration"] = self.duration
        return result




class SitesGroup:
    def __init__(self, site_ids: list[int], site_paths: list[Path]) -> None:
        """
        Simple container class supports many sites being searched at once.

        Args:
            site_ids: site ids of the sites
            site_paths: paths to site contents (directories)

        """
        self.ids: list[int] = site_ids
        self.paths: list[Path] = site_paths
        self.cache_key = frozenset(map(str, site_ids))

    def __str__(self) -> str:
        return f"[SitesGroup {self.cache_key}]"

    def get_sites(self) -> dict[int, str]:
        # unwrap { id1: path1, id2: path2 }
        return {site_id: str(path) for site_id, path in zip(self.ids, self.paths)}

class SitesStat:
    def __init__(self, group: SitesGroup, cached: bool) -> None:
        """
        Some basic bookeeping, for troubleshooting
        """
        self.group: Final[SitesGroup] = group
        self.timestamp: Final[datetime] = datetime.now()
        self.cached: Final[bool] = cached

class BaseManager:
    """
    Base class for managing web crawler data in in-memory SQLite databases.
    Provides connection pooling and caching for efficient access.
    """

    def __init__(self) -> None:
        """Initialize the manager with empty cache and statistics."""
        self._db_cache: dict[frozenset, tuple[sqlite3.Connection, IndexState]] = {}
        self._stats: list[SitesStat] = []
        # dictionary to track which database builds are in progress
        self._build_locks: dict[frozenset, tuple[datetime, str]] = {}

    @contextmanager
    def _building_lock(self, group: SitesGroup):
        """Context manager for database building operations.
           Sets a lock during database building and releases it when done."""
        try:
            self._build_locks[group.cache_key] = (datetime.now(), "building")
            yield
        except Exception as e:
            self._build_locks[group.cache_key] = (self._build_locks[group.cache_key][0], f"failed: {str(e)}")
            raise # re-raise
        finally:
            # clean up the lock
            self._build_locks.pop(group.cache_key, None)

    @staticmethod
    def string_to_id(value: str) -> int:
        """
        Convert a string, such as a directory name, to a numeric ID
        suitable for a database primary key.

        Hash space and collision probability notes:
        - [:8]  = 32 bits (4.29 billion values) - ~1% collision chance with 10,000 items
        - [:12] = 48 bits (280 trillion values) - ~0.0000001% collision chance with 10,000 items
        - [:16] = 64 bits (max safe SQLite INTEGER) - near-zero collision, 9.22 quintillion values
        - SQLite INTEGER type is 64-bit signed, with max value of 9,223,372,036,854,775,807.
        - The big problem with larger hashspaces is the length of the ids they generate for presentation.

        Args:
            dirname: Input string to convert to an ID

        Returns:
            Integer ID derived from the input string
        """
        hash_obj = hashlib.sha1(value.encode())
        return int(hash_obj.hexdigest()[:12], 16)

    @staticmethod
    def get_basic_headers(file_size: int, resource_type: ResourceResultType) -> str:
        content_type = {
            ResourceResultType.PAGE: "text/html",
            ResourceResultType.CSS: "text/css",
            ResourceResultType.SCRIPT: "application/javascript",
            ResourceResultType.IMAGE: "image/jpeg",  # default image type
            ResourceResultType.PDF: "application/pdf",
            ResourceResultType.TEXT: "text/plain",
            ResourceResultType.DOC: "application/msword",
            ResourceResultType.OTHER: "application/octet-stream"
        }.get(resource_type, "application/octet-stream")
        return f"HTTP/1.0 200 OK\r\nContent-Type: {content_type}\r\nContent-Length: {file_size}\r\n\r\n"

    @staticmethod
    def read_files(paths: list[Path]) -> dict[Path, str | None]:
        file_contents: dict[Path, str | None] = {}
        with ThreadPoolExecutor(max_workers=INDEXED_MAX_WORKERS) as executor:
            for file_path, content in executor.map(BaseManager.__read_files_contents, paths):
                if content is not None:
                    file_contents[file_path] = content
        return file_contents

    @staticmethod
    def __read_files_contents(file_path) -> tuple[Path, str | None]:
        """Read content from text files with better error handling and encoding detection."""
        #if resource_type not in [ResourceResultType.PAGE, ResourceResultType.TEXT,
        #            ResourceResultType.CSS, ResourceResultType.SCRIPT, ResourceResultType.OTHER]:
        #    return None

        null_result: tuple[Path, str] = file_path, None

        extension = os.path.splitext(file_path)[1].lower()
        if (extension in INDEXED_BINARY_EXTENSIONS or
            os.path.getsize(file_path) > INDEXED_MAX_FILE_SIZE):
            return null_result

        mime_type, _ = mimetypes.guess_type(file_path)
        mime_text_exceptions = ["application/json", "application/xml", "application/javascript"]
        if mime_type and not mime_type.startswith("text/") and mime_type not in mime_text_exceptions:
            return null_result

        content = None
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            logger.debug(f"Could not decode file as UTF-8: {file_path}")
            return null_result
        except Exception as e:
            logger.error(f"Error reading file {file_path}")
            return null_result

        return file_path, content

    @staticmethod
    def read_file_contents(file_path, resource_type) -> str | None:
        """Read content from text files with better error handling and encoding detection."""
        if resource_type not in [ResourceResultType.PAGE, ResourceResultType.TEXT,
                    ResourceResultType.CSS, ResourceResultType.SCRIPT, ResourceResultType.OTHER]:
            return None

        if os.path.getsize(file_path) > INDEXED_MAX_FILE_SIZE:
            return None

        extension = os.path.splitext(file_path)[1].lower()
        if extension in INDEXED_BINARY_EXTENSIONS:
            return None

        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type and not mime_type.startswith("text/"):
            if not any(mime_type.startswith(prefix) for prefix in ["application/json",
                    "application/xml", "application/javascript"]):
                return None

        content = None
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            logger.warning(f"Could not decode file as UTF-8: {file_path}")

        return content

    @staticmethod
    def decruft_path(path:str) -> list[str]:
        """
        Very light touch cleanup of wget file naming, these tmps are creating noise
        """
        decruftified = str(path)
        decruftified = decruftified.lower()
        decruftified = re.sub(r"[\u00b7·]?\d+\.tmp|\d{12}|\.tmp", "", decruftified)
        return decruftified

    def get_connection(self, group: SitesGroup) -> tuple[sqlite3.Connection | None, IndexState]:
        """
        Get database connection for sites in the group, creating if needed.

        Args:
            group: Group of sites to connect to

        Returns:
            Tuple of (SQLite connection to in-memory database with data loaded or None if building,
                     IndexState associated with this database)
        """
        if group.cache_key in self._build_locks:
            build_time, status = self._build_locks[group.cache_key]
            get_logger().info(f"Database for {group} is currently {status} (started at {build_time})")
            return None, IndexState()  # Return empty IndexState for building databases

        if len(self._db_cache) >= INDEXED_MANAGER_CACHE_MAX:
            self._db_cache.clear()

        is_cached: bool = group.cache_key in self._db_cache
        self._stats.append(SitesStat(group, is_cached))

        if not is_cached:
            # Create fresh IndexState for this new database
            index_state = IndexState()
            index_state.set_status(IndexStatus.INDEXING)

            # use the context manager to handle the building lock
            with self._building_lock(group):
                connection: sqlite3.Connection = sqlite3.connect(":memory:", check_same_thread=False)
                self._setup_database(connection)

                for site_id, site_path in group.get_sites().items():
                    self._load_site_data(connection, Path(site_path), site_id, index_state=index_state)
                    if index_state.is_timeout():
                        index_state.set_status(IndexStatus.PARTIAL)
                        break

                if index_state is not None and index_state.status == IndexStatus.INDEXING:
                    index_state.set_status(IndexStatus.COMPLETE)

                # Cache both connection and its IndexState
                self._db_cache[group.cache_key] = (connection, index_state)

        # Return cached or newly created connection with its IndexState
        connection, index_state = self._db_cache[group.cache_key]
        return connection, index_state

    def get_stats(self) -> list[SitesStat]:
        return self._stats.copy()

    def _setup_database(self, connection: sqlite3.Connection) -> None:
        """
        Create the database schema for storing resource data.

        Args:
            connection: SQLite connection to set up
        """
        with closing(connection.cursor()) as cursor:
            connection.execute("PRAGMA encoding = \"UTF-8\"")
            connection.execute("PRAGMA synchronous = OFF")
            connection.execute("PRAGMA journal_mode = MEMORY")
            cursor.execute("""
                CREATE VIRTUAL TABLE ResourcesFullText USING fts5(
                    Id,
                    Project,
                    Url,
                    Type,
                    Status,
                    Name,
                    Size,
                    Time,
                    Headers,
                    Content,
                    tokenize='unicode61 remove_diacritics 0'
                )
            """)

    def _load_site_data(self, connection: sqlite3.Connection, site_path: Path,
            site_id: int, index_state: IndexState = None) -> None:
        """
        Load site data into the database. To be implemented by subclasses.

        Args:
            connection: SQLite connection
            site_path: Path to the site data
            site_id: ID for the site
        """
        raise NotImplementedError("Subclasses must implement _load_site_data")

    def _determine_resource_type(self, content_type: str) -> ResourceResultType:

        content_type_mapping = {
            "html": ResourceResultType.PAGE,
            "javascript": ResourceResultType.SCRIPT,
            "css": ResourceResultType.CSS,
            "image/": ResourceResultType.IMAGE,
            "pdf": ResourceResultType.PDF,
            "text/": ResourceResultType.TEXT,
            "audio/": ResourceResultType.AUDIO,
            "video/": ResourceResultType.VIDEO,
            "application/json": ResourceResultType.TEXT,
            "application/xml": ResourceResultType.TEXT
        }

        content_type = content_type.lower()
        for pattern, res_type in content_type_mapping.items():
            if pattern in content_type:
                return res_type

        return ResourceResultType.OTHER

    def _is_text_content(self, content_type: str) -> bool:
        """
        Check if content type represents text.

        Args:
            content_type: HTTP Content-Type header value

        Returns:
            True if the content is textual, False otherwise
        """
        return any(t in content_type.lower() for t in [
            "text/", "javascript", "json", "xml", "html", "css"
        ])
