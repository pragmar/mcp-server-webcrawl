import os
import hashlib
import mimetypes
import re
import sqlite3
import traceback

from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from dataclasses import dataclass
from datetime import timezone
from typing import Final

from mcp_server_webcrawl.models.resources import (
    ResourceResult,
    ResourceResultType,
    RESOURCES_DEFAULT_FIELD_MAPPING,
    RESOURCES_DEFAULT_SORT_MAPPING,
    RESOURCES_FIELDS_REQUIRED,
    RESOURCES_ENUMERATED_TYPE_MAPPING,
    RESOURCES_LIMIT_MAX,
)

from mcp_server_webcrawl.utils import to_isoformat_zulu, from_isoformat_zulu
from mcp_server_webcrawl.utils.search import SearchQueryParser, SearchSubquery
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
INDEXED_IGNORE_DIRECTORIES: Final[list[str]] = ["http-client-cache", "result-storage"]

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
    ".bmp": ResourceResultType.IMAGE,
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

        # HH:MM:SS.mmm
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
            result["time_start"] = to_isoformat_zulu(self.time_start) if self.time_start else None
            result["time_end"] = to_isoformat_zulu(self.time_end) if self.time_end else None
            result["duration"] = self.duration
        return result


class SitesGroup:
    def __init__(self, datasrc: Path, site_ids: list[int], site_paths: list[Path]) -> None:
        """
        Container class supports the searching of one or more sites at once.

        Args:
            datasrc: site datasrc
            site_ids: site ids of the sites
            site_paths: paths to site contents (directories)

        """

        self.datasrc: Path = datasrc
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
        """Initialize the manager with statistics."""
        self._stats: list[SitesStat] = []

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
            value: Input string to convert to an ID

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
        """
        Read content from text files with better error handling and encoding detection.
        """

        # a null result just means we're not dealing with the content
        # which has been determined to be binary or of unknown format
        # we can still maintain a record the URL/headers/whatever as Resource
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
            # errors="ignore" or "replace" required to read Katana txt files with
            # data payloads and still capture url, headers, etc. replace supposedly
            # softer touch generally, but not any better for Katana specifically
            # as payload will not be stored
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
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
    def decruft_path(path:str) -> str:
        """
        Very light touch cleanup of file naming, these tmps are creating noise
        and extensions are useful in classifying resources
        """
        # clean path/file from wget modifications we don't want
        decruftified = str(path)
        decruftified = decruftified.lower()
        decruftified = re.sub(r"[\u00b7·]?\d+\.tmp|\d{12}|\.tmp", "", decruftified)

        # clean extension from non alpha
        # S1/wget can generate some weird extensions with URL args
        # filenames such as main.min.js202505251919
        decruftified = re.sub(r'\.(\w+)[^\w]*$', r'.\1', decruftified)
        return decruftified

    def get_stats(self) -> list[SitesStat]:
        return self._stats.copy()


    def get_resources_for_sites_group(
        self,
        sites_group: SitesGroup,
        query: str,
        fields: list[str] | None,
        sort: str | None,
        limit: int,
        offset: int,
        swap_values: dict = {}
    ) -> tuple[list[ResourceResult], int, IndexState]:
        """
        Get resources from directories using structured query parsing with SearchQueryParser.

        This method extracts types, fields, and statuses from the querystring instead of
        accepting them as separate arguments, using the new SearchSubquery functionality.

        Args:
            sites_group: Group of sites to search in
            query: Search query string that can include field:value syntax for filtering
            fields: resource fields to be returned by the API (Content, Headers, etc.)
            sort: Sort order for results
            limit: Maximum number of results to return
            offset: Number of results to skip for pagination
            swap_values: per-field parameterized values to check for (and replace)

        Returns:
            Tuple of (list of ResourceResult objects, total count, connection_index_state)

        Notes:
            Returns empty results if sites is empty or not provided.
            If the database is being built, it will log a message and return empty results.

            This method extracts field-specific filters from the query string using SearchQueryParser:
            - type:html (to filter by resource type)
            - status:200 (to filter by HTTP status)
            Any fields present in the SearchSubquery will be included in the response.
        """

        # get_connection must be defined in subclass
        assert hasattr(self, "get_connection"), "get_connection not found"

        null_result: tuple[list[ResourceResult], int, IndexState | None] = [], 0, None

        # get sites arg from group
        sites: list[int] = sites_group.ids

        if not sites or not sites_group or len(sites) == 0:
            return null_result

        connection: sqlite3.Connection
        connection_index_state: IndexState
        connection, connection_index_state = self.get_connection(sites_group)

        if connection is None:
            # database is currently being built
            logger.info(f"Database for sites {sites} is currently being built, try again later")
            return null_result

        parser = SearchQueryParser()
        parsed_query = []

        if query.strip():
            try:
                parsed_query = parser.parse(query.strip())
            except Exception as e:
                logger.error(f"Error parsing query: {e}")
                # fall back to simple text search
                parsed_query = []

        # if status not explicitly in query, add status >=100
        status_applied = False
        for squery in parsed_query:
            if squery.field == "status":
                status_applied = True
                break
        if not status_applied:
            http_status_received = SearchSubquery("status", 100, "term", [], "AND", comparator=">=")
            parsed_query.append(http_status_received)

        # determine fields to be retrieved
        selected_fields: set[str] = set(RESOURCES_FIELDS_REQUIRED)
        if fields:
            selected_fields.update(f for f in fields if f in RESOURCES_DEFAULT_FIELD_MAPPING)

        safe_sql_fields = [RESOURCES_DEFAULT_FIELD_MAPPING[f] for f in selected_fields]
        assert all(re.match(r'^[A-Za-z\.]+$', field) for field in safe_sql_fields), "Unknown or unsafe field requested"
        safe_sql_fields_joined: str = ", ".join(safe_sql_fields)
        from_clause = "ResourcesFullText LEFT JOIN Resources ON ResourcesFullText.Id = Resources.Id"
        where_clauses: list[str] = []
        params: dict[str, int | str] = {}

        if sites:
            placeholders: list[str] = [f":sites{i}" for i in range(len(sites))]
            where_clauses.append(f"ResourcesFullText.Project IN ({','.join(placeholders)})")
            params.update({f"sites{i}": id_val for i, id_val in enumerate(sites)})

        if parsed_query:
            fts_parts, fts_params = parser.to_sqlite_fts(parsed_query, swap_values)
            if fts_parts:
                fts_where = ""
                for part in fts_parts:
                    if part in ["AND", "OR", "NOT"]:    # operator
                        fts_where += f" {part} "
                    else:                               # condition
                        fts_where += part
                # fts subquery as a single condition in parentheses
                if fts_where:
                    where_clauses.append(f"({fts_where})")
                    for param_name, param_value in fts_params.items():
                        params[param_name] = param_value

        where_clause: str = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        if sort in RESOURCES_DEFAULT_SORT_MAPPING:
            field, direction = RESOURCES_DEFAULT_SORT_MAPPING[sort]
            if direction == "RANDOM":
                order_clause: str = " ORDER BY RANDOM()"
            else:
                order_clause = f" ORDER BY {field} {direction}"
        else:
            order_clause = " ORDER BY Resources.Id ASC"

        limit = min(max(1, limit), RESOURCES_LIMIT_MAX)
        limit_clause: str = f" LIMIT {limit} OFFSET {offset}"
        statement: str = f"SELECT {safe_sql_fields_joined} FROM {from_clause}{where_clause}{order_clause}{limit_clause}"
        results: list[ResourceResult] = []
        total_count: int = 0

        try:
            with closing(connection.cursor()) as cursor:
                cursor.execute(statement, params)
                rows = cursor.fetchall()

                if rows:
                    column_names = [description[0].lower() for description in cursor.description]
                    for row in rows:
                        row_dict = {column_names[i]: row[i] for i in range(len(column_names))}
                        type_value = row_dict.get("type", "")
                        resource_type = ResourceResultType.UNDEFINED

                        # map the type string back to enum
                        for rt in ResourceResultType:
                            if rt.value == type_value:
                                resource_type = rt
                                break

                        if resource_type == ResourceResultType.UNDEFINED and isinstance(type_value, int):
                            if type_value in RESOURCES_ENUMERATED_TYPE_MAPPING:
                                resource_type = RESOURCES_ENUMERATED_TYPE_MAPPING[type_value]

                        result = ResourceResult(
                            id=row_dict.get("id"),
                            site=row_dict.get("project"),
                            created=from_isoformat_zulu(row_dict.get("created")),
                            modified=from_isoformat_zulu(row_dict.get("modified")),
                            url=row_dict.get("url", ""),
                            type=resource_type,
                            name=row_dict.get("name"),
                            headers=row_dict.get("headers"),
                            content=row_dict.get("content") if "content" in selected_fields else None,
                            status=row_dict.get("status"),
                            size=row_dict.get("size"),
                            time=row_dict.get("time"),
                            metadata=None,
                        )

                        results.append(result)

                # get total count
                if len(results) < limit:
                    total_count = offset + len(results)
                else:
                    count_statement = f"SELECT COUNT(*) as total FROM {from_clause}{where_clause}"
                    cursor.execute(count_statement, params)
                    count_row = cursor.fetchone()
                    total_count = count_row[0] if count_row else 0

        except sqlite3.Error as ex:
            logger.error(f"SQLite error in structured query: {ex}\n{statement}\n{traceback.format_exc()}")
            return null_result

        return results, total_count, connection_index_state

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
        Check if content should be stored as text. Filter out deadweight content in fts index.
        """
        content_type_lower = content_type.lower()
        if content_type_lower.startswith("text/"):
            return True
        elif content_type_lower.startswith(("font/", "image/", "audio/", "video/", "application/octet-stream")):
            return False
        elif content_type_lower.startswith("application/"):
            return content_type_lower in {
                "application/atom+xml", "application/ld+json", "application/rss+xml",
                "application/x-www-form-urlencoded", "application/xml", "application/json",
                "application/javascript"
            }
        else:
            return True

