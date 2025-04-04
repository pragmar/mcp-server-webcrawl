import hashlib
import os
import re
import sqlite3
import mimetypes

from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any, Final, Optional, Set, Tuple

from mcp_server_webcrawl.crawlers.base.adapter import BaseManager, SitesGroup
from mcp_server_webcrawl.utils.logger import get_logger
from mcp_server_webcrawl.models.resources import (
    ResourceResult,
    ResourceResultType,
    RESOURCES_FIELDS_REQUIRED,
    RESOURCES_LIMIT_DEFAULT,
    RESOURCES_LIMIT_MAX,    
)
from mcp_server_webcrawl.models.sites import (
    SiteResult,
    SITES_FIELDS_DEFAULT,
    SITES_FIELDS_REQUIRED,    
)
from mcp_server_webcrawl.crawlers.base.indexed import (
    INDEXED_RESOURCE_FIELD_MAPPING,
    INDEXED_SORT_MAPPING,
    INDEXED_TYPE_MAPPING,
)

# field mappings similar to other adapters
WGET_RESOURCE_FIELD_MAPPING: Final[dict[str, str]] = INDEXED_RESOURCE_FIELD_MAPPING
WGET_SORT_MAPPING: Final[dict[str, Tuple[str, str]]] = INDEXED_SORT_MAPPING
WGET_TYPE_MAPPING = INDEXED_TYPE_MAPPING

logger = get_logger()

class WgetManager(BaseManager):
    """
    Manages wget directory data in in-memory SQLite databases.
    Provides connection pooling and caching for efficient access.
    """
    
    def __init__(self) -> None:
        """Initialize the wget manager with empty cache and statistics."""
        super().__init__()
        
    def _load_site_data(self, connection: sqlite3.Connection, directory: Path, site_id: int) -> None:
        """
        Load a wget directory into the database.
        
        Args:
            connection: SQLite connection
            directory: Path to the wget directory
            site_id: id for the site
        """
        with closing(connection.cursor()) as cursor:
            for root, _, files in os.walk(directory):
                for filename in files:
                    if filename == "robots.txt":
                        continue
                    file_path = Path(root) / filename
                    self._process_wget_file(cursor, file_path, site_id, directory)
            connection.commit()

    def _process_wget_file(self, cursor: sqlite3.Cursor, file_path: Path, site_id: int, base_dir: Path) -> None:
        """
        Process a single wget file and insert it into the database.
        
        Args:
            cursor: SQLite cursor
            file_path: Path to the wget file
            site_id: id for the site
            base_dir: Base directory for the wget capture
        """
        # generate relative url path from file path
        relative_path = file_path.relative_to(base_dir)
        url = f"http://{base_dir.name}/{str(relative_path).replace(os.sep, '/')}"
        # generate stable id from url
        file_id = int(hashlib.sha1(url.encode()).hexdigest()[:8], 16)
    
        # clean up the file path - strip wget artifacts
        clean_path = str(file_path)
        clean_path = clean_path.lower()
        clean_path = re.sub(r"[\u00b7·]?\d+\.tmp|\d{12}|\.tmp", "", clean_path)

        # get the final extension for type mapping
        extension = Path(clean_path).suffix.lower()
        resource_type = WGET_TYPE_MAPPING.get(extension, ResourceResultType.OTHER)
    
        # get file stats
        stat = file_path.stat()
        file_size = stat.st_size
    
        # read content for text files
        content = None
        if resource_type in [ResourceResultType.PAGE, ResourceResultType.TEXT,
                    ResourceResultType.CSS, ResourceResultType.SCRIPT, ResourceResultType.OTHER]:
            
            # vanilla --mirror will not adjust extension (ResourceResultType.OTHER)
            # so, need to determine the old fashioned way
            mime_type, _ = mimetypes.guess_type(file_path)
            if mime_type and not mime_type.startswith("text/"):
                return
            
            if os.path.getsize(file_path) > 2_000_000:  # 2MB limit
                return

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except UnicodeDecodeError:
                logger.warning(f"Could not decode file as UTF-8: {file_path}")
                content = None
        headers: str = self._get_basic_headers(resource_type, file_size)
        cursor.execute("""
            INSERT INTO ResourcesFullText (
                Id, Project, Url, Type, Status,
                Headers, Content, Size, Time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            file_id, site_id, url,
            resource_type.value,
            200,
            headers,
            content,
            file_size,
            0
        ))
    
    def _get_basic_headers(self, res_type: ResourceResultType, file_size: int) -> str:
        content_type = {
            ResourceResultType.PAGE: "text/html",
            ResourceResultType.CSS: "text/css",
            ResourceResultType.SCRIPT: "application/javascript",
            ResourceResultType.IMAGE: "image/jpeg",  # default image type
            ResourceResultType.PDF: "application/pdf",
            ResourceResultType.TEXT: "text/plain",
            ResourceResultType.DOC: "application/msword",
            ResourceResultType.OTHER: "application/octet-stream"
        }.get(res_type, "application/octet-stream")    
        return f"HTTP/1.0 200 OK\r\nContent-Type: {content_type}\r\nContent-Length: {file_size}\r\n\r\n"

manager: WgetManager = WgetManager()

def get_sites(
    datasrc: Path,
    ids: Optional[list[int]] = None,
    fields: Optional[list[str]] = None
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
    
    selected_fields: Set[str] = set(SITES_FIELDS_REQUIRED)
    if fields:
        valid_fields: Set[str] = set(SITES_FIELDS_DEFAULT)
        selected_fields.update(f for f in fields if f in valid_fields)
    else:
        selected_fields.update(SITES_FIELDS_DEFAULT)
    
    results: list[SiteResult] = []
    site_dirs = [d for d in datasrc.iterdir() if d.is_dir() and not d.name.startswith(".")]

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
            url=f"http://{dir_path.name}/",  # Base URL from directory name
            created=created_time if "created" in selected_fields else None,
            modified=modified_time if "modified" in selected_fields else None,
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
    
    limit = min(max(1, limit), RESOURCES_LIMIT_MAX)
    selected_fields: Set[str] = set(RESOURCES_FIELDS_REQUIRED)
    if fields:
        selected_fields.update(f for f in fields if f in WGET_RESOURCE_FIELD_MAPPING)
    
    # convert to qualified field names
    qualified_fields: list[str] = [WGET_RESOURCE_FIELD_MAPPING[f] for f in selected_fields]
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
    
    if sort in WGET_SORT_MAPPING:
        field, direction = WGET_SORT_MAPPING[sort]
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
        return [], 0
    
    return results, total_count
