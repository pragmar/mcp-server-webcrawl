from pathlib import Path
from typing import Any, Optional, Final, Tuple

from mcp.types import TextContent, ImageContent, EmbeddedResource, Tool

from mcp_server_webcrawl.models.resources import ResourceResultType, RESOURCES_FIELDS_REQUIRED
from mcp_server_webcrawl.crawlers.base.crawler import BaseCrawler
from mcp_server_webcrawl.crawlers.base.api import BaseJsonApi
from mcp_server_webcrawl.utils.tools import get_crawler_tools
from mcp_server_webcrawl.utils.logger import get_logger

logger = get_logger()

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

class IndexedCrawler(BaseCrawler):
    """
    A crawler implementation for data sources that load into an in-memory sqlite.
    Shares commonality between specialized crawlers.    
    """
    
    def __init__(self, datasrc: Path) -> None:
        """
        Initialize the IndexedCrawler with a data source path.
        
        Args:
            datasrc: Path to the data source
        """
        assert datasrc is not None, f"{self.__class__.__name__} needs a datasrc, regardless of action"
        assert datasrc.is_dir(), f"{self.__class__.__name__} datasrc must be a directory"
        super().__init__(datasrc)
        # Default resource field mapping that can be overridden by subclasses
        self.resource_field_mapping = INDEXED_RESOURCE_FIELD_MAPPING

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
        all_sites = self.get_sites(self.datasrc)
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
        raise NotImplementedError(f"{self.__class__.__name__} must implement get_sites_api")

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
        raise NotImplementedError(f"{self.__class__.__name__} must implement get_resources_api")
