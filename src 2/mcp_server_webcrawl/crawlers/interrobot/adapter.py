import re
import sqlite3
import traceback
from contextlib import closing
from logging import Logger
from pathlib import Path
from typing import Final

from mcp_server_webcrawl.crawlers.base.adapter import IndexState, IndexStatus, BaseManager, SitesGroup
from mcp_server_webcrawl.models.resources import (
    ResourceResult,
    RESOURCES_LIMIT_DEFAULT,
)

from mcp_server_webcrawl.models.sites import SiteResult
from mcp_server_webcrawl.utils import from_isoformat_zulu
from mcp_server_webcrawl.utils.logger import get_logger

# maybe dedupe with near match RESOURCES version
INTERROBOT_RESOURCE_FIELD_MAPPING: Final[dict[str, str]] = {
    "id": "ResourcesFullText.Id",
    "site": "ResourcesFullText.Project",
    "created": "Resources.Created",
    "modified": "Resources.Modified",
    "url": "ResourcesFullText.Url",
    "status": "ResourcesFullText.Status",
    "size": "Resources.Size",
    "type": "ResourcesFullText.Type",
    "headers": "ResourcesFullText.Headers",
    "content": "ResourcesFullText.Content",
    "time": "ResourcesFullText.Time"
}

INTERROBOT_SITE_FIELD_REQUIRED: Final[set[str]] = set(["id", "url"])

# legit different from default version (extra robots)
INTERROBOT_SITE_FIELD_MAPPING: Final[dict[str, str]] = {
    "id": "Project.Id",
    "url": "Project.Url",
    "created": "Project.Created",
    "modified": "Project.Modified",
    "robots": "Project.RobotsText",
}

logger: Logger = get_logger()

class InterroBotManager(BaseManager):
    """
    Manages HTTP text files in in-memory SQLite databases.
    Provides connection pooling and caching for efficient access.
    """

    def __init__(self) -> None:
        """Initialize the HTTP text manager with empty cache and statistics."""
        super().__init__()

    def get_connection(self, group: SitesGroup) -> tuple[sqlite3.Connection | None, IndexState]:
        """
        Get database connection for sites in the group, creating if needed.

        Args:
            group: Group of sites to connect to

        Returns:
            Tuple of (SQLite connection to in-memory database with data loaded or None if building,
                     IndexState associated with this database)
        """

        index_state = IndexState()
        index_state.set_status(IndexStatus.REMOTE)
        connection: sqlite3.Connection
        try:
            # note, responsible for implementing closing() on other side
            connection = sqlite3.connect(group.datasrc)
        except sqlite3.Error as ex:
            logger.error(f"SQLite error reading database: {ex}\n{traceback.format_exc()}")
        except (FileNotFoundError, PermissionError) as ex:
            logger.error(f"Database access error: {group.datasrc}\n{traceback.format_exc()}")
            raise
        except Exception as ex:
            logger.error(f"Unexpected error reading database {group.datasrc}: {ex}\n{traceback.format_exc()}")
            raise

        return connection, index_state

manager: InterroBotManager = InterroBotManager()

def get_sites(datasrc: Path, ids=None, fields=None) -> list[SiteResult]:
    """
    Get sites based on the provided parameters.

    Args:
        datasrc: path to the database
        ids: optional list of site IDs
        fields: list of fields to include in response

    Returns:
        List of SiteResult objects
    """
    site_fields_required: list[str] = ["id", "url"]
    site_fields_default: list[str] = site_fields_required + ["created", "modified"]
    site_fields_available: list[str] = list(INTERROBOT_SITE_FIELD_MAPPING.keys())

    # build query
    params: dict[str, int | str] = {}

    # these inputs are named parameters
    ids_clause: str = ""
    if ids and isinstance(ids, list) and len(ids) > 0:
        placeholders: list[str] = [f":id{i}" for i in range(len(ids))]
        ids_clause: str = f" WHERE Project.Id IN ({','.join(placeholders)})"
        params.update({f"id{i}": id_val for i, id_val in enumerate(ids)})

    # these inputs are not parameterized
    # fields will be returned from database, if found in INTERROBOT_SITE_FIELD_MAPPING
    selected_fields = set(site_fields_required)
    if fields and isinstance(fields, list):
        selected_fields.update(f for f in fields if f in site_fields_available)
    else:
        selected_fields.update(site_fields_default)

    safe_sql_fields = [INTERROBOT_SITE_FIELD_MAPPING[f] for f in selected_fields]
    assert all(re.match(r"^[A-Za-z\.]+$", field) for field in safe_sql_fields), "Unknown or unsafe field requested"
    safe_sql_fields_joined: str = ", ".join(safe_sql_fields)

    statement: str = f"SELECT {safe_sql_fields_joined} FROM Projects AS Project{ids_clause} ORDER BY Project.Url ASC"
    sql_results: list[dict[str, int | str | None]] = []
    try:
        if not statement.strip().upper().startswith("SELECT"):
            logger.error("Unauthorized SQL statement")
            raise ValueError("Only SELECT queries are permitted")

        with closing(sqlite3.connect(datasrc)) as conn:
            conn.row_factory = sqlite3.Row
            with closing(conn.cursor()) as cursor:
                cursor.execute(statement, params or {})
                sql_results = [{k.lower(): v for k, v in dict(row).items()} for row in cursor.fetchall()]
    except sqlite3.Error as ex:
        logger.error(f"SQLite error reading database: {ex}\n{traceback.format_exc()}")
        return []
    except Exception as ex:
        logger.error(f"Database error: {ex}")
        return []

    results: list[SiteResult] = []
    for row in sql_results:
        results.append(SiteResult(
            path=datasrc,
            id=row.get("id"),
            url=row.get("url", ""),
            created=from_isoformat_zulu(row.get("created")),
            modified=from_isoformat_zulu(row.get("modified")),
            robots=row.get("robotstext"),
            metadata=None,
        ))

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

    # InterroBot uses ints in place of strings
    swap_values = {
        "type" : {
            "": 0,             # UNDEFINED
            "html": 1,         # PAGE
            "other": 2,        # OTHER (could also be 5 or 12 depending on context)
            "rss": 3,          # FEED
            "iframe": 4,       # FRAME
            "img": 6,          # IMAGE
            "audio": 7,        # AUDIO
            "video": 8,        # VIDEO
            "font": 9,         # FONT
            "style": 10,       # CSS
            "script": 11,      # SCRIPT
            "text": 13,        # TEXT
            "pdf": 14,         # PDF
            "doc": 15          # DOC
        }
    }
    return manager.get_resources_for_sites_group(sites_group, query, fields, sort, limit, offset, swap_values)
