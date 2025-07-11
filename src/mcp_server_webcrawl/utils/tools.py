from mcp.types import Tool

from mcp_server_webcrawl.models.resources import (
    ResourceResultType,
    RESOURCES_FIELDS_BASE,
    RESOURCES_FIELDS_OPTIONS,
    RESOURCES_DEFAULT_SORT_MAPPING,
    RESOURCES_TOOL_NAME,
)
from mcp_server_webcrawl.models.sites import (
    SiteResult,
    SITES_FIELDS_DEFAULT,
    SITES_FIELDS_BASE,
    SITES_TOOL_NAME,
)

def get_crawler_tools(sites: list[SiteResult] | None = None):
    """
    Generate crawler tools based on available sites.

    Args:
        sites: optional list of site results to include in tool descriptions

    Returns:
        List of Tool objects for sites and resources
    """

    # you'd think maybe pass these in, but no, descriptions will also require tweaking
    # each crawler having its own peculiarities -- just let the subclass hack this
    # into whatever misshapen ball of clay it needs to be

    sites_field_options = list(set(SITES_FIELDS_DEFAULT) - set(SITES_FIELDS_BASE))
    resources_type_options = list(ResourceResultType.values())
    resources_sort_options = list(RESOURCES_DEFAULT_SORT_MAPPING.keys())
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
            description= ("Searches for resources (webpages, images, CSS, JS, etc.) across web crawler projects and "
                "retrieves specified fields. "
                "Supports boolean queries and field searching, along with site filtering to "
                "filter with fine control. "
                "To find a site homepage reliably, query type: html AND url: example.com (crawled domain) with sort='+url' and a LIMIT of 1. "
                "This pattern works consistently across all crawlers."
                "Most sites indexed by this tool will be small to moderately sized websites. "
                "Don't assume most keywords will generate results; start broader on first search (until you have a feel for results). "
                "A vital aspect of this API is field control; you can open up the limit wide when dealing with lightweight "
                "fields and dial way back when using larger fields, like content. Adjust dynamically. The best strategy "
                "balances preserving the user's context window while minimizing number of queries necessary to answer their question."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": ("The query field is the workhorse of the API and supports fulltext boolean queries "
                            "along with field searching using the name: value pattern. "
                            "Fields supported include page/resource id as id: <resource_id|int> (OR together for multiple docs), "
                            "HTTP status as status: <code|int>, URL as url: <url|str>, and content type as type: <type|str>. "
                            f"Valid types include ({', '.join(resources_type_options)}). "
                            "Additionally, headers as headers: <term|str> and content as content: <term|str> can be "
                            "searched specifically. You would only search content when fulltext search is diluted by other field hits. "
                            "For the status field, numerical operators are supported, e.g. status: >=400. "
                            "For the url and type fields, along with fulltext search terms (fieldless), FTS5 stem* suffix "
                            "wildcarding is enabled. An empty query returns all results. "
                            "A query MUST use one of these formats: (1) empty query for unfiltered results, (2) single keyword, "
                            "(3) quoted phrase: \"keyword1 keyword2\", (4) "
                            "explicit AND: keyword1 AND type: html, (5) explicit OR: keyword1 OR keyword2, or (6) advanced boolean: "
                            "(keyword1 OR keyword2) AND (status: 200 AND type: html). "
                            "The search index does not support stemming, use wildcards (keyword*), or the boolean OR and your "
                            "imagination instead."
                        )
                    },
                    "sites": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": ("List of crawl site IDs to filter search results to a specific site. In most "
                            "scenarios, you should filter to only one site, but multiple site filtering is offered for "
                            f"advanced search scenarios. Available sites include {sites_display}.")
                    },
                    "fields": {
                        "type": "array",
                        "items": {
                            "enum": RESOURCES_FIELDS_OPTIONS
                        },
                        "description": ("List of additional fields to include in the response beyond the base fields "
                            f"({', '.join(RESOURCES_FIELDS_BASE)}) returned for all results. "
                            "Empty list means base fields only. Use headers and content to retrieve raw HTTP contents, "
                            "and size to collect file size in bytes. "
                            "The content field can lead to large results and should be used judiciously with LIMIT. "
                            "Fields must be explicitly requested, even when used with sort. ")
                    },
                    "sort": {
                        "enum": resources_sort_options,
                        "default": "+url",
                        "description": ("Sort order for results. Prefixed with + for ascending, - for descending "
                        f"({', '.join(resources_sort_options)}). "
                        "? is a special option for random sort, useful in statistical sampling. The API expects exactly "
                        "one of the enum values above, not a quoted string.")
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return. Default is 20, max is 100."
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Number of results to skip for pagination. Default is 0."
                    },
                    "extras": {
                        "type": "array",
                        "items": {
                            "enum": ["thumbnails", "markdown", "snippets", "xpath"]
                        },
                        "description": ("Optional array of extra features to include in results. Available options include:\n"
                            "- 'thumbnails': generates base64 encoded thumbnails for image resources that can be viewed and "
                            "analyzed by AI models. Enables image description, content analysis, and visual understanding while"
                            "keeping token output minimal. Only works for image "
                            "(img) types, which can be filtered using `type: img` in queries. SVG is not supported.\n"
                            "- 'markdown': transforms the HTML content field into concise markdown, "
                            "reducing token usage and improving readability for LLMs.\n"
                            "- 'snippets': matches fulltext queries to contextual keyword usage within the content. When "
                            "used without requesting the content field (or markdown extra), it can provide an efficient means "
                            "of refining a search without pulling down the complete page contents. Also great for rendering "
                            "old school hit-highlighted results as a list, like Google search in 1999. Works with HTML, CSS, JS, "
                            "or any text-based, crawled file.\n"
                            "- 'xpath': extracts xpath selector data. Supports count(). Use xpath's text() for "
                            "text only, element selectors for HTML data. Only supported for HTML, other "
                            "types will be ignored. Sometimes referred to as scraping."
                            "")
                    },
                    "extrasXpath": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "description": ("Array of XPath expressions to extract specific content from HTML resources. "
                            "Each XPath should be a valid selector expression like `/html/body/h1`, `//h1/text()`, "
                            "//a, //a/@href, or count(//a). If you need many values (such as connected a/text() "
                            "and a/@href), request elements to preserve the relationship. "
                            "Use text() or @name when targeting text, elements will return outer HTML. "
                            "Only used when 'xpath' is included in the extras array. Many xpath expressions can be "
                            "passed at once to extract multiple selectors. Results are grouped by document within results. ")
                    }
                },
                "required": []
            },
        ),
    ]

    return tools
