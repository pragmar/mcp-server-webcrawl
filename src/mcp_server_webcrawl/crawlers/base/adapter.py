import os
import hashlib
import sqlite3
import re
import mimetypes

from typing import Optional
from datetime import datetime
from pathlib import Path
from typing import Any, Final, Tuple
from contextlib import closing, contextmanager

from mcp_server_webcrawl.models.resources import ResourceResultType
from mcp_server_webcrawl.utils.logger import get_logger
from mcp_server_webcrawl.crawlers.base.indexed import (
    INDEXED_MANAGER_CACHE_MAX,
    INDEXED_BINARY_EXTENSIONS,
)

logger = get_logger()


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
        self._db_cache: dict[frozenset, sqlite3.Connection] = {}
        self._stats: list[SitesStat] = []
        # dictionary to track which database builds are in progress
        self._building_locks: dict[frozenset, tuple[datetime, str]] = {}

    @contextmanager
    def _building_lock(self, group: SitesGroup):
        """Context manager for database building operations.
           Sets a lock during database building and releases it when done."""
        try:
            self._building_locks[group.cache_key] = (datetime.now(), "building")
            yield
        except Exception as e:
            self._building_locks[group.cache_key] = (self._building_locks[group.cache_key][0], f"failed: {str(e)}")
            # re-raise the exception
            raise
        finally:
            # clean up the lock
            self._building_locks.pop(group.cache_key, None)

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
    def read_file_contents(file_path, resource_type) -> Optional[str]:
        """Read content from text files with better error handling and encoding detection."""
        # Skip if not a text resource type
        if resource_type not in [ResourceResultType.PAGE, ResourceResultType.TEXT,
                    ResourceResultType.CSS, ResourceResultType.SCRIPT, ResourceResultType.OTHER]:
            return None

        # Check file size first to avoid unnecessary processing
        if os.path.getsize(file_path) > 2_000_000:  # 2MB limit
            return None

        # Check extension
        extension = os.path.splitext(file_path)[1].lower()
        if extension in INDEXED_BINARY_EXTENSIONS:
            return None

        # Check MIME type
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type and not mime_type.startswith("text/"):
            # Additional check: some non-text MIME types can still be text
            if not any(mime_type.startswith(prefix) for prefix in ["application/json", "application/xml", "application/javascript"]):
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

    def get_connection(self, group: SitesGroup) -> Optional[sqlite3.Connection]:
        """
        Get database connection for sites in the group, creating if needed.

        Args:
            sites_group: Group of sites to connect to

        Returns:
            SQLite connection to in-memory database with data loaded
            or None if the database is currently being built
        """
        if group.cache_key in self._building_locks:
            build_time, status = self._building_locks[group.cache_key]
            get_logger().info(f"Database for {group} is currently {status} (started at {build_time})")
            return None

        if len(self._db_cache) >= INDEXED_MANAGER_CACHE_MAX:
            self._db_cache.clear()

        is_cached: bool = group.cache_key in self._db_cache
        self._stats.append(SitesStat(group, is_cached))

        if not is_cached:
            # use the context manager to handle the building lock
            with self._building_lock(group):
                connection: sqlite3.Connection = sqlite3.connect(":memory:", check_same_thread=False)
                connection.execute("PRAGMA encoding = \"UTF-8\"")
                self._setup_schema(connection)

                for site_id, site_path in group.get_sites().items():
                    self._load_site_data(connection, Path(site_path), site_id)
                self._db_cache[group.cache_key] = connection

        return self._db_cache[group.cache_key]

    def get_stats(self) -> list[SitesStat]:
        return self._stats.copy()

    def _setup_schema(self, connection: sqlite3.Connection) -> None:
        """
        Create the database schema for storing resource data.

        Args:
            connection: SQLite connection to set up
        """
        with closing(connection.cursor()) as cursor:
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

    def _load_site_data(self, connection: sqlite3.Connection, site_path: Path, site_id: int) -> None:
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
