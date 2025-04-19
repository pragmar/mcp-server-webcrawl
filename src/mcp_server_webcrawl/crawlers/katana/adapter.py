import re
import sqlite3

from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Set, Tuple

from mcp_server_webcrawl.crawlers.base.adapter import BaseManager, SitesGroup
from mcp_server_webcrawl.crawlers.base.indexed import (
    INDEXED_RESOURCE_FIELD_MAPPING,
    INDEXED_RESOURCE_DEFAULT_PROTOCOL,
    INDEXED_SORT_MAPPING,
)
from mcp_server_webcrawl.models.resources import (
    RESOURCES_FIELDS_REQUIRED,
    RESOURCES_LIMIT_DEFAULT,
    RESOURCES_LIMIT_MAX,
    ResourceResult,
    ResourceResultType,
)
from mcp_server_webcrawl.models.sites import (
    SITES_FIELDS_DEFAULT,
    SITES_FIELDS_REQUIRED,
    SiteResult,
)
from mcp_server_webcrawl.utils.logger import get_logger

logger = get_logger()


class KatanaManager(BaseManager):
    """
    Manages HTTP text files in in-memory SQLite databases.
    Provides connection pooling and caching for efficient access.
    """

    def __init__(self) -> None:
        """Initialize the HTTP text manager with empty cache and statistics."""
        super().__init__()

    def _load_site_data(self, connection: sqlite3.Connection, directory: Path, site_id: int) -> None:
        """
        Load a site directory of HTTP text files into the database.

        Args:
            connection: SQLite connection
            directory: Path to the site directory
            site_id: ID for the site

        Notes:
            If the directory doesn't exist or isn't a directory, an error is logged
            and the method returns without processing.
        """
        if not directory.exists() or not directory.is_dir():
            logger.error(f"Directory not found or not a directory: {directory}")
            return

        with closing(connection.cursor()) as cursor:
            for file_path in directory.glob("*.txt"):
                try:
                    self._process_http_text_file(cursor, file_path, site_id)
                except Exception as e:
                    logger.error(f"Error processing file {file_path}: {e}")

            connection.commit()

    def _process_http_text_file(self, cursor: sqlite3.Cursor, file_path: Path, site_id: int) -> None:
        """
        Process a single HTTP text file and insert it into the database.

        Args:
            cursor: SQLite cursor
            file_path: Path to the HTTP text file
            site_id: ID for the site
        """
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            return

        # crawl format: <url>\n\n<request>\n\n<headers>...<response>
        parts: list[str] = content.split("\n\n", 2)
        if len(parts) < 3:
            logger.warning(f"Invalid HTTP text format in file {file_path}")
            return

        url: str = parts[0].strip()
        # request: str = parts[1].strip()
        response_data: str = parts[2].strip()

        try:
            response_parts: list[str] = response_data.split("\n\n", 1)
            headers: str = response_parts[0].strip()
            body: str = response_parts[1].strip() if len(response_parts) > 1 else ""

            # status from the first line of headers
            status_match: str = re.search(r"HTTP/\d\.\d\s+(\d+)", headers.split("\n")[0])
            status_code: int = int(status_match.group(1)) if status_match else 0

            content_type_match = re.search(r"Content-Type:\s*([^\r\n;]+)", headers, re.IGNORECASE)
            content_type = content_type_match.group(1).strip() if content_type_match else ""
            res_type = self._determine_resource_type(content_type)
            content_size = len(body)

            cursor.execute("""
                INSERT INTO ResourcesFullText (
                    Id, Project, Url, Type, Status,
                    Headers, Content, Size, Time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                BaseManager.string_to_id(url),
                site_id,
                url,
                res_type.value,
                status_code,
                headers,
                body if self._is_text_content(content_type) else None,
                content_size,
                0  # time not available
            ))

        except Exception as e:
            logger.error(f"Error processing HTTP response in file {file_path}: {e}")

manager: KatanaManager = KatanaManager()

def get_sites(
    datasrc: Path,
    ids: Optional[list[int]] = None,
    fields: Optional[list[str]] = None
) -> list[SiteResult]:
    """
    List site directories in the datasrc directory as sites.

    Args:
        datasrc: Path to the directory containing site subdirectories
        ids: Optional list of site IDs to filter by
        fields: Optional list of fields to include in the response

    Returns:
        List of SiteResult objects, one for each site directory

    Notes:
        Returns an empty list if the datasrc directory doesn't exist.
    """
    assert datasrc is not None, f"datasrc not provided ({datasrc})"

    if not datasrc.exists():
        logger.error(f"Directory not found ({datasrc})")
        return []

    # determine which fields to include
    select_fields: Set[str] = set(SITES_FIELDS_REQUIRED)
    if fields:
        valid_fields: Set[str] = set(SITES_FIELDS_DEFAULT)
        select_fields.update(f for f in fields if f in valid_fields)
    else:
        select_fields.update(SITES_FIELDS_DEFAULT)

    results: list[SiteResult] = []

    # get all directories that contain HTTP text files
    site_dirs = [d for d in datasrc.iterdir() if d.is_dir() and not d.name.startswith(".")]

    # map directory IDs to paths for filtering
    dir_id_map: dict[int, Path] = {KatanaManager.string_to_id(d.name): d for d in site_dirs}

    if ids:
        dir_id_map = {id_val: path for id_val, path in dir_id_map.items() if id_val in ids}

    # process each directory
    for site_id, dir_path in sorted(dir_id_map.items()):
        dir_stat = dir_path.stat()
        created_time: datetime = datetime.fromtimestamp(dir_stat.st_ctime)
        modified_time: datetime = datetime.fromtimestamp(dir_stat.st_mtime)

        # check for robots.txt
        robots_content = None
        robots_files = list(dir_path.glob("*robots.txt*"))
        if robots_files:
            try:
                with open(robots_files[0], "r", encoding="utf-8", errors="replace") as f:
                    # for robots.txt files in our format, extract only the content part
                    content = f.read()
                    parts = content.split("\n\n", 2)
                    if len(parts) >= 3:
                        response_parts = parts[2].split("\n\n", 1)
                        if len(response_parts) > 1:
                            robots_content = response_parts[1]
                        else:
                            robots_content = response_parts[0]
                    else:
                        robots_content = content
            except Exception as e:
                logger.error(f"Error reading robots.txt")

        site = SiteResult(
            id=site_id,
            url=f"{INDEXED_RESOURCE_DEFAULT_PROTOCOL}{dir_path.name}/",  # base URL from directory name
            created=created_time if "created" in select_fields else None,
            modified=modified_time if "modified" in select_fields else None,
            robots=robots_content
        )

        results.append(site)

    return results


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
    get resources from HTTP text files using in-memory SQLite.

    Args:
        datasrc: Path to the directory containing site directories
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
    if not sites or len(sites) == 0:
        return [], 0

    site_results = get_sites(datasrc, ids=sites)
    if not site_results:
        return [], 0

    site_paths = [Path(datasrc) / site.url.split("/")[-2] for site in site_results]
    sites_group = SitesGroup(sites, site_paths)
    connection: sqlite3.Connection = manager.get_connection(sites_group)
    if connection is None:
        # database is currently being built
        logger.info(f"Database for sites {sites} is currently being built, try again later")
        return [], 0

    # normalize limit
    limit = min(max(1, limit), RESOURCES_LIMIT_MAX)

    # process field selection
    select_fields: Set[str] = set(RESOURCES_FIELDS_REQUIRED)
    if fields:
        select_fields.update(f for f in fields if f in INDEXED_RESOURCE_FIELD_MAPPING)

    # convert to qualified field names
    qualified_fields: list[str] = [INDEXED_RESOURCE_FIELD_MAPPING[f] for f in select_fields]
    fields_joined: str = ", ".join(qualified_fields)

    # build query components
    params: dict[str, Any] = {}
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
                    resource_type = ResourceResultType.OTHER
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
                        content=row_dict.get("content") if "content" in select_fields else None,
                        status=row_dict.get("status"),
                        size=row_dict.get("size"),
                        time=row_dict.get("time"),
                        metadata=None,  # not implemented
                    )

                    results.append(result)

            if len(results) < limit:
                total_count = offset + len(results)
            else:
                count_statement = f"SELECT COUNT(*) as total FROM ResourcesFullText{where_clause}"
                cursor.execute(count_statement, params)
                count_row = cursor.fetchone()
                total_count = count_row[0] if count_row else 0

    except sqlite3.Error as e:
        logger.error(f"SQLite error in HTTP text adapter: {e}")
        return [], 0

    return results, total_count
