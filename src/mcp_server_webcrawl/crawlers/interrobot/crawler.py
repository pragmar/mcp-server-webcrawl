
from typing import Optional, Any
from mcp.types import TextContent, ImageContent, EmbeddedResource, Tool

from mcp_server_webcrawl.models.sites import SiteResult
from mcp_server_webcrawl.models.resources import ResourceResultType
from mcp_server_webcrawl.models.resources import (
    RESOURCES_FIELDS_DEFAULT,
    RESOURCES_FIELDS_REQUIRED,
)
from mcp_server_webcrawl.crawlers.base.crawler import BaseCrawler
from mcp_server_webcrawl.crawlers.base.api import BaseJsonApi
from mcp_server_webcrawl.crawlers.interrobot.adapter import (
    get_sites, 
    get_resources,
    INTERROBOT_RESOURCE_FIELD_MAPPING, 
    INTERROBOT_SORT_MAPPING,
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

    def __init__(self, datasrc):
        """
        Initialize the InterroBotCrawler with a data source path.

        Args:
            datasrc: Path to the data source
        """
        super().__init__(datasrc)

    async def mcp_call_tool(self, name: str, arguments: dict[str, Any] | None
        ) -> list[TextContent | ImageContent | EmbeddedResource]:
        """
        Handle tool execution requests.
        
        Args:
            name: Name of the tool to call
            arguments: Arguments to pass to the tool
            
        Returns:
            List of content objects
        """
        result = await super().mcp_call_tool(name, arguments)
        # post-processing here

        return result

    async def mcp_list_tools(self) -> list[Tool]:
        """
        List available tools for this crawler.
        
        Returns:
            List of Tool objects
        """
        # get the default crawler tools, then override necessary fields
        all_sites: list[SiteResult] = get_sites(self.datasrc)
        default_tools: list[Tool] = get_crawler_tools(sites=all_sites)
        assert len(default_tools) == 2, "expected exactly 2 Tools: sites and resources"

        # can replace get_crawler_tools or extend, here it is overwritten from default
        # you'd think maybe pass changes in, but no, it's better ad hoc
        default_sites_tool, default_resources_tool = default_tools
        
        # this adds InterroBot specific Robots field
        sites_field_options = list(set(INTERROBOT_SITE_FIELD_MAPPING.keys()) - set(INTERROBOT_SITE_FIELD_REQUIRED))
        dst_props = default_sites_tool.inputSchema["properties"]
        dst_props["fields"]["items"]["enum"] = sites_field_options

        resources_field_options = list(set(RESOURCES_FIELDS_DEFAULT) - set(RESOURCES_FIELDS_REQUIRED))
        resources_type_options = list(set(INTERROBOT_RESOURCE_FIELD_MAPPING.keys()) - set(RESOURCES_FIELDS_REQUIRED))
        resources_sort_options = list(INTERROBOT_SORT_MAPPING.keys())
        all_sites_display = ", ".join([f"{s.url} (site: {s.id})" for s in all_sites])

        drt_props = default_resources_tool.inputSchema["properties"]
        drt_props["fields"]["items"]["enum"] = resources_field_options
        drt_props["types"]["items"]["enum"] = resources_type_options
        drt_props["sort"]["enum"] = resources_sort_options        
        drt_props["sites"]["enum"] = sites_field_options
        drt_props["sites"]["description"] = ("Optional "
                "list of project ID to filter search results to a specific site. In 95% "
                "of scenarios, you'd filter to only one site, but many site filtering is offered "
                f"for advanced search scenarios. Available sites include {all_sites_display}.")

        return [default_sites_tool, default_resources_tool]

    def get_sites_api(
            self,
            ids: Optional[list[int]] = None,
            fields: Optional[list[str]] = None,
        ) -> BaseJsonApi:
        """
        Retrieve site information from the InterroBot data source.
        
        Args:
            ids: Optional list of site IDs to filter
            fields: Optional list of fields to include in the response
            
        Returns:
            API response object containing site information
        """
        json_result: BaseJsonApi = BaseJsonApi("GetProjects", {
            "ids": ids, "fields": fields})
        results: list[SiteResult] = get_sites(self.datasrc, ids, fields)
        json_result.set_results(results, len(results), 0, 100)
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
        """
        Get resources in JSON format based on the provided parameters.

        Args:
            ids: Optional list of resource ids to retrieve specific resources directly
            sites: Optional list of project ids to filter search results to a specific site
            query: Search query string
            types: Optional filter for specific resource types
            fields: List of additional fields to include in the response
            statuses: Optional list of HTTP status codes to filter results
            sort: Sort order for results
            limit: Maximum number of results to return
            offset: Number of results to skip for pagination

        Returns:
            JSON string containing the results
        """
        # convert keys/strings to enums for a sturdier API
        # this is the MCP/API boundary, inverse occurs on to_dict
        enum_types: list[ResourceResultType] = [ResourceResultType(t) for t in types] if types else None
        json_result: BaseJsonApi = BaseJsonApi("GetResources", {
            "ids": ids,
            "sites": sites,
            "query": query,
            "types": enum_types,
            "fields": fields,
            "statuses": statuses,
            "sort": sort,
            "limit": limit,
            "offset": offset,
        })

        results, total = get_resources(
            self.datasrc,
            ids=ids,
            sites=sites,
            query=query,
            types=enum_types,
            fields=fields,
            statuses=statuses,
            sort=sort,
            limit=limit,
            offset=offset,
        )

        json_result.set_results(results, total, offset, limit)
        return json_result
