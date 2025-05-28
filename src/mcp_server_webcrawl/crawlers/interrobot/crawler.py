
from pathlib import Path

from mcp.types import Tool

from mcp_server_webcrawl.models.sites import SiteResult
from mcp_server_webcrawl.models.resources import (
    RESOURCES_FIELDS_DEFAULT,
    RESOURCES_FIELDS_REQUIRED,
    RESOURCES_DEFAULT_SORT_MAPPING,
)
from mcp_server_webcrawl.crawlers.base.crawler import BaseCrawler
from mcp_server_webcrawl.crawlers.interrobot.adapter import (
    get_sites,
    get_resources,
    INTERROBOT_RESOURCE_FIELD_MAPPING,
    INTERROBOT_SITE_FIELD_MAPPING,
    INTERROBOT_SITE_FIELD_REQUIRED,
)
from mcp_server_webcrawl.utils.tools import get_crawler_tools
from mcp_server_webcrawl.utils.logger import get_logger

logger = get_logger()


class InterroBotCrawler(BaseCrawler):
    """
    A crawler implementation for InterroBot data sources.
    Provides functionality for accessing and searching web content from InterroBot.
    """

    def __init__(
        self,
        datasrc: Path,
    ) -> None:
        """
        Initialize the InterroBotCrawler with a data source path and required adapter functions.

        Args:
            datasrc: Path to the data source
        """
        super().__init__(datasrc, get_sites, get_resources, resource_field_mapping=INTERROBOT_RESOURCE_FIELD_MAPPING)
        assert datasrc.is_file() and datasrc.suffix == ".db", f"{self.__class__.__name__} datasrc must be a db file"

    async def mcp_list_tools(self) -> list[Tool]:
        """
        List available tools for this crawler.

        Returns:
            List of Tool objects
        """
        # get the default crawler tools, then override necessary fields
        all_sites: list[SiteResult] = self._adapter_get_sites(self._datasrc)
        default_tools: list[Tool] = get_crawler_tools(sites=all_sites)
        assert len(default_tools) == 2, "expected exactly 2 Tools: sites and resources"

        # can replace get_crawler_tools or extend, here it is overwritten from default
        # you'd think maybe pass changes in, but no, it's better ad hoc
        default_sites_tool: Tool
        default_resources_tool: Tool
        default_sites_tool, default_resources_tool = default_tools

        # this adds InterroBot specific Robots field
        sites_field_options: list[str] = list(set(INTERROBOT_SITE_FIELD_MAPPING.keys()) - set(INTERROBOT_SITE_FIELD_REQUIRED))
        dst_props: dict = default_sites_tool.inputSchema["properties"]
        dst_props["fields"]["items"]["enum"] = sites_field_options

        resources_field_options: list[str] = list(set(RESOURCES_FIELDS_DEFAULT) - set(RESOURCES_FIELDS_REQUIRED))
        resources_type_options: list[str] = list(set(INTERROBOT_RESOURCE_FIELD_MAPPING.keys()) - set(RESOURCES_FIELDS_REQUIRED))
        resources_sort_options: list[str] = list(RESOURCES_DEFAULT_SORT_MAPPING.keys())
        all_sites_display: str = ", ".join([f"{s.url} (site: {s.id})" for s in all_sites])

        drt_props: dict = default_resources_tool.inputSchema["properties"]
        drt_props["fields"]["items"]["enum"] = resources_field_options
        drt_props["sort"]["enum"] = resources_sort_options
        drt_props["sites"]["enum"] = sites_field_options
        drt_props["sites"]["description"] = ("Optional "
                "list of project ID to filter search results to a specific site. In 95% "
                "of scenarios, you'd filter to only one site, but many site filtering is offered "
                f"for advanced search scenarios. Available sites include {all_sites_display}.")

        return [default_sites_tool, default_resources_tool]
