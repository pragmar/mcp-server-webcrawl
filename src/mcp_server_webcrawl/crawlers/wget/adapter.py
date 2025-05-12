import os
import sqlite3

from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Final

from mcp_server_webcrawl.crawlers.base.adapter import (
    BaseManager,
    IndexState,
    IndexStatus,
    SitesGroup,
    INDEXED_BATCH_SIZE,
    INDEXED_RESOURCE_DEFAULT_PROTOCOL,
    INDEXED_SORT_MAPPING,
    INDEXED_TYPE_MAPPING
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

# "http-client-cache", "result-storage" are technically SiteOne ignores
# but this is the only modification to an otherwise clean alias of wget
# a complete breakout of SiteOne subclassing isn't necessary yet
WGET_IGNORE_DIRECTORIES: Final[list[str]] = ["http-client-cache", "result-storage"]

logger = get_logger()

class WgetManager(BaseManager):
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
            directory: Path to the wget directory
            site_id: id for the site
            index_state: IndexState object for tracking progress
        """
        if not directory.exists() or not directory.is_dir():
            logger.error(f"Directory not found or not a directory: {directory}")
            return

        if index_state is not None:
            index_state.set_status(IndexStatus.INDEXING)

        # Collect all files to process
        file_paths = []
        for root, _, files in os.walk(directory):
            for filename in files:
                if filename == "robots.txt":
                    continue

                rel_path = Path(root).relative_to(directory)
                ignore_file = False
                for ignore_dir in WGET_IGNORE_DIRECTORIES:
                    if ignore_dir in str(rel_path):
                        ignore_file = True
                        break

                if not ignore_file:
                    file_paths.append(Path(root) / filename)

        with closing(connection.cursor()) as cursor:
            for i in range(0, len(file_paths), INDEXED_BATCH_SIZE):
                if index_state is not None and index_state.is_timeout():
                    index_state.set_status(IndexStatus.PARTIAL)
                    return
                batch_paths = file_paths[i:i+INDEXED_BATCH_SIZE]
                file_contents = BaseManager.read_files(batch_paths)
                batch_insert_data = []

                for file_path in batch_paths:
                    try:
                        record = self._prepare_wget_record(file_path, site_id, directory, file_contents.get(file_path))
                        if record:
                            batch_insert_data.append(record)
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

            if index_state is not None and index_state.status == IndexStatus.INDEXING:
                index_state.set_status(IndexStatus.COMPLETE)

    def _prepare_wget_record(self, file_path: Path, site_id: int, base_dir: Path, content: str = None) -> tuple | None:
        """
        Prepare a record for batch insertion from a wget file.

        Args:
            file_path: Path to the wget file
            site_id: id for the site
            base_dir: Base directory for the wget capture
            content: Optional pre-loaded file content

        Returns:
            Tuple of values ready for insertion, or None if processing fails
        """
        try:
            # generate relative url path from file path
            relative_path = file_path.relative_to(base_dir)
            url = f"{INDEXED_RESOURCE_DEFAULT_PROTOCOL}{base_dir.name}/{str(relative_path).replace(os.sep, '/')}"

            # clean up the file path - strip wget artifacts
            decruftified_path = BaseManager.decruft_path(str(file_path))

            # get the final extension for type mapping
            extension = Path(decruftified_path).suffix.lower()
            resource_type = INDEXED_TYPE_MAPPING.get(extension, ResourceResultType.OTHER)

            # get file stats
            stat = file_path.stat()
            file_size = stat.st_size

            # Use pre-loaded content if available, otherwise rely on read_file_contents
            file_content = content
            if file_content is None:
                file_content = BaseManager.read_file_contents(file_path, resource_type)

            return (
                BaseManager.string_to_id(url),
                site_id,
                url,
                resource_type.value,
                200,
                BaseManager.get_basic_headers(file_size, resource_type),
                file_content,
                file_size,
                0
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
    List wget directories in the datasrc directory as sites.

    Args:
        datasrc: Path to the directory containing wget captures
        ids: Optional list of site ids to filter by
        fields: List of fields to include in the response

    Returns:
        List of SiteResult objects, one for each wget directory
    """
    assert datasrc is not None, f"datasrc not provided ({datasrc})"

    if not datasrc.exists():
        logger.error(f"Directory not found ({datasrc})")
        return []

    selected_fields: set[str] = set(SITES_FIELDS_REQUIRED)
    if fields:
        valid_fields: set[str] = set(SITES_FIELDS_DEFAULT)
        selected_fields.update(f for f in fields if f in valid_fields)
    else:
        selected_fields.update(SITES_FIELDS_DEFAULT)

    results: list[SiteResult] = []
    site_dirs = [d for d in datasrc.iterdir() if d.is_dir() and not d.name.startswith(".") and d.name not in WGET_IGNORE_DIRECTORIES]

    dir_id_map: dict[int, Path] = {WgetManager.string_to_id(d.name): d for d in site_dirs}

    if ids:
        dir_id_map = {id_val: path for id_val, path in dir_id_map.items() if id_val in ids}

    # process each directory
    for site_id, dir_path in sorted(dir_id_map.items()):
        dir_stat = dir_path.stat()
        created_time: datetime = datetime.fromtimestamp(dir_stat.st_ctime)
        modified_time: datetime = datetime.fromtimestamp(dir_stat.st_mtime)
        robots_content = None
        robots_path = dir_path / "robots.txt"
        if robots_path.exists():
            try:
                with open(robots_path, "r", encoding="utf-8") as f:
                    robots_content = f.read()
            except Exception as e:
                logger.error(f"Error reading robots.txt from {robots_path}: {e}")

        site = SiteResult(
            id=site_id,
            url=f"{INDEXED_RESOURCE_DEFAULT_PROTOCOL}{dir_path.name}/",
            created=created_time if "created" in selected_fields else None,
            modified=modified_time if "modified" in selected_fields else None,
            robots=robots_content
        )

        results.append(site)

    return results

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


def get_resources_with_manager(
    crawl_manager: BaseManager,
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
    Get resources from directories using in-memory SQLite with the specified manager.

    Args:
        crawl_manager: BaseManager instance used for file indexing and database access
        datasrc: Path to the directory containing site captures
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

    Notes:
        Returns empty results if sites is empty or not provided.
        If the database is being built, it will log a message and return empty results.
    """
    null_result: tuple[list[ResourceResult], int, IndexState | None] = [], 0, None


    if not sites or len(sites) == 0:
        return null_result

    site_results = get_sites(datasrc, ids=sites)
    if not site_results:
        return null_result

    site_paths = [Path(datasrc) / site.url.split("/")[-2] for site in site_results]
    sites_group = SitesGroup(sites, site_paths)
    connection: sqlite3.Connection
    connection_index_state: IndexState
    connection, connection_index_state = crawl_manager.get_connection(sites_group)

    if connection is None:
        # database is currently being built
        logger.info(f"Database for sites {sites} is currently being built, try again later")
        return null_result

    limit = min(max(1, limit), RESOURCES_LIMIT_MAX)
    selected_fields: set[str] = set(RESOURCES_FIELDS_REQUIRED)
    if fields:
        selected_fields.update(f for f in fields if f in RESOURCES_DEFAULT_FIELD_MAPPING)

    # convert to qualified field names
    qualified_fields: list[str] = [RESOURCES_DEFAULT_FIELD_MAPPING[f] for f in selected_fields]
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
        params.update({f"status{i}": status_val for i, status_val in enumerate(statuses)})

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
            rows = cursor.fetchall()

            if rows:
                column_names = [description[0].lower() for description in cursor.description]
                for row in rows:
                    row_dict = {column_names[i]: row[i] for i in range(len(column_names))}
                    type_value = row_dict.get("type", "")
                    resource_type = ResourceResultType.UNDEFINED

                    # Map the type string back to enum
                    for rt in ResourceResultType:
                        if rt.value == type_value:
                            resource_type = rt
                            break

                    result = ResourceResult(
                        id=row_dict.get("id"),
                        site=row_dict.get("project"),
                        url=row_dict.get("url", ""),
                        type=resource_type,
                        name=row_dict.get("name"),
                        headers=row_dict.get("headers"),
                        content=row_dict.get("content") if "content" in selected_fields else None,
                        status=row_dict.get("status"),
                        size=row_dict.get("size"),
                        time=row_dict.get("time"),
                        metadata=None,  # Not implemented for wget
                    )

                    results.append(result)

            # get total count
            if len(results) < limit:
                total_count = offset + len(results)
            else:
                count_statement = f"SELECT COUNT(*) as total FROM ResourcesFullText{where_clause}"
                cursor.execute(count_statement, params)
                count_row = cursor.fetchone()
                total_count = count_row[0] if count_row else 0

    except sqlite3.Error as e:
        logger.error(f"SQLite error in wget adapter: {e}")
        return null_result

    return results, total_count, connection_index_state

