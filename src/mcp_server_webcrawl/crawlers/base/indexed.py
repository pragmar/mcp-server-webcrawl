from pathlib import Path
from typing import Callable

from mcp.types import Tool

from mcp_server_webcrawl.crawlers.base.crawler import BaseCrawler
from mcp_server_webcrawl.models.resources import (
    RESOURCES_DEFAULT_FIELD_MAPPING,
    RESOURCES_FIELDS_REQUIRED,
)
from mcp_server_webcrawl.utils.logger import get_logger
from mcp_server_webcrawl.utils.tools import get_crawler_tools

logger = get_logger()


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
            datasrc: Path to the data source
            get_sites_func: Function to retrieve sites from the data source
            get_resources_func: Function to retrieve resources from the data source
            resource_field_mapping: Mapping of resource field names to display names
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
        resources_type_options = list(set(self._resource_field_mapping.keys()) - set(RESOURCES_FIELDS_REQUIRED))
        all_sites_display = ", ".join([f"{s.url} (site: {s.id})" for s in all_sites])

        drt_props = default_resources_tool.inputSchema["properties"]
        drt_props["types"]["items"]["enum"] = resources_type_options
        drt_props["sites"]["description"] = ("Optional "
            "list of project ID to filter search results to a specific site. In 95% "
            "of scenarios, you'd filter to only one site, but many site filtering is offered for "
            f"advanced search scenarios. Available sites include {all_sites_display}.")

        return [default_sites_tool, default_resources_tool]


