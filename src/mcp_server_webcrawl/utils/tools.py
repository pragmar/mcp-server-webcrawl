
from typing import Optional
from mcp.types import Tool
from mcp_server_webcrawl.models.resources import (
    ResourceResultType,
    RESOURCES_FIELDS_REQUIRED,
)
from mcp_server_webcrawl.models.sites import (
    SiteResult, 
    SITES_TOOL_NAME, 
    SITES_FIELDS_DEFAULT,
    SITES_FIELDS_REQUIRED,
)
from mcp_server_webcrawl.models.resources import (
    RESOURCES_TOOL_NAME, 
    RESOURCES_FIELDS_DEFAULT,
    RESOURCES_SORT_OPTIONS_DEFAULT,
)

def get_crawler_tools(sites: Optional[list[SiteResult]] = None):
    """
    Generate crawler tools based on available sites.

    Parameters:
        sites: Optional list of site results to include in tool descriptions

    Returns:
        List of Tool objects for sites and resources
    """

    # you'd think maybe pass these in, but no, descriptions will also require tweaking
    # each crawler having its own peculiarities -- just let the subclass hack this
    # into whatever misshapen ball of clay it needs to be

    sites_field_options = list(set(SITES_FIELDS_DEFAULT) - set(SITES_FIELDS_REQUIRED))
    resources_field_options = list(set(RESOURCES_FIELDS_DEFAULT) - set(RESOURCES_FIELDS_REQUIRED))
    resources_type_options = list(ResourceResultType.values())
    resources_sort_options = RESOURCES_SORT_OPTIONS_DEFAULT
    sites_display = ", ".join([f"{s.url} (site: {s.id})" for s in sites]) if sites is not None else ""

    tools = [
        Tool(
            name=SITES_TOOL_NAME,
            description="Retrieves a list of sites (project websites or crawl directories).",
            inputSchema={
                "type": "object",
                "properties": {
                    "ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "List of project IDs to retrieve. Leave empty for all projects."
                    },
                    "fields": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": sites_field_options
                        },
                        "description": ("List of additional fields to include in the response beyond the defaults "
                            "(id, url) Empty list means default fields only. Options include created (ISO 8601), "
                            "modified (ISO 8601), and norobots (str).")
                    }
                },
                "required": []
            },
        ),
        Tool(
            name=RESOURCES_TOOL_NAME,
            description= ("Searches for resources (webpages, images, CSS, JS, etc.) across projects and retrieves specified fields. "
                "Invaluable tips to guide efficient search follows. "
                "To find a site homepage or index, use sort='+id' with types=['html'] and the appropriate site ID. "
                "Most sites indexed by this tool will be small to moderately sized websites, "
                "don't assume most keywords will generate results. "
                "When searching a new topic, it is generally best to start with just a site "
                "(all resources, lay of the land), a site and a search query, "
                "or by site and filters—combine query and filters once you have a result set to refine. "
                "This becomes less true as you search more, acquiring a lay of the land and ability to anticipate results. "
                "If you need to separate internal from external pages, you can query the site index URL with a wildcard (*), e.g. "
                "https://example.com/*. A vital aspect of this API is field control, you should open up the limit wide when dealing with thin "
                "fields (string length) and dial way back when using larger fields, like content. Adjust dynamically, the best strategy "
                "balances preserving the user's context window while minimizing number of queries necessary to answer their question."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": ("Fulltext search query string. Leave empty to return all resources when "
                            "filtering on other fields and you will get better precision. "
                            "Extremely useful tips to guide query construction follows. "
                            "Be explicit—a query MUST use one of these formats: (1) single keyword, (2) quoted phrase: \"keyword1 keyword2\", (3) " 
                            "explicit AND: keyword1 AND keyword2, (4) explicit OR: keyword1 OR keyword2, or (5) advanced boolean: (keyword1 AND keyword2) " 
                            "OR (keyword3 NOT keyword4). " 
                            "WARNING, space-separated keywords without quotes or operators will not work correctly."
                            "Supports fulltext and boolean operators, syntax and capabilities consistent with "
                            "SQLite FTS5 in boolean mode. Supports AND, OR, NOT operators, quoted phrases, "
                            "and suffix wildcards (word*), but not prefix wildcards (*word). "
                            "Parentheses nesting for complex boolean expressions is fully supported. "
                            "Does not support `field: value` format, it will poison the query, cause zero results—use filters instead. "
                            "Does not support stemming, use wildcards (keyword*) instead."
                        )
                    },
                    "ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": ("Optional list of resource IDs to retrieve specific resources directly.")
                    },
                    "sites": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": ("Optional list of project ID to filter search results to a specific site. In 95% "
                            "of scenarios, you'd filter to only one site, but multiple site filtering is offered for "
                            f"advanced search scenarios. Available sites include {sites_display}.")
                    },
                    "types": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": resources_type_options,
                        },
                        "description": "Optional filter for specific resource types."
                    },
                    "fields": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": resources_field_options
                        },
                        "description": ("List of additional fields to include in the response beyond the defaults "
                            f"({', '.join(resources_field_options)}). Empty list means default fields only. "
                            "The content field can lead to large results and should be used judiously with LIMIT.")
                    },
                    "statuses": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": ("Optional list of HTTP status codes to filter results. "
                            "For example, [200] returns only successful resources, [404, 500] returns "
                            "only resources with Not Found or Server Error.")
                    },
                    "sort": {
                        "type": "string",
                        "enum": resources_sort_options,
                        "description": ("Sort order for results. Prefixed with + for ascending, - for descending. "
                        "? is a special option for random sort, useful in statistical sampling.")
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return. Default is 20, max is 100."
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Number of results to skip for pagination. Default is 0."
                    },
                    "thumbnails": {
                        "type": "boolean",
                        "description": ("Support for base64 encoded data for image thumbnails. "
                            "Default is false. This creates small thumbnails that enable basic "
                            "image recognition while keeping token output minimal. Only works for image "
                            "(""img"") types, which is filterable in types field. Svg format is not " 
                            "currently supported.")
                    },
                },
                "required": []
            },
        ),
    ]

    return tools
