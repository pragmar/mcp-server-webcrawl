import re
import sqlite3
import traceback

from contextlib import closing
from datetime import datetime
from logging import Logger
from pathlib import Path
from typing import Any, Optional, Tuple

from mcp_server_webcrawl.models.sites import SiteResult
from mcp_server_webcrawl.models.resources import ResourceResult, ResourceResultType
from mcp_server_webcrawl.utils.logger import get_logger
from mcp_server_webcrawl.models.resources import (
    RESOURCES_LIMIT_DEFAULT,
    RESOURCES_LIMIT_MAX, 
    RESOURCES_FIELDS_REQUIRED,
)

INTERROBOT_RESOURCE_FIELD_MAPPING = {
    "id": "ResourcesFullText.Id",
    "site": "ResourcesFullText.Project",
    "created": "Resources.Created",
    "modified": "Resources.Modified",
    "url": "ResourcesFullText.Url",
    "name": "ResourcesFullText.Name",
    "status": "ResourcesFullText.Status",
    "size": "Resources.Size",
    "type": "ResourcesFullText.Type",
    "headers": "ResourcesFullText.Headers",
    "content": "ResourcesFullText.Content",
    "time": "ResourcesFullText.Time"
}

INTERROBOT_SITE_FIELD_REQUIRED = set(["id", "url"])
INTERROBOT_SITE_FIELD_MAPPING = {
    "id": "Project.Id",
    "url": "Project.Url",
    "created": "Project.Created",
    "modified": "Project.Modified",
    "robots": "Project.RobotsText",
}

INTERROBOT_SORT_MAPPING = {
    "+id": ("ResourcesFullText.Id", "ASC"),
    "-id": ("ResourcesFullText.Id", "DESC"),
    "+url": ("ResourcesFullText.Url", "ASC"),
    "-url": ("ResourcesFullText.Url", "DESC"),
    "+status": ("ResourcesFullText.Status", "ASC"),
    "-status": ("ResourcesFullText.Status", "DESC"),
    "?": ("ResourcesFullText.Id", "?"),
}

INTERROBOT_TYPE_MAPPING = {
    0: ResourceResultType.UNDEFINED,
    1: ResourceResultType.PAGE,
    2: ResourceResultType.OTHER,  # Fixed
    3: ResourceResultType.FEED,
    4: ResourceResultType.FRAME,
    5: ResourceResultType.OTHER,  # External
    6: ResourceResultType.IMAGE,
    7: ResourceResultType.AUDIO,
    8: ResourceResultType.VIDEO,
    9: ResourceResultType.FONT,
    10: ResourceResultType.CSS,
    11: ResourceResultType.SCRIPT,
    12: ResourceResultType.OTHER,  # Blob
    13: ResourceResultType.TEXT,
    14: ResourceResultType.PDF,
    15: ResourceResultType.DOC
}

INTERROBOT_TYPE_TO_KEY = {
    ResourceResultType.UNDEFINED: "",
    ResourceResultType.PAGE: "html",
    ResourceResultType.FRAME: "iframe",
    ResourceResultType.IMAGE: "img",
    ResourceResultType.AUDIO: "audio",
    ResourceResultType.VIDEO: "video",
    ResourceResultType.FONT: "font",
    ResourceResultType.CSS: "style",
    ResourceResultType.SCRIPT: "script",
    ResourceResultType.FEED: "rss",
    ResourceResultType.TEXT: "text",
    ResourceResultType.PDF: "pdf",
    ResourceResultType.DOC: "doc",
    ResourceResultType.OTHER: "other"
}

INTERROBOT_TYPE_TO_INT = {v: k for k, v in INTERROBOT_TYPE_MAPPING.items()}

logger: Logger = get_logger()

def iso_to_datetime(dt_string: Optional[str]) -> datetime:
    """
    Convert ISO string to datetime.
    
    python<=3.10 struggles with zulu and fractions of seconds, will
    throw. smooth out the iso string, second precision isn't key here
    """

    if not dt_string:
        return None
    dt_string = dt_string.replace('Z', '+00:00')
    match = re.match(r"(.*\.\d{6})\d*([-+]\d{2}:\d{2}|$)", dt_string)
    if match:
        dt_string = match.group(1) + (match.group(2) or '')
    return datetime.fromisoformat(dt_string)


def get_sites(datasrc: Path, ids=None, fields=None) -> list[SiteResult]:
    """
    Get sites based on the provided parameters.

    Args:
        datasrc: Path to the database
        ids: Optional list of site IDs
        fields: List of fields to include in response

    Returns:
        List of SiteResult objects
    """

    site_fields_required: list[str] = ["id", "url"]
    site_fields_default: list[str] = site_fields_required + ["created", "modified"]
    site_fields_available: list[str] = list(INTERROBOT_SITE_FIELD_MAPPING.keys())

    # field selection
    selected_fields = set(site_fields_required)
    if fields and isinstance(fields, list):
        selected_fields.update(f for f in fields if f in site_fields_available)
    else:
        selected_fields.update(site_fields_default)

    # convert to qualified field names
    qualified_fields = [INTERROBOT_SITE_FIELD_MAPPING[f] for f in selected_fields]
    fields_joined: str = ", ".join(qualified_fields)

    # build query components
    params: dict[str, Any] = {}
    ids_clause: str = ""

    # handle id filtering
    if ids and isinstance(ids, list) and len(ids) > 0:
        placeholders: list[str] = [f":id{i}" for i in range(len(ids))]
        ids_clause: str = f" WHERE Project.Id IN ({','.join(placeholders)})"
        params.update({f"id{i}": id_val for i, id_val in enumerate(ids)})

    # build and execute query
    statement: str = f"SELECT {fields_joined} FROM Projects AS Project{ids_clause} ORDER BY Project.Url ASC"
    dict_results: dict = __sql(datasrc, statement, params)

    results: list[SiteResult] = []
    for row in dict_results:
        result = SiteResult(
            id=row.get("id"),
            url=row.get("url", ""),
            created=iso_to_datetime(row.get('created')),
            modified=iso_to_datetime(row.get('modified')),
            robots=row.get("robotstext"),
            metadata=None,
        )

        results.append(result)

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
    Get resources based on the provided parameters.

    Args (all query/WHERE args ANDed):
        datasrc: Path to the database
        ids: Optional list of resource IDs
        site: Optional project ID to filter by site
        query: Search query string for FTS5 search
        types: Optional filter for specific resource types
        fields: List of fields to include in response
        statuses: List of HTTP statuses to include in response
        sort: Sort order for results
        limit: Maximum number of results to return
        offset: Number of results to skip for pagination

    Returns:
        Tuple containing:
            - List of ResourceResult objects
            - Total count of matching resources
    """

    params: dict[str, Any] = {}
    where_clauses: list[str] = []
    from_clause = "ResourcesFullText LEFT JOIN Resources ON ResourcesFullText.Id = Resources.Id"

    # process field selection
    select_fields = set(RESOURCES_FIELDS_REQUIRED)
    if fields:
        select_fields.update(f for f in fields if f in INTERROBOT_RESOURCE_FIELD_MAPPING.keys())

    # convert model to database field names
    qualified_fields = [INTERROBOT_RESOURCE_FIELD_MAPPING[f] for f in select_fields]
    fields_joined = ", ".join(qualified_fields)

    if ids:
        placeholders = [f":id{i}" for i in range(len(ids))]
        where_clauses.append(f"ResourcesFullText.Id IN ({','.join(placeholders)})")
        params.update({f"id{i}": id_val for i, id_val in enumerate(ids)})

    if sites:
        placeholders = [f":site{i}" for i in range(len(sites))]
        where_clauses.append(f"ResourcesFullText.Project IN ({','.join(placeholders)})")
        params.update({f"site{i}": id_val for i, id_val in enumerate(sites)})

    if types:
        numeric_types = [INTERROBOT_TYPE_TO_INT[t] for t in types]
        type_placeholders = [f":type{i}" for i in range(len(numeric_types))]
        where_clauses.append(f"ResourcesFullText.Type IN ({','.join(type_placeholders)})")
        params.update({f"type{i}": type_val for i, type_val in enumerate(numeric_types)})

    if statuses:
        status_placeholders = [f":status{i}" for i in range(len(statuses))]
        where_clauses.append(f"ResourcesFullText.Status IN ({','.join(status_placeholders)})")
        params.update({f"status{i}": status_val for i, status_val in enumerate(statuses)})

    if query.strip():
        where_clauses.append("ResourcesFullText MATCH :query")
        params["query"] = query.strip()

    # construct WHERE clause
    where_clause = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    # handle sorting
    if sort in INTERROBOT_SORT_MAPPING:
        field, direction = INTERROBOT_SORT_MAPPING[sort]
        if direction == "?":
            order_clause = " ORDER BY RANDOM()"
        else:
            order_clause = f" ORDER BY {field} {direction}"
    else:
        order_clause = f" ORDER BY {INTERROBOT_RESOURCE_FIELD_MAPPING['id']} ASC"

    # add pagination
    limit: int = min(max(1, limit), RESOURCES_LIMIT_MAX)
    limit_clause = f" LIMIT {limit} OFFSET {offset}"

    # build and execute query
    statement = f"SELECT {fields_joined} FROM {from_clause}{where_clause}{order_clause}{limit_clause}"
    dict_results = __sql(datasrc, statement, params)

    # optimize count query
    if len(dict_results) < limit:
        total_count = offset + len(dict_results)
    else:
        count_statement = f"SELECT COUNT(*) as total_count FROM {from_clause}{where_clause}"
        count_results = __sql(datasrc, count_statement, params)
        total_count = count_results[0].get("total_count", 0) if count_results else 0

    results = []
    for row in dict_results:
        resource_type = INTERROBOT_TYPE_MAPPING.get(row.get("type", 0), ResourceResultType.UNDEFINED)
        result = ResourceResult(
            id=row.get("id"),
            site=row.get("project"),
            created=iso_to_datetime(row.get("created")),
            modified=iso_to_datetime(row.get("modified")),
            url=row.get("url", ""),
            crawl=None,
            type=resource_type,
            name=row.get("name"),
            headers=row.get("headers"),
            content=row.get("content"),
            status=row.get("status"),
            size=row.get("size"),
            time=row.get("time"),
            metadata=None, # reserved
        )
        results.append(result)

    return results, total_count

def __sql(datasrc: Path, statement: str, params: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    """
    Execute a SQL query against the database.
    
    Args:
        datasrc: Path to the database
        statement: SQL statement to execute
        params: Optional parameters for the SQL statement
        
    Returns:
        List of dictionaries containing the query results
    """
    
    try:
        if not statement.strip().upper().startswith("SELECT"):
            logger.error("Unauthorized SQL statement")
            raise ValueError("Only SELECT queries are permitted")

        with closing(sqlite3.connect(datasrc)) as conn:
            conn.row_factory = sqlite3.Row
            with closing(conn.cursor()) as cursor:
                cursor.execute(statement, params or {})
                return [{k.lower(): v for k, v in dict(row).items()} for row in cursor.fetchall()]

    except sqlite3.Error as ex:
        logger.error(f"SQLite error reading database: {ex}")
        return []
    except (FileNotFoundError, PermissionError) as ex:
        logger.error(f"Database access error: {datasrc}\n{traceback.format_exc()}")
        raise
    except Exception as ex:
        logger.error(f"Unexpected error reading database {datasrc}: {ex}\n{statement}\n{traceback.format_exc()}")
        raise
