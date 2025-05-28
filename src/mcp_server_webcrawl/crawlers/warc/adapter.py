import email.utils
import os
import sqlite3
import warcio

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Final
from warcio.recordloader import ArcWarcRecord

from mcp_server_webcrawl.crawlers.base.adapter import (
    IndexState,
    IndexStatus,
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
    SITES_FIELDS_DEFAULT,
    SITES_FIELDS_REQUIRED,
)
from mcp_server_webcrawl.utils.logger import get_logger

logger = get_logger()

WARC_FILE_EXTENSIONS: Final[list[str]] = [".warc", ".warc.gz", ".txt"]


class WarcManager(IndexedManager):
    """
    Manages WARC file data in in-memory SQLite databases.
    Provides connection pooling and caching for efficient access.
    """

    def __init__(self) -> None:
        """Initialize the WARC manager with empty cache and statistics."""
        super().__init__()

    def _load_site_data(self, connection: sqlite3.Connection, warc_path: Path,
        site_id: int, index_state: IndexState = None) -> None:
        """
        Load a WARC file into the database with batch processing for better performance.

        Args:
            connection: SQLite connection
            warc_path: path to the WARC file
            site_id: ID for the site
            index_state: IndexState object for tracking progress
        """
        if not warc_path.exists() or not warc_path.is_file():
            logger.error(f"WARC file not found or not a file: {warc_path}")
            return

        with closing(connection.cursor()) as cursor:
            if index_state is not None:
                index_state.set_status(IndexStatus.INDEXING)
            try:
                batch_insert_resource_results: list[ResourceResult] = []
                batch_count: int = 0
                with open(warc_path, "rb") as stream:
                    for warc_record in warcio.ArchiveIterator(stream):

                        if index_state is not None and index_state.is_timeout():
                            index_state.set_status(IndexStatus.PARTIAL)
                            # commit current batch and shut it down
                            if batch_insert_resource_results:
                                self._execute_batch_insert(connection, cursor, batch_insert_resource_results)
                            return

                        if warc_record is not None and warc_record.rec_type == "response":
                            resource_result: ResourceResult = self._prepare_warc_record(warc_record, site_id)
                            if resource_result:
                                batch_insert_resource_results.append(resource_result)
                                if index_state is not None:
                                    index_state.increment_processed()

                                batch_count += 1
                                if batch_count >= INDEXED_BATCH_SIZE:
                                    self._execute_batch_insert(connection, cursor, batch_insert_resource_results)
                                    batch_insert_resource_results = []
                                    batch_count = 0

                # batch insert remaining
                if batch_insert_resource_results:
                    self._execute_batch_insert(connection, cursor, batch_insert_resource_results)

                if index_state is not None and index_state.status == IndexStatus.INDEXING:
                    index_state.set_status(IndexStatus.COMPLETE)

            except Exception as e:
                logger.error(f"Error processing WARC file {warc_path}: {e}")
                if index_state is not None:
                    index_state.set_status(IndexStatus.FAILED)

    def _prepare_warc_record(self, record: ArcWarcRecord, site_id: int) -> ResourceResult | None:
        """
        Prepare a WARC record for batch insertion.

        Args:
            record: a warcio record object
            site_id: ID for the site

        Returns:
            Tuple of values ready for insertion, or None if processing fails
        """
        try:
            url: str = record.rec_headers.get_header("WARC-Target-URI")
            content_type: str = record.http_headers.get_header("Content-Type", "")
            status: int = int(record.http_headers.get_statuscode()) or 200
            resource_type: ResourceResultType = self._determine_resource_type(content_type)
            content: bytes = record.content_stream().read()
            content_size: int = len(content)

            if self._is_text_content(content_type):
                try:
                    content_str: str = content.decode("utf-8")
                except UnicodeDecodeError:
                    content_str = None
            else:
                content_str = None

            warc_date = record.rec_headers.get_header("WARC-Date")
            if warc_date:
                try:
                    file_created = datetime.fromisoformat(warc_date.replace('Z', '+00:00'))
                except ValueError:
                    # Fallback to email date parser
                    try:
                        time_tuple = email.utils.parsedate_tz(warc_date)
                        file_created = datetime.fromtimestamp(email.utils.mktime_tz(time_tuple), tz=timezone.utc)
                    except (ValueError, TypeError):
                        file_created = datetime.now(timezone.utc)
            else:
                file_created = None # don't pretend it is now, ResourceResult can survive
            file_modified = file_created # like file stat indexes, these are equivalent

            result = ResourceResult(
                id=IndexedManager.string_to_id(url),
                site=site_id,
                created=file_created,
                modified=file_modified,
                url=url,
                type=resource_type,
                status=status,
                headers=record.http_headers.to_str(),
                content=content_str,
                size=content_size,
                time=0  # time not available
            )
            return result
        except Exception as e:
            logger.error(f"Error processing WARC record for URL {url if 'url' in locals() else 'unknown'}: {e}")
            return None

manager: WarcManager = WarcManager()

def get_sites(
    datasrc: Path,
    ids: list[int] | None = None,
    fields: list[str] | None = None
) -> list[SiteResult]:
    """
    List WARC files in the datasrc directory as sites.

    Args:
        datasrc: path to the directory containing WARC files
        ids: optional list of site IDs to filter by
        fields: list of fields to include in the response

    Returns:
        List of SiteResult objects, one for each WARC file
    """
    assert datasrc is not None, f"datasrc not provided ({datasrc})"

    # nothing can be done, but don't crash the server either, keep chugging along
    if not datasrc.exists():
        logger.error(f"Directory not found ({datasrc})")
        return []

    # determine which fields to include
    selected_fields: set[str] = set(SITES_FIELDS_REQUIRED)
    if fields:
        valid_fields: set[str] = set(SITES_FIELDS_DEFAULT)
        selected_fields.update(f for f in fields if f in valid_fields)
    else:
        selected_fields.update(SITES_FIELDS_DEFAULT)

    results: list[SiteResult] = []

    files_to_check: list[Path] = []
    for ext in WARC_FILE_EXTENSIONS:
        files_to_check.extend(datasrc.glob(f"*{ext}"))

    # map of file_id -> file_path for filtering
    file_id_map: dict[int, Path] = {WarcManager.string_to_id(str(os.path.basename(f))): f for f in files_to_check if f is not None}

    if ids:
        file_id_map = {id_val: path for id_val, path in file_id_map.items() if id_val in ids}

    for site_id, file_path in sorted(file_id_map.items()):
        file_stat = file_path.stat()
        created_time: datetime = datetime.fromtimestamp(file_stat.st_ctime)
        modified_time: datetime = datetime.fromtimestamp(file_stat.st_mtime)
        site: SiteResult = SiteResult(
            path=file_path,
            id=site_id,
            url=str(file_path.absolute()),
            created=created_time if "created" in selected_fields else None,
            modified=modified_time if "modified" in selected_fields else None,
        )
        results.append(site)
    return results

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
