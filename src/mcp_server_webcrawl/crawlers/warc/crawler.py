from typing import Any, Optional
from pathlib import Path

from mcp_server_webcrawl.crawlers.base.indexed import IndexedCrawler
from mcp_server_webcrawl.crawlers.base.api import BaseJsonApi
from mcp_server_webcrawl.crawlers.warc.adapter import WARC_RESOURCE_FIELD_MAPPING
from mcp_server_webcrawl.crawlers.warc.adapter import get_resources, get_sites
from mcp_server_webcrawl.models.resources import ResourceResultType, RESOURCES_FIELDS_REQUIRED
from mcp_server_webcrawl.utils.tools import get_crawler_tools
from mcp_server_webcrawl.utils.logger import get_logger

logger = get_logger()

class WarcCrawler(IndexedCrawler):
    """
    A crawler implementation for WARC (Web ARChive) files.
    Provides functionality for accessing and searching web archive content.
    """

    def __init__(self, datasrc: Path):
        """
        Initialize the WARC crawler with a data source directory.
        
        Args:
            datasrc: The input argument as Path, it can be a directory (returning
                    sites) or a site returning results (but still requiring sites awareness)
        """
        assert datasrc is not None, f"WarcCrawler needs a datasrc, regardless of action"
        assert datasrc.is_dir(), "WarcCrawler datasrc must be a directory"
        super().__init__(datasrc)
        # used to produce LLM search manual
        self._indexed_get_sites = get_sites

    def get_sites_api(
            self,
            ids: Optional[list[int]] = None,
            fields: Optional[list[str]] = None,
    ) -> BaseJsonApi:
        """
        Implementation of sites API - lists WARC files as sites.
        
        Args:
            ids: Optional list of site IDs to filter
            fields: Optional list of fields to include in the response
            
        Returns:
            API response object containing site information
        """
        sites = get_sites(self.datasrc, ids=ids, fields=fields)
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
        """
        Implementation of resources API - searches within WARC files.
        
        Args:
            ids: Optional list of resource IDs to retrieve
            sites: Optional list of site IDs to search within
            query: Search query string
            types: Optional list of resource types to filter
            fields: Optional list of fields to include in the response
            statuses: Optional list of HTTP status codes to filter
            sort: Sort order for results
            limit: Maximum number of results to return
            offset: Number of results to skip for pagination
            
        Returns:
            API response object containing resource information
        """
        
        # no site is specified, use the first site
        if not sites:
            all_sites = get_sites(self.datasrc)
            if not all_sites:
                return BaseJsonApi("GetResources", {}).set_results([], 0, 0, limit)
            sites = [all_sites[0].id]

        site_matches = get_sites(self.datasrc, ids=sites)
        if not site_matches:
            return BaseJsonApi("GetResources", {}).set_results([], 0, 0, limit)

        typed_resource_types = None
        if types:
            typed_resource_types = [rt for rt in ResourceResultType if rt.value in types]

        results, total = get_resources(
            self.datasrc,
            ids=ids,
            sites=sites,
            query=query,
            types=typed_resource_types,
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
