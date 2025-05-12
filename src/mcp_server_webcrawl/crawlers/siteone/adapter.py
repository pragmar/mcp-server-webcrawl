import os
import re
import sqlite3

from contextlib import closing
from pathlib import Path

from mcp_server_webcrawl.crawlers.base.adapter import (
    BaseManager,
    IndexState,
    IndexStatus,
    INDEXED_BATCH_SIZE,
    INDEXED_RESOURCE_DEFAULT_PROTOCOL,
    INDEXED_TYPE_MAPPING
)
from mcp_server_webcrawl.utils.logger import get_logger
from mcp_server_webcrawl.models.resources import (
    ResourceResult,
    ResourceResultType,
    RESOURCES_LIMIT_DEFAULT,
)

# heads up. SiteOne uses wget adapters, this is unintuitive but reasonable as SiteOne
# uses wget for archiving. lean into maximal recycling of wget, if it stops making
# sense switch to homegrown
from mcp_server_webcrawl.crawlers.wget.adapter import (
    get_sites,  # hands off, used
    get_resources_with_manager,
)

logger = get_logger()

class SiteOneManager(BaseManager):
    """
    Manages SiteOne directory data in in-memory SQLite databases.
    Wraps wget archive format (shared by SiteOne and wget)
    Provides connection pooling and caching for efficient access.
    """

    def __init__(self) -> None:
        """Initialize the SiteOne manager with empty cache and statistics."""

        super().__init__()

    def _extract_log_metadata(self, directory: Path) -> tuple[dict, dict]:
        """
        Extract metadata from SiteOne log files.

        Args:
            directory: Path to the site directory

        Returns:
            Tuple of (success log data, error log data) dictionaries
        """
        directory_name: str = directory.name
        log_data = {}
        log_http_error_data = {}

        log_pattern: str = f"output.{directory_name}.*.txt"
        log_files = list(Path(directory.parent).glob(log_pattern))

        if not log_files:
            return log_data, log_http_error_data

        log_latest = max(log_files, key=lambda p: p.stat().st_mtime)

        try:
            with open(log_latest, "r", encoding="utf-8") as log_file:
                for line in log_file:
                    parts = [part.strip() for part in line.split("|")]
                    if len(parts) == 10:
                        parts_path = parts[3].split("?")[0]
                        try:
                            status = int(parts[4])
                            url = f"{INDEXED_RESOURCE_DEFAULT_PROTOCOL}{directory_name}{parts_path}"
                            time_str = parts[6].split()[0]
                            time = int(float(time_str) * (1000 if "s" in parts[6] else 1))

                            # size collected for errors, os stat preferred
                            size_str = parts[7].strip()
                            size = 0
                            if size_str:
                                size_value = float(size_str.split()[0])
                                size_unit = size_str.split()[1].lower() if len(size_str.split()) > 1 else "b"
                                multiplier = {
                                    "b": 1,
                                    "kb": 1024,
                                    "kB": 1024,
                                    "mb": 1024*1024,
                                    "MB": 1024*1024,
                                    "gb": 1024*1024*1024,
                                    "GB": 1024*1024*1024
                                }.get(size_unit, 1)
                                size = int(size_value * multiplier)

                            if 400 <= status < 600:
                                log_http_error_data[url] = {
                                    "status": status,
                                    "type": parts[5].lower(),
                                    "time": time,
                                    "size": size,
                                }
                            else:
                                log_data[url] = {
                                    "status": status,
                                    "type": parts[5].lower(),
                                    "time": time,
                                    "size": size,
                                }

                        except (ValueError, IndexError, UnicodeDecodeError, KeyError):
                            continue

                    elif line.strip() == "Redirected URLs":
                        # stop processing we're through HTTP requests
                        break
        except Exception as e:
            logger.error(f"Error processing log file {log_latest}: {e}")

        return log_data, log_http_error_data

    def _load_site_data(self, connection: sqlite3.Connection, directory: Path,
            site_id: int, index_state: IndexState = None) -> None:
        """
        Load a SiteOne directory into the database with parallel processing and batch insertions.

        Args:
            connection: SQLite connection
            directory: Path to the SiteOne directory
            site_id: ID for the site
            index_state: IndexState object for tracking progress
        """

        if not directory.exists() or not directory.is_dir():
            logger.error(f"Directory not found or not a directory: {directory}")
            return

        if index_state is not None:
            index_state.set_status(IndexStatus.INDEXING)

        log_data, log_http_error_data = self._extract_log_metadata(directory)

        file_paths = []
        for root, _, files in os.walk(directory):
            for filename in files:
                if filename == "robots.txt" or (filename.startswith("output.") and filename.endswith(".txt")):
                    continue
                file_paths.append(Path(root) / filename)

        processed_urls = set()

        with closing(connection.cursor()) as cursor:
            for i in range(0, len(file_paths), INDEXED_BATCH_SIZE):
                if index_state is not None and index_state.is_timeout():
                    index_state.set_status(IndexStatus.PARTIAL)
                    return

                batch_paths = file_paths[i:i+INDEXED_BATCH_SIZE]
                batch_insert_data = []
                file_contents = BaseManager.read_files(batch_paths)
                for file_path in batch_paths:
                    try:
                        result = self._prepare_siteone_record(file_path, site_id, directory, log_data, file_contents.get(file_path))
                        if result:
                            record, url = result
                            batch_insert_data.append(record)
                            processed_urls.add(url)
                            if index_state is not None:
                                index_state.increment_processed()
                    except Exception as e:
                        logger.error(f"Error processing file {file_path}: {e}")

                if batch_insert_data:
                    try:
                        connection.execute("BEGIN TRANSACTION")
                        cursor.executemany("""
                            INSERT INTO ResourcesFullText (
                                Id, Project, Url, Type, Status,
                                Headers, Content, Size, Time
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, batch_insert_data)
                        connection.execute("COMMIT")
                    except Exception as e:
                        connection.execute("ROLLBACK")
                        logger.error(f"Error during batch insert: {e}")

            # Process HTTP errors not already processed
            error_batch = []
            for url, meta in log_http_error_data.items():
                if url not in processed_urls:
                    size = meta.get("size", 0)
                    error_record = (
                        BaseManager.string_to_id(url),
                        site_id,
                        url,
                        ResourceResultType.OTHER.value,
                        meta["status"],
                        BaseManager.get_basic_headers(size, ResourceResultType.OTHER),
                        "",     # no content
                        size,   # size from log
                        meta["time"]
                    )
                    error_batch.append(error_record)

                    if index_state is not None:
                        index_state.increment_processed()

                    # Process error records in batches too
                    if len(error_batch) >= INDEXED_BATCH_SIZE:
                        try:
                            connection.execute("BEGIN TRANSACTION")
                            cursor.executemany("""
                                INSERT INTO ResourcesFullText (
                                    Id, Project, Url, Type, Status,
                                    Headers, Content, Size, Time
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, error_batch)
                            connection.execute("COMMIT")
                            error_batch = []
                        except Exception as e:
                            connection.execute("ROLLBACK")
                            logger.error(f"Error during error batch insert: {e}")

            # Insert any remaining error records
            if error_batch:
                try:
                    connection.execute("BEGIN TRANSACTION")
                    cursor.executemany("""
                        INSERT INTO ResourcesFullText (
                            Id, Project, Url, Type, Status,
                            Headers, Content, Size, Time
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, error_batch)
                    connection.execute("COMMIT")
                except Exception as e:
                    connection.execute("ROLLBACK")
                    logger.error(f"Error during final error batch insert: {e}")

            if index_state is not None and index_state.status == IndexStatus.INDEXING:
                index_state.set_status(IndexStatus.COMPLETE)

    def _prepare_siteone_record(self, file_path: Path, site_id: int, base_dir: Path,
                            log_data: dict, content: str = None) -> tuple[tuple, str] | None:
        """
        Prepare a record for batch insertion from a SiteOne file.

        Args:
            file_path: Path to the file
            site_id: ID for the site
            base_dir: Base directory for the capture
            log_data: Dictionary of metadata from logs keyed by URL
            content: Optional pre-loaded file content

        Returns:
            Tuple of (record tuple, URL) or None if processing fails
        """
        try:
            # generate relative url path from file path (similar to wget)
            relative_path = file_path.relative_to(base_dir)
            url = f"{INDEXED_RESOURCE_DEFAULT_PROTOCOL}{base_dir.name}/{str(relative_path).replace(os.sep, '/')}"
            file_size = file_path.stat().st_size
            decruftified_path = BaseManager.decruft_path(str(file_path))
            extension = Path(decruftified_path).suffix.lower()
            wget_static_pattern = re.compile(r"\.[0-9a-f]{8,}\.")

            # look up metadata from log if available, otherwise use defaults
            metadata = None
            wget_aliases = list(set([
                url,
                url.replace("index.html", ""),
                url.replace(".html", "/"),
                url.replace(".html", ""),
                re.sub(wget_static_pattern, ".", url)
            ]))

            for wget_alias in wget_aliases:
                metadata = log_data.get(wget_alias, None)
                if metadata is not None:
                    break

            if metadata is None:
                metadata = {}

            status_code = metadata.get("status", 200)
            response_time = metadata.get("time", 0)
            log_type = metadata.get("type", "").lower()

            if log_type:
                # no type for redirects, but more often than not pages
                type_mapping = {
                    "html": ResourceResultType.PAGE,
                    "redirect": ResourceResultType.PAGE,
                    "image": ResourceResultType.IMAGE,
                    "js": ResourceResultType.SCRIPT,
                    "css": ResourceResultType.CSS,
                    "video": ResourceResultType.VIDEO,
                    "audio": ResourceResultType.AUDIO,
                    "pdf": ResourceResultType.PDF,
                    "other": ResourceResultType.OTHER,
                    "font": ResourceResultType.OTHER,
                }
                resource_type = type_mapping.get(log_type, INDEXED_TYPE_MAPPING.get(extension, ResourceResultType.OTHER))
            else:
                # fallback to extension-based mapping
                resource_type = INDEXED_TYPE_MAPPING.get(extension, ResourceResultType.OTHER)

            # Use pre-loaded content if available, otherwise rely on read_file_contents
            file_content = content
            if file_content is None:
                file_content = BaseManager.read_file_contents(file_path, resource_type)

            record = (
                BaseManager.string_to_id(url),
                site_id,
                url,
                resource_type.value,
                status_code,  # possibly from log
                BaseManager.get_basic_headers(file_size, resource_type),
                file_content,
                file_size,
                response_time  # possibly from log
            )

            return record, url
        except Exception as e:
            logger.error(f"Error preparing record for file {file_path}: {e}")
            return None

manager: SiteOneManager = SiteOneManager()

def get_resources(
    datasrc: Path,
    ids: list[int] | None = None,
    sites: list[int] | None = None,
    query: str = "",
    types: list[ResourceResultType] | None = None,
    fields: list[str] | None = None,
    statuses: list[int] | None = None,
    sort: str | None = None,
    limit: int = RESOURCES_LIMIT_DEFAULT,
    offset: int = 0,
) -> tuple[list[ResourceResult], int, IndexState]:
    """
    Get resources from wget directories using in-memory SQLite.

    Args:
        datasrc: Path to the directory containing wget captures
        ids: Optional list of resource IDs to filter by
        sites: Optional list of site IDs to filter by
        query: Search query string
        types: Optional list of resource types to filter by
        fields: Optional list of fields to include in response
        statuses: Optional list of HTTP status codes to filter by
        sort: Sort order for results
        limit: Maximum number of results to return
        offset: Number of results to skip for pagination

    Returns:
        Tuple of (list of ResourceResult objects, total count)
    """

    return get_resources_with_manager(manager, datasrc, ids, sites, query, types, fields, statuses, sort, limit, offset)
