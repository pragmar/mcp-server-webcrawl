import os
import sqlite3
import traceback
from datetime import timezone

from contextlib import closing
from datetime import datetime
from pathlib import Path

from mcp_server_webcrawl.crawlers.base.adapter import (
    BaseManager,
    IndexState,
    IndexStatus,
    SitesGroup,
    INDEXED_BATCH_SIZE,
    INDEXED_RESOURCE_DEFAULT_PROTOCOL,
    INDEXED_TYPE_MAPPING,
    INDEXED_IGNORE_DIRECTORIES,
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


class WgetManager(IndexedManager):
    """
    Manages wget directory data in in-memory SQLite databases.
    Provides connection pooling and caching for efficient access.
    """

    def __init__(self) -> None:
        """Initialize the wget manager with empty cache and statistics."""
        super().__init__()

    def _load_site_data(self, connection: sqlite3.Connection, directory: Path,
        site_id: int, index_state: IndexState = None) -> None:
        """
        Load a wget directory into the database with parallel processing and batch SQL insertions.

        Args:
            connection: SQLite connection
            directory: path to the wget directory
            site_id: id for the site
            index_state: indexState object for tracking progress
        """
        if not directory.exists() or not directory.is_dir():
            logger.error(f"Directory not found or not a directory: {directory}")
            return

        if index_state is not None:
            index_state.set_status(IndexStatus.INDEXING)

        # collect files to process
        file_paths = []
        for root, _, files in os.walk(directory):
            for filename in files:
                if filename == "robots.txt":
                    continue

                rel_path = Path(root).relative_to(directory)
                ignore_file = False
                for ignore_dir in INDEXED_IGNORE_DIRECTORIES:
                    if ignore_dir in str(rel_path):
                        ignore_file = True
                        break

                if not ignore_file:
                    file_paths.append(Path(root) / filename)

        # each crawler a litle different
        with closing(connection.cursor()) as cursor:
            for i in range(0, len(file_paths), INDEXED_BATCH_SIZE):
                if index_state is not None and index_state.is_timeout():
                    index_state.set_status(IndexStatus.PARTIAL)
                    return

                batch_file_paths: list[Path] = file_paths[i:i+INDEXED_BATCH_SIZE]
                batch_file_contents = BaseManager.read_files(batch_file_paths)
                batch_insert_resource_results: list[ResourceResult] = []
                for file_path, content in batch_file_contents.items():
                    try:
                        result: ResourceResult = self._prepare_wget_record(file_path, site_id, directory, content)
                        if result:
                            batch_insert_resource_results.append(result)
                            if index_state is not None:
                                index_state.increment_processed()
                    except Exception as e:
                        logger.error(f"Error processing file {file_path}: {e}\n{traceback.format_exc()}")

                self._execute_batch_insert(connection, cursor, batch_insert_resource_results)

            if index_state is not None and index_state.status == IndexStatus.INDEXING:
                index_state.set_status(IndexStatus.COMPLETE)

    def _prepare_wget_record(self, file_path: Path, site_id: int, base_dir: Path, content: str = None) -> ResourceResult | None:
        """
        Prepare a record for batch insertion from a wget file.

        Args:
            file_path: path to the wget file
            site_id: id for the site
            base_dir: base directory for the wget capture
            content: optional pre-loaded file content

        Returns:
            Tuple of values ready for insertion, or None if processing fails
        """
        try:
            relative_path = file_path.relative_to(base_dir)
            url = f"{INDEXED_RESOURCE_DEFAULT_PROTOCOL}{base_dir.name}/{str(relative_path).replace(os.sep, '/')}"
            decruftified_path = BaseManager.decruft_path(str(file_path))
            extension = Path(decruftified_path).suffix.lower()
            resource_type = INDEXED_TYPE_MAPPING.get(extension, ResourceResultType.OTHER)
            file_stat = file_path.stat()
            file_size = file_stat.st_size
            file_created = datetime.fromtimestamp(file_stat.st_ctime, tz=timezone.utc)
            file_modified = datetime.fromtimestamp(file_stat.st_mtime, tz=timezone.utc)

            # use pre-loaded content if available, otherwise rely on read_file_contents
            file_content = content
            if file_content is None:
                file_content = BaseManager.read_file_contents(file_path, resource_type)

            return ResourceResult(
                id=BaseManager.string_to_id(url),
                site=site_id,
                created=file_created,
                modified=file_modified,
                url=url,
                type=resource_type,
                status=200,
                headers=BaseManager.get_basic_headers(file_size, resource_type),
                content=file_content,
                size=file_size,
                time=0,
            )
        except Exception as e:
            logger.error(f"Error preparing record for file {file_path}: {e}")
            return None


manager: WgetManager = WgetManager()

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
