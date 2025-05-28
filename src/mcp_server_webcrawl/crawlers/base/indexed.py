import sqlite3
import traceback

from datetime import datetime
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Callable
from mcp.types import Tool

from mcp_server_webcrawl.crawlers.base.adapter import (
    BaseManager,
    IndexState,
    IndexStatus,
    SitesGroup,
    SitesStat,
    INDEXED_MANAGER_CACHE_MAX,
    INDEXED_RESOURCE_DEFAULT_PROTOCOL,
    INDEXED_IGNORE_DIRECTORIES,
)
from mcp_server_webcrawl.crawlers.base.crawler import BaseCrawler
from mcp_server_webcrawl.models.resources import (
    ResourceResult,
    ResourceResultType,
    RESOURCES_DEFAULT_FIELD_MAPPING,
)
from mcp_server_webcrawl.models.sites import (
    SiteResult,
    SITES_FIELDS_REQUIRED,
    SITES_FIELDS_DEFAULT,
)
from mcp_server_webcrawl.utils import to_isoformat_zulu
from mcp_server_webcrawl.utils.logger import get_logger
from mcp_server_webcrawl.utils.tools import get_crawler_tools

logger = get_logger()

class IndexedManager(BaseManager):

    def __init__(self):
        super().__init__()
        self._db_cache: dict[frozenset, tuple[sqlite3.Connection, IndexState]] = {}
        self._build_locks: dict[frozenset, tuple[datetime, str]] = {}

    def get_connection(self, group: SitesGroup) -> tuple[sqlite3.Connection | None, IndexState]:
        """
        Get database connection for sites in the group, creating if needed.

        Args:
            group: group of sites to connect to

        Returns:
            Tuple of (SQLite connection to in-memory database with data loaded or None if building,
                     IndexState associated with this database)
        """
        if group.cache_key in self._build_locks:
            build_time, status = self._build_locks[group.cache_key]
            get_logger().info(f"Database for {group} is currently {status} (started at {build_time})")
            return None, IndexState()  # Return empty IndexState for building databases

        if len(self._db_cache) >= INDEXED_MANAGER_CACHE_MAX:
            logger.warning(f"Cache limit reached ({INDEXED_MANAGER_CACHE_MAX}), clearing all cached databases")
            self._db_cache.clear()

        is_cached: bool = group.cache_key in self._db_cache
        self._stats.append(SitesStat(group, is_cached))

        if not is_cached:
            index_state = IndexState()
            index_state.set_status(IndexStatus.INDEXING)
            with self._building_lock(group):
                connection: sqlite3.Connection = sqlite3.connect(":memory:", check_same_thread=False)
                self._setup_database(connection)
                for site_id, site_path in group.get_sites().items():
                    self._load_site_data(connection, Path(site_path), site_id, index_state=index_state)
                    if index_state.is_timeout():
                        index_state.set_status(IndexStatus.PARTIAL)
                        break
                if index_state is not None and index_state.status == IndexStatus.INDEXING:
                    index_state.set_status(IndexStatus.COMPLETE)
                self._db_cache[group.cache_key] = (connection, index_state)

        # returns cached or newly created connection with IndexState
        connection, index_state = self._db_cache[group.cache_key]
        return connection, index_state

    def get_sites_for_directories(
        self,
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
        assert datasrc is not None, f"datasrc not provided ({datasrc})"

        if not datasrc.exists():
            logger.error(f"Directory not found ({datasrc})")
            return []

        # determine which fields to include
        select_fields: set[str] = set(SITES_FIELDS_REQUIRED)
        if fields:
            valid_fields: set[str] = set(SITES_FIELDS_DEFAULT)
            select_fields.update(f for f in fields if f in valid_fields)
        else:
            select_fields.update(SITES_FIELDS_DEFAULT)

        results: list[SiteResult] = []

        # get all directories that contain HTTP text files
        site_directories = [d for d in datasrc.iterdir() if d.is_dir() and
            not d.name.startswith(".") and not d.name in INDEXED_IGNORE_DIRECTORIES]

        # map directory IDs to paths for filtering
        site_directories_map: dict[int, Path] = {BaseManager.string_to_id(d.name): d for d in site_directories}

        if ids:
            site_directories_map = {id_val: path for id_val, path in site_directories_map.items() if id_val in ids}

        # process each directory
        for site_id, site_directory in sorted(site_directories_map.items()):
            site_directory_stat = site_directory.stat()
            created_time: datetime = datetime.fromtimestamp(site_directory_stat.st_ctime)
            modified_time: datetime = datetime.fromtimestamp(site_directory_stat.st_mtime)

            # check for robots.txt
            robots_content = None
            robots_files = list(site_directory.glob("*robots.txt*"))
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
                path=site_directory,
                id=site_id,
                url=f"{INDEXED_RESOURCE_DEFAULT_PROTOCOL}{site_directory.name}/",  # base URL from directory name
                created=created_time if "created" in select_fields else None,
                modified=modified_time if "modified" in select_fields else None,
                robots=robots_content
            )

            results.append(site)
        return results

    @contextmanager
    def _building_lock(self, group: SitesGroup):
        """
        Context manager for database building operations.
        Sets a lock during database building and releases it when done.
        """
        try:
            self._build_locks[group.cache_key] = (datetime.now(), "building")
            yield
        except Exception as e:
            self._build_locks[group.cache_key] = (self._build_locks[group.cache_key][0], f"failed: {str(e)}")
            raise # re-raise
        finally:
            # clean up the lock
            self._build_locks.pop(group.cache_key, None)

    def _setup_database(self, connection: sqlite3.Connection) -> None:
        """
        Create the database schema for storing resource data.

        Args:
            connection: SQLite connection to set up
        """
        # store project/site (also) in fulltext, doesn't suppport >= <=,
        # and pure fts search is much faster, want to only introduce
        # Resource table sql clauses when field specified (Status,
        # Size, or Time explicitly queried)
        with closing(connection.cursor()) as cursor:
            connection.execute("PRAGMA encoding = \"UTF-8\"")
            connection.execute("PRAGMA synchronous = OFF")
            connection.execute("PRAGMA journal_mode = MEMORY")
            cursor.execute("""
            CREATE TABLE Resources (
                Id INTEGER PRIMARY KEY,
                Project INTEGER NOT NULL,
                Created TEXT,
                Modified TEXT,
                Status INTEGER NOT NULL,
                Size INTEGER NOT NULL,
                Time INTEGER NOT NULL
            )""")
            cursor.execute("""
            CREATE VIRTUAL TABLE ResourcesFullText USING fts5(
                Id,
                Project,
                Url,
                Type,
                Headers,
                Content,
                tokenize="unicode61 remove_diacritics 0 tokenchars '-_'"
            )""")

    def _execute_batch_insert(self, connection: sqlite3.Connection, cursor: sqlite3.Cursor,
        batch_records: list[ResourceResult]) -> None:
        """
        Execute batch insert of records with transaction handling.
        Inserts data into both ResourcesFullText and Resources tables.

        Args:
            connection: SQLite connection
            cursor: SQLite cursor
            batch_records: list of ResourceResult objects ready for insertion
        """
        if not batch_records:
            return

        resources_base_records = []
        resources_fts_records = []
        for resource in batch_records:
            resources_base_records.append((
                resource.id,
                resource.site,
                to_isoformat_zulu(resource.created) if resource.created else None,
                to_isoformat_zulu(resource.modified) if resource.modified else None,
                resource.status,
                resource.size if resource.size is not None else 0,
                resource.time if resource.time is not None else 0,
            ))
            resources_fts_records.append((
                resource.id,
                resource.site,
                resource.url,
                resource.type.value if resource.type else ResourceResultType.UNDEFINED.value,
                resource.headers,
                resource.content,
            ))

        try:
            connection.execute("BEGIN TRANSACTION")
            cursor.executemany("""
                INSERT INTO Resources (
                    Id, Project, Created, Modified, Status, Size, Time
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, resources_base_records)
            cursor.executemany("""
                INSERT INTO ResourcesFullText (
                    Id, Project, Url, Type, Headers, Content
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, resources_fts_records)
            connection.execute("COMMIT")

        except Exception as e:
            connection.execute("ROLLBACK")
            logger.error(f"Error during batch insert: {e}\n{traceback.format_exc()}")

class IndexedCrawler(BaseCrawler):
    """
    A crawler implementation for data sources that load into an in-memory sqlite.
    Shares commonality between specialized crawlers.
    """

    def __init__(
        self,
        datasrc: Path,
        get_sites_func: Callable,
        get_resources_func: Callable,
        resource_field_mapping: dict[str, str] = RESOURCES_DEFAULT_FIELD_MAPPING
    ) -> None:
        """
        Initialize the IndexedCrawler with a data source path and required adapter functions.

        Args:
            datasrc: path to the data source
            get_sites_func: function to retrieve sites from the data source
            get_resources_func: function to retrieve resources from the data source
            resource_field_mapping: mapping of resource field names to display names
        """

        assert datasrc.is_dir(), f"{self.__class__.__name__} datasrc must be a directory"
        super().__init__(datasrc, get_sites_func, get_resources_func, resource_field_mapping=resource_field_mapping)

    async def mcp_list_tools(self) -> list[Tool]:
        """
        List available tools for this crawler.

        Returns:
            List of Tool objects
        """
        if self._adapter_get_sites is None:
            logger.error(f"_adapter_get_sites not set (function required)")
            return []

        all_sites = self._adapter_get_sites(self._datasrc)
        default_tools: list[Tool] = get_crawler_tools(sites=all_sites)
        assert len(default_tools) == 2, "expected exactly 2 Tools: sites and resources"

        default_sites_tool, default_resources_tool = default_tools
        all_sites_display = ", ".join([f"{s.url} (site: {s.id})" for s in all_sites])
        drt_props = default_resources_tool.inputSchema["properties"]
        drt_props["sites"]["description"] = ("Optional "
            "list of project ID to filter search results to a specific site. In 95% "
            "of scenarios, you'd filter to only one site, but many site filtering is offered for "
            f"advanced search scenarios. Available sites include {all_sites_display}.")

        return [default_sites_tool, default_resources_tool]

