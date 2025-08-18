import os
import re
import sqlite3

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from mcp_server_webcrawl.crawlers.base.adapter import (
    BaseManager,
    IndexState,
    IndexStatus,
    SitesGroup,
    INDEXED_BATCH_SIZE,
    INDEXED_RESOURCE_DEFAULT_PROTOCOL,
    INDEXED_TYPE_MAPPING
)
from mcp_server_webcrawl.crawlers.base.indexed import IndexedManager
from mcp_server_webcrawl.utils.logger import get_logger
from mcp_server_webcrawl.models.resources import (
    ResourceResult,
    ResourceResultType,
    RESOURCES_LIMIT_DEFAULT,
)
from mcp_server_webcrawl.models.sites import (
    SiteResult,
)

# heads up. SiteOne uses wget adapters, this is unintuitive but reasonable as SiteOne
# uses wget for archiving. lean into maximal recycling of wget, if it stops making
# sense switch to homegrown
# from mcp_server_webcrawl.crawlers.wget.adapter import (
#     get_sites,  # hands off, used
# )

logger = get_logger()

class SiteOneManager(IndexedManager):
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
            directory: path to the site directory

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
            directory: path to the SiteOne directory
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
                batch_insert_crawled: list[ResourceResult] = []
                file_contents = BaseManager.read_files(batch_paths)
                for file_path in batch_paths:
                    try:
                        result: ResourceResult | None = self._prepare_siteone_record(file_path,
                                site_id, directory, log_data, file_contents.get(file_path))
                        if result and result.url not in processed_urls:
                            batch_insert_crawled.append(result)
                            processed_urls.add(result.url)
                            if index_state is not None:
                                index_state.increment_processed()
                    except Exception as e:
                        logger.error(f"Error processing file {file_path}: {e}")

                self._execute_batch_insert(connection, cursor, batch_insert_crawled)

            # HTTP errors not already processed
            batch_insert_errors: list[ResourceResult] = []
            for url, meta in log_http_error_data.items():
                if url not in processed_urls:
                    size = meta.get("size", 0)
                    result = ResourceResult(
                        id=BaseManager.string_to_id(url),
                        site=site_id,
                        url=url,
                        type=ResourceResultType.OTHER,
                        status=meta["status"],
                        headers=BaseManager.get_basic_headers(size, ResourceResultType.OTHER),
                        content="",     # no content
                        size=size,      # size from log
                        time=meta["time"]
                    )
                    batch_insert_errors.append(result)

                    if index_state is not None:
                        index_state.increment_processed()

                    # errors in batches too
                    if len(batch_insert_errors) >= INDEXED_BATCH_SIZE:
                        self._execute_batch_insert(connection, cursor, batch_insert_errors)

            # insert any remaining error records
            if batch_insert_errors:
                self._execute_batch_insert(connection, cursor, batch_insert_errors)

            if index_state is not None and index_state.status == IndexStatus.INDEXING:
                index_state.set_status(IndexStatus.COMPLETE)

    def _prepare_siteone_record(self, file_path: Path, site_id: int, base_dir: Path,
                            log_data: dict, content: str = None) -> ResourceResult | None:
        """
        Prepare a record for batch insertion from a SiteOne file.

        Args:
            file_path: path to the file
            site_id: id for the site
            base_dir: base directory for the capture
            log_data: dictionary of metadata from logs keyed by URL
            content: optional pre-loaded file content

        Returns:
            Tuple of (record tuple, URL) or None if processing fails
        """
        try:
            # generate relative url path from file path (similar to wget)
            relative_path = file_path.relative_to(base_dir)
            url = f"{INDEXED_RESOURCE_DEFAULT_PROTOCOL}{base_dir.name}/{str(relative_path).replace(os.sep, '/')}"

            if file_path.is_file():
                file_stat = file_path.stat()
                file_size = file_stat.st_size
                file_created = datetime.fromtimestamp(file_stat.st_ctime, tz=timezone.utc)
                file_modified = datetime.fromtimestamp(file_stat.st_mtime, tz=timezone.utc)
            else:
                file_created = None
                file_modified = None
                file_size = 0

            decruftified_path = BaseManager.decruft_path(str(file_path))
            extension = Path(decruftified_path).suffix.lower()
            wget_static_pattern = re.compile(r"\.[0-9a-f]{8,}\.")

            # look up metadata from log if available, otherwise use defaults
            metadata = None
            wget_aliases = list(set([
                url,                                   # exact match first
                re.sub(wget_static_pattern, ".", url), # static pattern
                url.replace(".html", ""),              # file without extension (redirects)
                url.replace(".html", "/"),             # directory style (targets)
                url.replace("index.html", ""),         # index removal
            ]))

            for wget_alias in wget_aliases:
                metadata = log_data.get(wget_alias, None)
                if metadata is not None:
                    break

            if metadata is not None:
                # preventing duplicate html pages ./appstat.html and ./appstat/index.html
                # prefer index.html (actual content) over redirect stubs
                canonical_url = None
                # Sort aliases to prefer index.html files over redirect stubs
                sorted_aliases = sorted([alias for alias in wget_aliases if log_data.get(alias) == metadata],
                                    key=lambda x: (not x.endswith('index.html'), x))

                if sorted_aliases:
                    canonical_url = sorted_aliases[0]  # Take the preferred one
                    url = canonical_url
            else:
                metadata = {}

            status_code = metadata.get("status", 200)
            response_time = metadata.get("time", 0)
            log_type = metadata.get("type", "").lower()

            if log_type:
                # no type for redirects, but more often than not
                # redirection to another page
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

            file_content = content
            if file_content is None:
                file_content = BaseManager.read_file_contents(file_path, resource_type)

            # skip redirect stub files left in SiteOne archive (duplicate, wait for real content)
            if status_code == 200 and file_content and '<meta http-equiv="refresh" content="0' in file_content:
                return None

            record = ResourceResult(
                id=BaseManager.string_to_id(url),
                site=site_id,
                created=file_created,
                modified=file_modified,
                url=url,
                type=resource_type,
                status=status_code,
                headers=BaseManager.get_basic_headers(file_size, resource_type),
                content=file_content,
                size=file_size,
                time=response_time  # possibly from log
            )
            return record
        except Exception as e:
            logger.error(f"Error preparing record for file {file_path}: {e}")
            return None

manager: SiteOneManager = SiteOneManager()

def get_sites(
        datasrc: Path,
        ids: list[int] | None = None,
        fields: list[str] | None = None
    ) -> list[SiteResult]:
    """
    List site directories in the datasrc directory as sites.

    Args:
        datasrc: path to the directory containing site subdirectories
        ids: optional list of site IDs to filter by
        fields: optional list of fields to include in the response

    Returns:
        List of SiteResult objects, one for each site directory

    Notes:
        Returns an empty list if the datasrc directory doesn't exist.
    """
    return manager.get_sites_for_directories(datasrc, ids, fields)

def get_resources(
    datasrc: Path,
    sites: list[int] | None = None,
    query: str = "",
    fields: list[str] | None = None,
    sort: str | None = None,
    limit: int = RESOURCES_LIMIT_DEFAULT,
    offset: int = 0,
) -> tuple[list[ResourceResult], int, IndexState]:
    """
    Get resources from wget directories using in-memory SQLite.

    Args:
        datasrc: path to the directory containing wget captures
        sites: optional list of site IDs to filter by
        query: search query string
        fields: optional list of fields to include in response
        sort: sort order for results
        limit: maximum number of results to return
        offset: number of results to skip for pagination

    Returns:
        Tuple of (list of ResourceResult objects, total count)
    """
    sites_results: list[SiteResult] = get_sites(datasrc=datasrc, ids=sites)
    assert sites_results, "At least one site is required to search"
    site_paths = [site.path for site in sites_results]
    sites_group = SitesGroup(datasrc, sites, site_paths)
    return manager.get_resources_for_sites_group(sites_group, query, fields, sort, limit, offset)
