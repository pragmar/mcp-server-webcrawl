import re
import sqlite3

from itertools import chain
from contextlib import closing
from pathlib import Path

from datetime import datetime, timezone

from mcp_server_webcrawl.crawlers.base.adapter import (
    IndexState,
    IndexStatus,
    BaseManager,
    SitesGroup,
    INDEXED_BATCH_SIZE,
)
from mcp_server_webcrawl.crawlers.base.indexed import IndexedManager
from mcp_server_webcrawl.models.resources import (
    ResourceResult,
    ResourceResultType,
    RESOURCES_LIMIT_DEFAULT,
)
from mcp_server_webcrawl.models.sites import (
    SiteResult,
)
from mcp_server_webcrawl.utils.logger import get_logger

logger = get_logger()


class KatanaManager(IndexedManager):
    """
    Manages HTTP text files in in-memory SQLite databases.
    Provides connection pooling and caching for efficient access.
    """

    def __init__(self) -> None:
        """Initialize the HTTP text manager with empty cache and statistics."""
        super().__init__()

    def _load_site_data(self, connection: sqlite3.Connection, directory: Path,
            site_id: int, index_state: IndexState = None) -> None:
        """
        Load a site directory of HTTP text files into the database with parallel reading
        and batch SQL insertions.

        Args:
            connection: SQLite connection
            directory: path to the site directory
            site_id: ID for the site
            index_state: tracker for FTS indexing status
        """

        if not directory.exists() or not directory.is_dir():
            logger.error(f"Directory not found or not a directory: {directory}")
            return

        if index_state is not None:
            index_state.set_status(IndexStatus.INDEXING)

        file_paths = list(chain(
            directory.glob("*.txt"),
            directory.glob("*/*.txt")  # katana stores offsite assets under hostname
        ))

        with closing(connection.cursor()) as cursor:
            for i in range(0, len(file_paths), INDEXED_BATCH_SIZE):
                if index_state is not None and index_state.is_timeout():
                    index_state.set_status(IndexStatus.PARTIAL)
                    return

                batch_file_paths: list[Path] = file_paths[i:i+INDEXED_BATCH_SIZE]
                batch_file_contents = BaseManager.read_files(batch_file_paths)
                batch_insert_resource_results: list[ResourceResult] = []
                for file_path, content in batch_file_contents.items():
                    # avoid readme in repo, katana crawl files should be named 9080ef8...
                    if file_path.name.lower().endswith("readme.txt"):
                        continue
                    try:
                        record = self._prepare_katana_record(file_path, site_id, content)
                        if record:
                            batch_insert_resource_results.append(record)
                            if index_state is not None:
                                index_state.increment_processed()
                    except Exception as e:
                        logger.error(f"Error processing file {file_path}: {e}")

                self._execute_batch_insert(connection, cursor, batch_insert_resource_results)

            if index_state is not None and index_state.status == IndexStatus.INDEXING:
                index_state.set_status(IndexStatus.COMPLETE)

    def _prepare_katana_record(self, file_path: Path, site_id: int, content: str) -> ResourceResult | None:
        """
        Prepare a record for batch insertion.

        Args:
            file_path: path to the Katana crawl file record
            site_id: ID for the site
            content: loaded file content

        Returns:
            ResourceResult object ready for insertion, or None if processing fails
        """
        if file_path.is_file():
            file_stat = file_path.stat()
            # HTTP header modified mostly useless, change my mind
            file_created = datetime.fromtimestamp(file_stat.st_ctime, tz=timezone.utc)
            file_modified = datetime.fromtimestamp(file_stat.st_mtime, tz=timezone.utc)
        else:
            file_created = None
            file_modified = None

        # crawl format: <url>\n\n<request>\n\n<headers>...<response>
        parts: list[str] = content.split("\n\n", 2)
        if len(parts) < 3:
            logger.warning(f"Invalid HTTP text format in file {file_path}")
            return None

        url: str = parts[0].strip()
        response_data: str = parts[2].strip()

        try:
            response_parts: list[str] = response_data.split("\n\n", 1)
            headers: str = response_parts[0].strip()
            body: str = response_parts[1].strip() if len(response_parts) > 1 else ""

            if "Transfer-Encoding: chunked" in headers:
                body = body.split("\n", 1)[1].strip()   # remove hex prefix
                body = body.rsplit("\n0", 1)[0].strip() # remove trailing "0" terminator

            # status from the first line of headers
            status_match: str = re.search(r"HTTP/\d\.\d\s+(\d+)", headers.split("\n")[0])
            status_code: int = int(status_match.group(1)) if status_match else 0

            content_type_match = re.search(r"Content-Type:\s*([^\r\n;]+)", headers, re.IGNORECASE)
            content_type = content_type_match.group(1).strip() if content_type_match else ""
            resource_type = self._determine_resource_type(content_type)
            content_size = len(body)
            resource_id = BaseManager.string_to_id(url)

            return ResourceResult(
                id=resource_id,
                site=site_id,
                created=file_created,
                modified=file_modified,
                url=url,
                type=resource_type,
                headers=headers,
                content=body if self._is_text_content(content_type) else None,
                status=status_code,
                size=content_size,
                time=0  # time not available in file or Katana index
            )

        except Exception as e:
            logger.error(f"Error processing HTTP response in file {file_path}: {e}")
            return None

manager: KatanaManager = KatanaManager()

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
        datasrc: path to the directory containing wget captures
        ids: optional list of resource IDs to filter by
        sites: optional list of site IDs to filter by
        query: search query string
        types: optional list of resource types to filter by
        fields: optional list of fields to include in response
        statuses: optional list of HTTP status codes to filter by
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
