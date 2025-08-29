import json
import os
import sqlite3

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from mcp_server_webcrawl.crawlers.base.adapter import (
    BaseManager,
    IndexState,
    IndexStatus,
    SitesGroup,
    INDEXED_BATCH_SIZE,
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
    SITES_FIELDS_BASE,
    SITES_FIELDS_DEFAULT,
)
from mcp_server_webcrawl.utils.logger import get_logger

logger = get_logger()

class ArchiveBoxManager(IndexedManager):
    """
    Manages ArchiveBox in-memory SQLite databases for session-level reuse.
    """

    def __init__(self) -> None:
        """
        Initialize the ArchiveBox manager with empty cache and statistics.
        """
        super().__init__()

    def _load_site_data(self, connection: sqlite3.Connection, site_directory: Path,
                       site_id: int, index_state: IndexState = None) -> None:
        """
        Load ArchiveBox site data into the database.
        
        Args:
            connection: SQLite connection
            site_directory: path to the ArchiveBox site directory (e.g., "example" or "pragmar")
            site_id: ID for the site
            index_state: IndexState object for tracking progress
        """
        # The site_directory should be something like "example" or "pragmar"
        # We need to look for the "archive" subdirectory within it
        archive_directory: Path = site_directory / "archive"

        if not archive_directory.exists() or not archive_directory.is_dir():
            logger.error(f"Archive directory not found in site: {archive_directory}")
            return

        if index_state is not None:
            index_state.set_status(IndexStatus.INDEXING)

        # page directories are timestamped (e.g. example/archive/1756357684.13023)
        # these contiain page data/media
        page_directories = self._get_page_directories(archive_directory)
        if not page_directories:
            logger.warning(f"No timestamped entries found in archive: {archive_directory}")
            return

        all_resources: list[ResourceResult] = []

        # process each timestamped entry
        for page_directory in page_directories:

            if index_state is not None and index_state.is_timeout():
                index_state.set_status(IndexStatus.PARTIAL)
                break

            try:
                metadata = self._get_page_metadata(page_directory)
                main_url: str = metadata["url"] if "url" in metadata else \
                    f"archivebox://unknown/{page_directory.name}"

                # primary resource
                main_resource = self._create_page_resource(page_directory, site_id, main_url, metadata)
                if main_resource:
                    all_resources.append(main_resource)
                    if index_state is not None:
                        index_state.increment_processed()

                # collect assets (external js/css/fonts/whatever)
                domain_assets = self._get_page_domain_assets(page_directory, main_url)
                for file_path, asset_url in domain_assets:
                    asset_resource = self._create_asset_resource(file_path, site_id, asset_url, page_directory)
                    if asset_resource:
                        all_resources.append(asset_resource)
                        if index_state is not None:
                            index_state.increment_processed()

            except Exception as ex:
                logger.error(f"Error processing entry {page_directory}: {ex}")

        deduplicated_resources = self._dedupe_resources(all_resources)
        with closing(connection.cursor()) as cursor:
            for i in range(0, len(deduplicated_resources), INDEXED_BATCH_SIZE):
                batch = deduplicated_resources[i:i+INDEXED_BATCH_SIZE]
                self._execute_batch_insert(connection, cursor, batch)

        if index_state is not None and index_state.status == IndexStatus.INDEXING:
            index_state.set_status(IndexStatus.COMPLETE)

    def _create_page_resource(self, resource_directory: Path, site_id: int,
                url: str, metadata: dict) -> ResourceResult | None:
        """
        Create ResourceResult for the main captured page.
        """
        try:

            # created/modified is directory stat
            resource_stat: os.stat_result = resource_directory.stat()
            created: datetime = datetime.fromtimestamp(resource_stat.st_ctime, tz=timezone.utc)
            modified: datetime = datetime.fromtimestamp(resource_stat.st_mtime, tz=timezone.utc)

            # read content
            html_file: Path = resource_directory / "index.html"
            content: str|None = None
            file_size: int = 0
            if html_file.exists():
                try:
                    with open(html_file, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    file_size: int = html_file.stat().st_size
                except Exception as ex:
                    logger.warning(f"Could not read HTML from {html_file}: {ex}")

            # assemble metadata
            status_code: int = 200
            headers_reconstructed: str = ""
            if "http_headers" in metadata:
                http_headers = metadata["http_headers"]
                if "status" in http_headers:
                    try:
                        status_code = int(str(http_headers["status"]).split()[0])
                    except (ValueError, IndexError):
                        pass
                headers_reconstructed = self._get_http_headers_string(http_headers)

            if not headers_reconstructed:
                headers_reconstructed = BaseManager.get_basic_headers(
                        file_size, ResourceResultType.PAGE)

            return ResourceResult(
                id=BaseManager.string_to_id(url),
                site=site_id,
                created=created,
                modified=modified,
                url=url,
                type=ResourceResultType.PAGE,
                status=status_code,
                headers=headers_reconstructed,
                content=content,
                size=file_size,
                time=0
            )

        except Exception as ex:
            logger.error(f"Error creating main resource for {resource_directory}: {ex}")
            return None

    def _create_asset_resource(self, file_path: Path, site_id: int, url: str, entry_dir: Path) -> ResourceResult | None:
        """
        Create ResourceResult for a domain asset file.
        """
        try:
            # get file info
            if not file_path.exists():
                return None

            file_stat = file_path.stat()
            created: datetime = datetime.fromtimestamp(file_stat.st_ctime, tz=timezone.utc)
            modified: datetime = datetime.fromtimestamp(file_stat.st_mtime, tz=timezone.utc)
            file_size: int = file_stat.st_size
            extension: str = file_path.suffix.lower()

            # ArchiveBox will stuff URL args into @... in the filename
            # sometimes it's the filename, sometimes the extension
            # both need cleaning
            clean_url: str = url.split("@")[0]
            clean_extension: str = extension.split("@")[0]
            resource_type: str = INDEXED_TYPE_MAPPING.get(clean_extension, ResourceResultType.OTHER)

            # read content for text files
            content: str | None = BaseManager.read_file_contents(file_path, resource_type)

            return ResourceResult(
                id=BaseManager.string_to_id(clean_url),
                site=site_id,
                created=created,
                modified=modified,
                url=clean_url,
                type=resource_type,
                status=200,  # assume assets successful
                headers=BaseManager.get_basic_headers(file_size, resource_type),
                content=content,
                size=file_size,
                time=0
            )

        except Exception as ex:
            logger.error(f"Error creating asset resource for {file_path}: {ex}")
            return None

    def _get_page_directories(self, archive_directory: Path) -> list[Path]:
        """
        Get webpage directories within ArchiveBox archive.

        Args:
            archive_directory: path to the ArchiveBox archive directory

        Returns:
            List of timestamped entry directory paths
        """

        # page_directories are the timestamped directories,
        # e.g. archive/1756342555.086082
        page_directories = []

        if not archive_directory.is_dir():
            return page_directories

        for item in archive_directory.iterdir():
            # 1756342555.086082.replace(".", "") is numeric
            if (item.is_dir() and item.name.replace(".", "").isdigit()):
                data_files: list[Path] = [
                    (item / "index.json"),
                    (item / "headers.json"),
                    (item / "index.html"),
                ]
                for data_file in data_files:
                    if data_file.exists():
                        page_directories.append(item)
                        break

        return sorted(page_directories)

    def _get_page_metadata(self, entry_directory: Path) -> dict:
        """
        Extract metadata from ArchiveBox entry files.

        Args:
            entry_directory: path to the timestamped entry directory

        Returns:
            Dictionary containing extracted metadata
        """
        page_metadata: dict[str, str] = {}

        # read index.json for primary URL and metadata
        index_json_path: Path = entry_directory / "index.json"
        if index_json_path.exists():
            try:
                with open(index_json_path, "r", encoding="utf-8", errors="replace") as f:
                    index_data = json.load(f)
                    page_metadata.update(index_data)
            except (json.JSONDecodeError, UnicodeDecodeError) as ex:
                logger.warning(f"Could not parse index.json from {entry_directory}: {ex}")
            except Exception as ex:
                logger.error(f"Error reading index.json from {entry_directory}: {ex}")

        # read headers.json for HTTP headers
        headers_json_path = entry_directory / "headers.json"
        if headers_json_path.exists():
            try:
                with open(headers_json_path, "r", encoding="utf-8", errors="replace") as f:
                    http_headers = json.load(f)
                    page_metadata["http_headers"] = http_headers
            except (json.JSONDecodeError, UnicodeDecodeError) as ex:
                logger.warning(f"Could not parse headers.json from {entry_directory}: {ex}")
            except Exception as ex:
                logger.error(f"Error reading headers.json from {entry_directory}: {ex}")

        return page_metadata

    def _get_page_domain_assets(self, entry_dir: Path, main_url: str) -> list[tuple[Path, str]]:
        """
        Collect all domain asset files within an entry.

        Args:
            entry_dir: path to the timestamped entry
            main_url: the main captured URL

        Returns:
            List of (file_path, reconstructed_url) tuples
        """
        assets: list[tuple] = []

        # skip metadata directories
        skip_directories: set[str] = {"media", "mercury"}
        collapse_filenames: list[str] = ["/index.html", "/index.htm"]

        for item in entry_dir.iterdir():
            if item.is_dir() and item.name not in skip_directories:
                # this is an archivebox domain directory
                domain_name: str = item.name

                # walk domain directories for assets
                # (e.g. example/archive/1756357684.13023/example.com)
                for root, _, files in os.walk(item):
                    for filename in files:

                        # *orig$ are dupes, not reliably in fileext form
                        if filename.endswith("orig"):
                            continue

                        file_path = Path(root) / filename

                        # clean up ArchiveBox's @timestamp suffixes for URL construction
                        clean_filename: str = filename.split("@")[0]
                        clean_file_path: Path = Path(root) / clean_filename
                        relative_path = clean_file_path.relative_to(item)
                        url = f"https://{domain_name}/{str(relative_path).replace(os.sep, '/')}"
                        for collapse_filename in collapse_filenames:
                            # turn ./index.html and variants into ./ (dir index) to help the indexer
                            if url.endswith(collapse_filename):
                                url = url[:-(len(collapse_filename))]
                                break

                        # Use original file_path for reading, clean url for storage
                        assets.append((file_path, url))

        return assets

    def _dedupe_resources(self, resources: list[ResourceResult]) -> list[ResourceResult]:
        """
        Deduplicate resources based on URL and metadata

        Args:
            resources: list of ResourceResult objects

        Returns:
            Deduplicated list of ResourceResult objects
        """
        seen_urls: dict[str, ResourceResult] = {}
        deduplicated: list[ResourceResult] = []
        resource: ResourceResult
        for resource in resources:
            if resource.url in seen_urls:
                # url collision, check if content differs, prefer newer
                existing = seen_urls[resource.url]
                if resource.modified and existing.modified:
                    if resource.modified > existing.modified:
                        deduplicated = [r for r in deduplicated if r.url != resource.url]
                        deduplicated.append(resource)
                        seen_urls[resource.url] = resource
            else:
                # keep existing
                seen_urls[resource.url] = resource
                deduplicated.append(resource)

        return deduplicated

    def _get_http_headers_string(self, http_headers: dict) -> str:
        """
        Format headers dictionary as HTTP headers string.
        """
        if not http_headers:
            return ""

        headers_lines: list[str] = []
        status: int = http_headers.get("Status-Code", 200)
        headers_lines.append(f"HTTP/1.0 {status}")

        for key, value in http_headers.items():
            if key.lower() not in ["status-code"]:
                headers_lines.append(f"{key}: {value}")

        return "\r\n".join(headers_lines) + "\r\n\r\n"


manager: ArchiveBoxManager = ArchiveBoxManager()

def get_sites(
    datasrc: Path,
    ids: list[int] | None = None,
    fields: list[str] | None = None
) -> list[SiteResult]:
    """
    List ArchiveBox instances as separate sites.
    Each subdirectory of datasrc that contains an "archive" folder is treated as a separate ArchiveBox instance.

    Args:
        datasrc: path to the directory containing ArchiveBox instance directories
        ids: optional list of site IDs to filter by
        fields: optional list of fields to include in the response

    Returns:
        List of SiteResult objects, one for each ArchiveBox instance
    """
    assert datasrc is not None, f"datasrc not provided ({datasrc})"

    if not datasrc.exists():
        logger.error(f"Directory not found ({datasrc})")
        return []

    # determine which fields to include
    selected_fields: set[str] = set(SITES_FIELDS_BASE)
    if fields:
        valid_fields: set[str] = set(SITES_FIELDS_DEFAULT)
        selected_fields.update(f for f in fields if f in valid_fields)
    else:
        selected_fields.update(SITES_FIELDS_DEFAULT)

    results: list[SiteResult] = []

    # get all directories that contain an "archive" subdirectory
    site_directories: list[Path] = []
    for datasrc_item in datasrc.iterdir():
        if (
                datasrc_item.is_dir() and
                not datasrc_item.name.startswith(".") and
                datasrc_item.name not in INDEXED_IGNORE_DIRECTORIES and
                (datasrc_item / "archive").is_dir()
            ):
            site_directories.append(datasrc_item)

    # map directory IDs to paths for filtering
    site_directories_map: dict[int, Path] = {BaseManager.string_to_id(d.name): d for d in site_directories}

    if ids:
        site_directories_map = {id_val: path for id_val, path in site_directories_map.items() if id_val in ids}

    # process each ArchiveBox instance directory
    for site_id, site_directory in sorted(site_directories_map.items()):
        site_directory_stat = site_directory.stat()
        created_time: datetime = datetime.fromtimestamp(site_directory_stat.st_ctime)
        modified_time: datetime = datetime.fromtimestamp(site_directory_stat.st_mtime)

        site = SiteResult(
            path=site_directory,
            id=site_id,
            url=f"archivebox://{site_directory.name}/",
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
    Get resources from ArchiveBox instances using in-memory SQLite.

    Args:
        datasrc: path to the directory containing ArchiveBox instance directories
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

    # use the actual site directories as paths (e.g., "example", "pragmar")
    site_paths = [site.path for site in sites_results]
    sites_group = SitesGroup(datasrc, sites or [site.id for site in sites_results], site_paths)

    return manager.get_resources_for_sites_group(sites_group, query, fields, sort, limit, offset)
