import os
import re
import sqlite3

from contextlib import closing
from pathlib import Path
from typing import Any, Optional, Tuple

from mcp_server_webcrawl.crawlers.base.adapter import BaseManager
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
    WGET_TYPE_MAPPING,
    get_sites, # recycle wget get sites, there is no difference
    get_resources_with_manager, # get_resources wrapper using SiteOneManager
)

# field mappings similar to other adapters
SITEONE_TYPE_MAPPING = WGET_TYPE_MAPPING

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


    def _load_site_data(self, connection: sqlite3.Connection, directory: Path, site_id: int) -> None:
        directory_name: str = directory.name

        # target SiteOne text log for additional metadata beyond wget
        log_data = {}
        log_http_error_data = {}

        log_pattern: str = f"output.{directory_name}.*.txt"
        log_files = list(Path(directory.parent).glob(log_pattern))
        if log_files:
            log_latest = max(log_files, key=lambda p: p.stat().st_mtime)
            with open(log_latest, "r", encoding="utf-8") as log_file:
                for line in log_file:
                    parts = [part.strip() for part in line.split("|")]
                    if len(parts) == 10:
                        parts_path = parts[3].split("?")[0]
                        try:
                            status = int(parts[4])
                            url = f"http://{directory_name}{parts_path}"
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

        with closing(connection.cursor()) as cursor:

            processed_urls = set()

            for root, _, files in os.walk(directory):
                for filename in files:
                    if filename == "robots.txt" or filename.startswith("output.") and filename.endswith(".txt"):
                        continue
                    file_path = Path(root) / filename
                    url = self._process_siteone_file(cursor, file_path, site_id, directory, log_data)
                    if url:
                        processed_urls.add(url)

            # add HTTP errors not already processed (wget did not download, limited data)
            for url, meta in log_http_error_data.items():
                if url not in processed_urls:
                    size = meta.get("size", 0)
                    cursor.execute("""
                        INSERT INTO ResourcesFullText (
                            Id, Project, Url, Type, Status,
                            Headers, Content, Size, Time
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        BaseManager.string_to_id(url),
                        site_id,
                        url,
                        ResourceResultType.OTHER.value,
                        meta["status"],
                        BaseManager.get_basic_headers(size, ResourceResultType.OTHER),
                        None,  # no content
                        size,     # Zero size
                        meta["time"]
                    ))

            connection.commit()

    def _process_siteone_file(self, cursor: sqlite3.Cursor, file_path: Path,
                             site_id: int, base_dir: Path, log_data: dict) -> str:
        """
        Process a single file and insert it into the database with log metadata.

        Args:
            cursor: SQLite cursor
            file_path: Path to the file
            site_id: ID for the site
            base_dir: Base directory for the capture
            log_data: Dictionary of metadata from logs keyed by URL

        Returns:
            str: URL of the resource that was added to the database
        """
        # relative url path from file path (similar to wget)
        relative_path = file_path.relative_to(base_dir)
        url = f"http://{base_dir.name}/{str(relative_path).replace(os.sep, '/')}"
        file_size = file_path.stat().st_size
        decruftified_path = BaseManager.decruft_path(file_path)
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

        status_code = metadata.get("status", 200)
        response_time = metadata.get("time", 0)
        log_type = metadata.get("type", "").lower()

        if metadata is None:
            metadata = {}

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
            resource_type = type_mapping.get(log_type, SITEONE_TYPE_MAPPING.get(extension, ResourceResultType.OTHER))
        else:
            # fallback to extension-based mapping
            resource_type = SITEONE_TYPE_MAPPING.get(extension, ResourceResultType.OTHER)

        cursor.execute("""
            INSERT INTO ResourcesFullText (
                Id, Project, Url, Type, Status,
                Headers, Content, Size, Time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            BaseManager.string_to_id(url),
            site_id,
            url,
            resource_type.value,
            status_code,  # possibly from log
            BaseManager.get_basic_headers(file_size, resource_type),
            BaseManager.read_file_contents(file_path, resource_type),
            file_size,
            response_time  # possibly from log
        ))

        return url


manager: SiteOneManager = SiteOneManager()

def get_resources(
    datasrc: Path,
    ids: Optional[list[int]] = None,
    sites: Optional[list[int]] = None,
    query: str = "",
    types: Optional[list[ResourceResultType]] = None,
    fields: Optional[list[str]] = None,
    statuses: Optional[list[int]] = None,
    sort: Optional[str] = None,
    limit: int = RESOURCES_LIMIT_DEFAULT,
    offset: int = 0
) -> Tuple[list[ResourceResult], int]:
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
