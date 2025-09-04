import os
import re
import sqlite3
import traceback

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from mcp_server_webcrawl.crawlers.base.adapter import (
    BaseManager,
    IndexState,
    IndexStatus,
    SitesGroup,
    INDEXED_BATCH_SIZE,
    INDEXED_RESOURCE_DEFAULT_PROTOCOL,
    INDEXED_TYPE_MAPPING
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

HTTRACK_REGEX_LAUNCH_URL = re.compile(r"launched on .+ at (https?://[^\s]+)")
HTTRACK_REGEX_REDIRECT = re.compile(r"File has moved from (https?://[^\s]+) to (.+)")
HTTRACK_REGEX_ERROR = re.compile(r'"([^"]+)" \((\d+)\) at link (https?://[^\s]+)')
HTTRACK_REGEX_DOMAIN = re.compile(r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$')
HTTRACK_REGEX_INDEX_HTML = re.compile(r"/index\.html($|\?)")

logger = get_logger()

class HtTrackManager(IndexedManager):
    """
    Manages HTTrack project data in in-memory SQLite databases.
    """

    def __init__(self) -> None:
        """
        Initialize the HTTrack manager with empty cache and statistics.
        """
        super().__init__()

    def _load_site_data(self, connection: sqlite3.Connection, project_directory: Path,
                       site_id: int, index_state: IndexState = None) -> None:
        """
        Load an HTTrack project directory into the database.

        Args:
            connection: SQLite connection
            project_dir: path to the HTTrack project directory
            site_id: ID for the site
            index_state: IndexState object for tracking progress
        """
        if not project_directory.exists() or not project_directory.is_dir():
            logger.error(f"Directory not found or not a directory: {project_directory}")
            return

        if index_state is not None:
            index_state.set_status(IndexStatus.INDEXING)

        # metadata from hts-log.txt
        project_metadata = self._get_project_metadata(project_directory)

        # domain directories discovery
        domain_directories = self._get_content_directories(project_directory)

        if not domain_directories:
            logger.warning(f"No domain directories found in HTTrack project: {project_directory}")
            return

        httrack_skip_files_lower = ["hts-log.txt", "index.html"]
        with closing(connection.cursor()) as cursor:
            for domain_directory in domain_directories:
                base_url = self._get_base_url(domain_directory, project_metadata)
                file_paths = []
                for root, _, files in os.walk(domain_directory):
                    for filename in files:
                        file_path = Path(root) / filename

                        if filename.lower() in httrack_skip_files_lower and file_path.parent == project_directory:
                            continue
                        file_paths.append(file_path)

                # batch process
                for i in range(0, len(file_paths), INDEXED_BATCH_SIZE):
                    if index_state is not None and index_state.is_timeout():
                        index_state.set_status(IndexStatus.PARTIAL)
                        return

                    batch_file_paths = file_paths[i:i+INDEXED_BATCH_SIZE]
                    batch_file_contents = BaseManager.read_files(batch_file_paths)
                    batch_insert_resource_results = []

                    for file_path in batch_file_paths:
                        content = batch_file_contents.get(file_path)
                        try:
                            result = self._create_resource(
                                file_path, site_id, domain_directory, base_url,
                                project_metadata, content
                            )
                            if result:
                                batch_insert_resource_results.append(result)
                                if index_state is not None:
                                    index_state.increment_processed()
                        except Exception as ex:
                            logger.error(f"Error processing file {file_path}: {ex}")

                    self._execute_batch_insert(connection, cursor, batch_insert_resource_results)

            if index_state is not None and index_state.status == IndexStatus.INDEXING:
                index_state.set_status(IndexStatus.COMPLETE)

    def _create_resource(self, file_path: Path, site_id: int, domain_directory: Path,
                             base_url: str, project_metadata: dict, content: str = None) -> ResourceResult | None:
        """
        Create ResourceResult for an HTTrack file.

        Args:
            file_path: path to the file
            site_id: ID for the site
            domain_dir: path to the domain directory
            base_url: reconstructed base URL for the domain
            project_metadata: extracted project metadata
            content: optional pre-loaded file content

        Returns:
            ResourceResult object ready for insertion, or None if processing fails
        """
        try:
            relative_path: Path = file_path.relative_to(domain_directory)
            url = base_url + str(relative_path).replace(os.sep, "/")

            # Handle homepage index.html like wget does
            url = HTTRACK_REGEX_INDEX_HTML.sub(r"/\1", url)

            # Determine resource type from file extension
            extension = file_path.suffix.lower()
            resource_type = INDEXED_TYPE_MAPPING.get(extension, ResourceResultType.OTHER)

            # Get file metadata
            if file_path.is_file():
                file_stat = file_path.stat()
                file_size = file_stat.st_size
                file_created = datetime.fromtimestamp(file_stat.st_ctime, tz=timezone.utc)
                file_modified = datetime.fromtimestamp(file_stat.st_mtime, tz=timezone.utc)
            else:
                file_created = None
                file_modified = None
                file_size = 0

            status_code = 200  # Default for files that exist
            errors = project_metadata.get("errors", {})
            redirects = project_metadata.get("redirects", {})

            if url in errors:
                status_code = errors[url]
            elif url in redirects:
                status_code = 302  # Assume redirect

            # pre-loaded content if available
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
                status=status_code,
                headers=BaseManager.get_basic_headers(file_size, resource_type, file_path),
                content=file_content,
                size=file_size,
                time=0  # data unavailable (HTTrack)
            )

        except Exception as ex:
            logger.error(f"Error creating resource for file {file_path}: {ex}\n{traceback.format_exc()}")
            return None

    def _get_project_metadata(self, project_directory: Path) -> dict[str, str]:
        """
        Get metadata from HTTrack hts-log.txt file.

        Args:
            project_dir: path to the HTTrack project directory

        Returns:
            Dictionary containing extracted metadata (urls, launch_time, etc.)
        """
        metadata: dict = {}
        hts_log_path: Path = project_directory / "hts-log.txt"

        if not hts_log_path.exists():
            logger.warning(f"No hts-log.txt found in {project_directory}")
            return metadata

        # into fragile territory, if in doubt follow latest official HTTrack
        try:
            with open(hts_log_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

                # extract primary network domain (http) from first line
                launch_match = HTTRACK_REGEX_LAUNCH_URL.search(content)
                if launch_match:
                    metadata["launch_url"] = launch_match.group(1)

                redirects = {}
                errors = {}

                for line in content.split("\n"):
                    line = line.strip()

                    # redirects - file has moved from X to Y
                    redirect_match = HTTRACK_REGEX_REDIRECT.search(line)
                    if redirect_match:
                        redirects[redirect_match.group(1)] = redirect_match.group(2)

                    # errors - Not Found (404) at link X
                    error_match = HTTRACK_REGEX_ERROR.search(line)
                    if error_match:
                        error_text, status_code, url = error_match.groups()
                        errors[url] = int(status_code)

                metadata["redirects"] = redirects
                metadata["errors"] = errors

        except (FileNotFoundError, PermissionError, UnicodeDecodeError) as ex:
            logger.warning(f"Could not read hts-log.txt from {project_directory}: {ex}")
        except Exception as ex:
            logger.error(f"Error parsing hts-log.txt from {project_directory}: {ex}")

        return metadata

    def _get_content_directories(self, project_directory: Path) -> list[Path]:
        """
        Get domain directories within an HTTrack project.

        Args:
            project_dir: path to the HTTrack project directory

        Returns:
            List of domain directory paths
        """
        content_directories: list[Path] = []

        for item in project_directory.iterdir():
            if (item.is_dir() and
                not item.name.startswith(".") and
                item.name not in ["hts-cache", "hts-tmp"] and
                not item.name.startswith("hts-")):

                # if directory contains web content (has HTML, CSS, JS, or image files)
                has_web_content = any(
                    file_path.suffix.lower() in [".html", ".htm", ".css", ".js", ".png", ".jpg", ".gif"]
                    for file_path in item.rglob("*") if file_path.is_file()
                )

                if has_web_content:
                    content_directories.append(item)

        return content_directories

    def _get_base_url(self, domain_directory: Path, project_metadata: dict) -> str:
        """
        Get the base URL for a domain directory.

        Args:
            domain_dir: path to the domain directory
            project_metadata: extracted project metadata

        Returns:
            Reconstructed base URL
        """
        #  use launch URL if match
        if "launch_url" in project_metadata:
            launch_url = project_metadata["launch_url"]
            try:
                from urllib.parse import urlparse
                parsed = urlparse(launch_url)
                if parsed.netloc.replace("www.", "") == domain_directory.name.replace("www.", ""):
                    return f"{parsed.scheme}://{parsed.netloc}/"
            except Exception:
                pass

        # if domain_directory name looks like a domain
        if HTTRACK_REGEX_DOMAIN.match(domain_directory.name):
            return f"{INDEXED_RESOURCE_DEFAULT_PROTOCOL}{domain_directory.name}/"

        # fallback
        project_name = domain_directory.parent.name
        logger.warning(f"Could not determine domain for {domain_directory}, using fallback: {project_name}")
        return f"{INDEXED_RESOURCE_DEFAULT_PROTOCOL}{project_name}.local/{domain_directory.name}/"

manager: HtTrackManager = HtTrackManager()

def get_sites(
    datasrc: Path,
    ids: list[int] | None = None,
    fields: list[str] | None = None
) -> list[SiteResult]:
    """
    List HTTrack project directories as sites.

    Args:
        datasrc: path to the directory containing HTTrack projects
        ids: optional list of site IDs to filter by
        fields: optional list of fields to include in the response

    Returns:
        List of SiteResult objects, one for each HTTrack project
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
    Get resources from HTTrack project directories using in-memory SQLite.

    Args:
        datasrc: path to the directory containing HTTrack projects
        sites: optional list of site IDs to filter by
        query: search query string
        fields: optional list of fields to include in response
        sort: sort order for results
        limit: maximum number of results to return
        offset: number of results to skip for pagination

    Returns:
        Tuple of (list of ResourceResult objects, total count, IndexState)
    """
    sites_results: list[SiteResult] = get_sites(datasrc=datasrc, ids=sites)
    assert sites_results, "At least one site is required to search"
    site_paths = [site.path for site in sites_results]
    sites_group = SitesGroup(datasrc, sites, site_paths)
    return manager.get_resources_for_sites_group(sites_group, query, fields, sort, limit, offset)
