from pathlib import Path
from typing import Any, Optional, Final, Tuple, Callable

from mcp.types import TextContent, ImageContent, EmbeddedResource, Tool

from mcp_server_webcrawl.models.resources import ResourceResultType, RESOURCES_FIELDS_REQUIRED
from mcp_server_webcrawl.crawlers.base.crawler import BaseCrawler
from mcp_server_webcrawl.crawlers.base.api import BaseJsonApi
from mcp_server_webcrawl.utils.tools import get_crawler_tools
from mcp_server_webcrawl.utils.logger import get_logger

from mcp_server_webcrawl.models.sites import SiteResult

logger = get_logger()

# files on disk will need default for reassembly {proto}{dir}
# these things are already approximations (perhaps) having passed through wget filtering (--adjust-extension)
# representative of the file on disk, also https is what the LLM is going to guess in all cases
INDEXED_RESOURCE_DEFAULT_PROTOCOL:str = "https://"

# Field mappings similar to other adapters
INDEXED_RESOURCE_FIELD_MAPPING: Final[dict[str, str]] = {
    "id": "Id",
    "site": "Project",
    "url": "Url",
    "name": "Name",
    "status": "Status",
    "size": "Size",
    "type": "Type",
    "headers": "Headers",
    "content": "Content",
    "time": "Time"
}

INDEXED_SORT_MAPPING: Final[dict[str, Tuple[str, str]]] = {
    "+id": ("Id", "ASC"),
    "-id": ("Id", "DESC"),
    "+url": ("Url", "ASC"),
    "-url": ("Url", "DESC"),
    "+status": ("Status", "ASC"),
    "-status": ("Status", "DESC"),
    "?": ("Id", "RANDOM")
}

INDEXED_MANAGER_CACHE_MAX = 20

# Content type to ResourceResultType mapping
INDEXED_TYPE_MAPPING = {
    "": ResourceResultType.PAGE,
    ".html": ResourceResultType.PAGE,
    ".htm": ResourceResultType.PAGE,
    ".php": ResourceResultType.PAGE,
    ".asp": ResourceResultType.PAGE,
    ".aspx": ResourceResultType.PAGE,
    ".js": ResourceResultType.SCRIPT,
    ".css": ResourceResultType.CSS,
    ".jpg": ResourceResultType.IMAGE,
    ".jpeg": ResourceResultType.IMAGE,
    ".png": ResourceResultType.IMAGE,
    ".gif": ResourceResultType.IMAGE,
    ".svg": ResourceResultType.IMAGE,
    ".pdf": ResourceResultType.PDF,
    ".txt": ResourceResultType.TEXT,
    ".xml": ResourceResultType.TEXT,
    ".json": ResourceResultType.TEXT,
    ".doc": ResourceResultType.DOC,
    ".docx": ResourceResultType.DOC
}

INDEXED_BINARY_EXTENSIONS = (
    ".woff",".woff2",".ttf",".otf",".eot",
    ".jpeg",".jpg",".png",".webp",".gif",".bmp",".tiff",".tif",".svg",".ico",".heic",".heif",
    ".mp3",".wav",".ogg",".flac",".aac",".m4a",".wma",
    ".mp4",".webm",".avi",".mov",".wmv",".mkv",".flv",".m4v",".mpg",".mpeg",
    ".pdf",".doc",".docx",".xls",".xlsx",".ppt",".pptx",
    ".zip",".rar",".7z",".tar",".gz",".bz2",".xz",
    ".exe",".dll",".so",".dylib",".bin",".apk",".app",
    ".swf",".dat",".db",".sqlite",".class",".pyc",".o"
)

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
        resource_field_mapping: dict[str, str] = INDEXED_RESOURCE_FIELD_MAPPING
    ) -> None:
        """
        Initialize the IndexedCrawler with a data source path and required adapter functions.
        
        Args:
            datasrc: Path to the data source
            get_sites_func: Function to retrieve sites from the data source
            get_resources_func: Function to retrieve resources from the data source
            resource_field_mapping: Mapping of resource field names to display names
        """
        assert datasrc is not None, f"{self.__class__.__name__} needs a datasrc, regardless of action"
        assert datasrc.is_dir(), f"{self.__class__.__name__} datasrc must be a directory"
        assert callable(get_sites_func), f"{self.__class__.__name__} requires a callable get_sites_func"
        assert callable(get_resources_func), f"{self.__class__.__name__} requires a callable get_resources_func"
        assert isinstance(resource_field_mapping, dict), f"{self.__class__.__name__} resource_field_mapping must be a dict"
        
        super().__init__(datasrc)
        self.resource_field_mapping = resource_field_mapping
        self._indexed_get_sites = get_sites_func
        self._indexed_get_resources = get_resources_func

    async def mcp_call_tool(self, name: str, arguments: dict[str, Any] | None
        ) -> list[TextContent | ImageContent | EmbeddedResource]:
        """
        Call a tool with the given name and arguments.
        
        Args:
            name: Tool name to call
            arguments: Tool arguments
            
        Returns:
            List of content objects
        """
        # Use the base implementation which already has the common logic
        return await super().mcp_call_tool(name, arguments)

    async def mcp_list_tools(self) -> list[Tool]:
        """
        List available tools for this crawler.
        
        Returns:
            List of Tool objects
        """
        if self._indexed_get_sites is None:
            logger.error(f"_indexed_get_sites not set (function required)")
            return []

        all_sites = self._indexed_get_sites(self.datasrc)
        default_tools: list[Tool] = get_crawler_tools(sites=all_sites)
        assert len(default_tools) == 2, "expected exactly 2 Tools: sites and resources"

        default_sites_tool, default_resources_tool = default_tools
        resources_type_options = list(set(self.resource_field_mapping.keys()) - set(RESOURCES_FIELDS_REQUIRED))
        all_sites_display = ", ".join([f"{s.url} (site: {s.id})" for s in all_sites])

        drt_props = default_resources_tool.inputSchema["properties"]
        drt_props["types"]["items"]["enum"] = resources_type_options
        drt_props["sites"]["description"] = ("Optional "
            "list of project ID to filter search results to a specific site. In 95% "
            "of scenarios, you'd filter to only one site, but many site filtering is offered for "
            f"advanced search scenarios. Available sites include {all_sites_display}.")

        return [default_sites_tool, default_resources_tool]

    def get_sites_api(
            self,
            ids: Optional[list[int]] = None,
            fields: Optional[list[str]] = None,
    ) -> BaseJsonApi:
        sites = self._indexed_get_sites(self.datasrc, ids=ids, fields=fields)
        json_result = BaseJsonApi("GetProjects", {"ids": ids, "fields": fields})
        json_result.set_results(sites, len(sites), 0, len(sites))
        return json_result

    def get_resources_api(
        self,
        ids: Optional[list[int]] = None,
        sites: Optional[list[int]] = None,
        query: str = "",
        types: Optional[list[str]] = None,
        fields: Optional[list[str]] = None,
        statuses: Optional[list[int]] = None,
        sort: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> BaseJsonApi:
        # no site is specified, use the first site
        # reasoning: no idea what's in the archive directory, don't kick 
        # off high-compute index of everything, esp. not by default
        if not sites:
            all_sites = self._indexed_get_sites(self.datasrc)
            if not all_sites:
                return BaseJsonApi("GetResources", {}).set_results([], 0, 0, limit)
            sites = [all_sites[0].id]

        site_matches = self._indexed_get_sites(self.datasrc, ids=sites)
        if not site_matches:
            return BaseJsonApi("GetResources", {}).set_results([], 0, 0, limit)
        
        # convert to enums
        resource_types = self._convert_to_resource_types(types)

        results, total = self._indexed_get_resources(
            self.datasrc,
            ids=ids,
            sites=sites,
            query=query,
            types=resource_types,
            fields=fields,
            statuses=statuses,
            sort=sort,
            limit=limit,
            offset=offset
        )

        json_result = BaseJsonApi("GetResources", {
            "ids": ids,
            "sites": sites,
            "query": query,
            "types": types,
            "fields": fields,
            "statuses": statuses,
            "sort": sort,
            "limit": limit,
            "offset": offset,
        })

        json_result.set_results(results, total, offset, limit)
        return json_result
