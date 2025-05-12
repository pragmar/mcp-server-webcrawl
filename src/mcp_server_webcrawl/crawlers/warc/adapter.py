import os
import sqlite3
import warcio

from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Final
from warcio.recordloader import ArcWarcRecord

from mcp_server_webcrawl.crawlers.base.adapter import (
    BaseManager,
    IndexState,
    IndexStatus,
    SitesGroup,
    INDEXED_BATCH_SIZE,
    INDEXED_SORT_MAPPING
)
from mcp_server_webcrawl.models.resources import (
    ResourceResult,
    ResourceResultType,
    RESOURCES_DEFAULT_FIELD_MAPPING,
    RESOURCES_FIELDS_REQUIRED,
    RESOURCES_LIMIT_DEFAULT,
    RESOURCES_LIMIT_MAX,
)
from mcp_server_webcrawl.models.sites import (
    SiteResult,
    SITES_FIELDS_DEFAULT,
    SITES_FIELDS_REQUIRED,
)
from mcp_server_webcrawl.utils.logger import get_logger

logger = get_logger()

WARC_FILE_EXTENSIONS: Final[list[str]] = [".warc", ".warc.gz", ".txt"]

class WarcManager(BaseManager):
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
            warc_path: Path to the WARC file
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
                batch_records = []
                batch_count = 0
                with open(warc_path, "rb") as stream:
                    for record in warcio.ArchiveIterator(stream):

                        if index_state is not None and index_state.has_timed_out():
                            index_state.set_status(IndexStatus.PARTIAL)
                            if batch_records:
                                self._execute_batch_insert(connection, cursor, batch_records)
                            return

                        if record is not None and record.rec_type == "response":
                            record_data = self._prepare_warc_record(record, site_id)
                            if record_data:
                                batch_records.append(record_data)
                                if index_state is not None:
                                    index_state.increment_processed()

                                batch_count += 1

                                # batch insert chunk
                                if batch_count >= INDEXED_BATCH_SIZE:
                                    self._execute_batch_insert(connection, cursor, batch_records)
                                    batch_records = []
                                    batch_count = 0

                # batch insert remaining
                if batch_records:
                    self._execute_batch_insert(connection, cursor, batch_records)

                if index_state is not None and index_state.status == IndexStatus.INDEXING:
                    index_state.set_status(IndexStatus.COMPLETE)

            except Exception as e:
                logger.error(f"Error processing WARC file {warc_path}: {e}")
                if index_state is not None:
                    index_state.set_status(IndexStatus.FAILED)

    def _execute_batch_insert(self, connection: sqlite3.Connection, cursor: sqlite3.Cursor,
                            batch_records: list[tuple]) -> None:
        """
        Execute batch insert of WARC records with transaction handling.

        Args:
            connection: SQLite connection
            cursor: SQLite cursor
            batch_records: List of record tuples ready for insertion
        """
        if not batch_records:
            return

        try:
            connection.execute("BEGIN TRANSACTION")
            cursor.executemany("""
                INSERT INTO ResourcesFullText (
                    Id, Project, Url, Type, Status,
                    Headers, Content, Size, Time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, batch_records)
            connection.execute("COMMIT")
        except Exception as e:
            connection.execute("ROLLBACK")
            logger.error(f"Error during batch insert: {e}")

    def _prepare_warc_record(self, record: ArcWarcRecord, site_id: int) -> tuple | None:
        """
        Prepare a WARC record for batch insertion.

        Args:
            record: A warcio record object
            site_id: ID for the site

        Returns:
            Tuple of values ready for insertion, or None if processing fails
        """
        try:
            url: str = record.rec_headers.get_header("WARC-Target-URI")
            content_type: str = record.http_headers.get_header("Content-Type", "")
            status: int = record.http_headers.get_statuscode() or 0
            res_type: ResourceResultType = self._determine_resource_type(content_type)
            content: bytes = record.content_stream().read()
            content_size: int = len(content)

            if self._is_text_content(content_type):
                try:
                    content_str: str = content.decode("utf-8")
                except UnicodeDecodeError:
                    content_str = None
            else:
                content_str = None

            return (
                BaseManager.string_to_id(url),
                site_id,
                url,
                res_type.value,
                status,
                record.http_headers.to_str(),
                content_str,
                content_size,
                0  # Time not available
            )
        except Exception as e:
            logger.error(f"Error processing WARC record for URL {url if 'url' in locals() else 'unknown'}: {e}")
            return None

manager: WarcManager = WarcManager()

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
    Get resources from WARC files using in-memory SQLite.

    Args:
        datasrc: Path to the directory containing WARC files
        ids: Optional list of resource IDs to filter by
        sites: Optional list of site IDs to filter by
        query: Search query string
        types: Optional list of resource types to filter by
        fields: Optional list of fields to include in the response
        statuses: Optional list of HTTP status codes to filter by
        sort: Sort order for results
        limit: Maximum number of results to return
        offset: Number of results to skip for pagination

    Returns:
        Tuple of (list of ResourceResult objects, total count)
    """

    if not sites or len(sites) == 0:
        return [], 0

    site_results = get_sites(datasrc, ids=sites)
    if not site_results:
        return [], 0

    site_paths = [Path(site.url) for site in site_results]
    sites_group = SitesGroup(sites, site_paths)
    connection: sqlite3.Connection
    connection_index_state: IndexState
    connection, connection_index_state = manager.get_connection(sites_group)

    if connection is None:
        # database is currently being built
        logger.info(f"Database for sites {sites} is currently being built, try again later")
        return [], 0

    # normalize limit and prepare field selection
    limit = min(max(1, limit), RESOURCES_LIMIT_MAX)

    # process field selection
    select_fields: set[str] = set(RESOURCES_FIELDS_REQUIRED)
    if fields:
        select_fields.update(f for f in fields if f in RESOURCES_DEFAULT_FIELD_MAPPING)

    # convert to qualified field names
    qualified_fields: list[str] = [RESOURCES_DEFAULT_FIELD_MAPPING[f] for f in select_fields]
    fields_joined: str = ", ".join(qualified_fields)

    # build query components
    params: dict[str, int | str] = {}
    where_clauses: list[str] = []

    if ids:
        placeholders: list[str] = [f":id{i}" for i in range(len(ids))]
        where_clauses.append(f"Id IN ({','.join(placeholders)})")
        params.update({f"id{i}": id_val for i, id_val in enumerate(ids)})

    if types:
        type_placeholders: list[str] = [f":type{i}" for i in range(len(types))]
        where_clauses.append(f"Type IN ({','.join(type_placeholders)})")
        params.update({f"type{i}": type_val.value for i, type_val in enumerate(types)})

    if statuses:
        status_placeholders: list[str] = [f":status{i}" for i in range(len(statuses))]
        where_clauses.append(f"Status IN ({','.join(status_placeholders)})")
        params.update({f"status{i}": str(status_val) for i, status_val in enumerate(statuses)})

    if query.strip():
        where_clauses.append("ResourcesFullText MATCH :query")
        params["query"] = query.strip()

    where_clause: str = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    if sort in INDEXED_SORT_MAPPING:
        field, direction = INDEXED_SORT_MAPPING[sort]
        if direction == "RANDOM":
            order_clause: str = " ORDER BY RANDOM()"
        else:
            order_clause = f" ORDER BY {field} {direction}"
    else:
        order_clause = " ORDER BY Id ASC"

    limit_clause: str = f" LIMIT {limit} OFFSET {offset}"
    statement: str = f"SELECT {fields_joined} FROM ResourcesFullText{where_clause}{order_clause}{limit_clause}"
    results: list[ResourceResult] = []
    total_count: int = 0

    try:
        with closing(connection.cursor()) as cursor:
            cursor.execute(statement, params)
            rows: list[tuple] = cursor.fetchall()
            if rows:
                column_names: list[str] = [description[0].lower() for description in cursor.description]
                for row in rows:
                    row_dict: dict[str, int | str | None] = {column_names[i]: row[i] for i in range(len(column_names))}
                    type_value: str = row_dict.get("type", "")
                    resource_type: ResourceResultType = ResourceResultType.UNDEFINED
                    for rt in ResourceResultType:
                        if rt.value == type_value:
                            resource_type = rt
                            break

                    result: ResourceResult = ResourceResult(
                        id=row_dict.get("id"),
                        site=row_dict.get("project"),
                        url=row_dict.get("url", ""),
                        type=resource_type,
                        name=row_dict.get("name"),
                        headers=row_dict.get("headers"),
                        content=row_dict.get("content") if "content" in select_fields else None,
                        status=row_dict.get("status"),
                        size=row_dict.get("size"),
                        time=row_dict.get("time"),
                        metadata=None,  # reserved
                    )

                    results.append(result)

            if len(results) < limit:
                total_count = offset + len(results)
            else:
                count_statement: str = f"SELECT COUNT(*) as total FROM ResourcesFullText{where_clause}"
                cursor.execute(count_statement, params)
                count_row: tuple = cursor.fetchone()
                total_count = count_row[0] if count_row else 0

    except sqlite3.Error as e:
        print(f"SQLite error in WARC adapter: {e}")
        return [], 0

    return results, total_count, connection_index_state


def get_sites(
    datasrc: Path,
    ids: list[int] | None = None,
    fields: list[str] | None = None
) -> list[SiteResult]:
    """
    List WARC files in the datasrc directory as sites.

    Args:
        datasrc: Path to the directory containing WARC files
        ids: Optional list of site IDs to filter by
        fields: List of fields to include in the response

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
            id=site_id,
            url=str(file_path.absolute()),
            created=created_time if "created" in selected_fields else None,
            modified=modified_time if "modified" in selected_fields else None,
        )
        results.append(site)

    return results
