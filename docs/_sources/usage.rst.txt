
.. raw:: html

   <style>
   .wy-table-responsive table td, .wy-table-responsive table th {
     white-space: normal !important;
   }
   </style>

mcp-server-webcrawl Usage
=========================

Once installed, **mcp-server-webcrawl** can leverage search and retrieval capabilities to pull 
your website crawl data as needed, using advanced filtering. Use it to help manage your website, 
as an on-demand resource database (marketing, SEO, etc.), or anything else.

The truth of the matter is, you don't need to know the API behind the MCP server, as it is 
designed to be consumed by the LLM. It is, however, useful to understand for advanced use cases.

Available Tools
---------------

The API is *supposed* to stay out your way, and to a large degree
it can be navigated autonomously by your MCP client. Sometimes, however,
you may need to nudge the LLM to the correct field or search strategy. The 
following is the currect API interface for your reference.

webcrawl_sites
~~~~~~~~~~~~~~~~~~~

This tool retrieves a list of sites (project websites or crawl directories).

.. list-table::
   :header-rows: 1
   :widths: 15 15 15 55

   * - Parameter
     - Type
     - Required
     - Description
   * - ids
     - array<int>
     - No
     - List of project IDs to retrieve. Leave empty for all projects.
   * - fields
     - array<string>
     - No
     - List of additional fields to include beyond defaults (id, url). Empty list means default fields only. Options include created (ISO 8601), modified (ISO 8601), and norobots (str).

webcrawl_search
~~~~~~~~~~~~~~~~~~~~

This tool searches for resources (webpages, CSS, images, etc.) across projects and retrieves specified fields.

.. list-table::
   :header-rows: 1
   :widths: 15 15 15 55

   * - Parameter
     - Type
     - Required
     - Description
   * - ids
     - array<int>
     - No
     - Optional list of resource IDs to retrieve specific resources directly.
   * - sites
     - array<int>
     - No
     - Optional list of project IDs to filter search results to specific sites. In most scenarios, you'd filter to only one site.
   * - query
     - string
     - No
     - Fulltext search query string. Leave empty to return all resources when filtering on other fields for better precision. Supports fulltext and boolean operators (AND, OR, NOT), quoted phrases, and suffix wildcards, but not prefix wildcards.
   * - statuses
     - array<int>
     - No
     - Optional list of HTTP status codes to filter results. Example: [200] returns only successful resources, [404, 500] returns only resources with Not Found or Server Error.
   * - types
     - array<string>
     - No
     - Optional filter for specific resource types. Allowed values include: headers, content, size, name, time.
   * - fields
     - array<string>
     - No
     - List of additional fields to include beyond defaults (modified, created). Empty list means default fields only. The content field can lead to large results and should be used with LIMIT.
   * - sort
     - string
     - No
     - Sort order for results. Prefixed with + for ascending, - for descending. ? is a special option for random sort, useful in statistical sampling. Options include: +id, -id, +url, -url, +status, -status, ?.
   * - limit
     - integer
     - No
     - Maximum number of results to return. Default is 20, max is 100.
   * - offset
     - integer
     - No
     - Number of results to skip for pagination. Default is 0.
   * - thumbnails
     - boolean
     - No
     - Support for base64 encoded data for image thumbnails. Default is false. This creates small thumbnails that enable basic image recognition while keeping token output minimal. Only works for image (img) types. SVG format is not currently supported.

Crawler Features Support
~~~~~~~~~~~~~~~~~~~~~~~

API support, by parameter, across crawler type.

.. list-table::
   :header-rows: 1
   :widths: 16 16 16 16 16 16

   * - Parameter
     - wget
     - WARC
     - InterroBot
     - Katana
     - SiteOne
   * - Sites/ids
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
   * - Sites/fields
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
   * - Search/ids
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
   * - Search/sites
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
   * - Search/query
     - ①
     - ✔
     - ✔
     - ✔
     - ①
   * - Search/types
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
   * - Search/fields
     - ②
     - ✔
     - ✔
     - ✔
     - ②
   * - Search/statuses
     - ③
     - ✔
     - ✔
     - ✔
     - ✔
   * - Search/sort
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
   * - Search/limit
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
   * - Search/offset
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
   * - Search/thumbnails
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔

Crawler Field Support
~~~~~~~~~~~~~~~~~~~~~

API support, by field, across crawler type.

.. list-table::
   :header-rows: 1
   :widths: 16 16 16 16 16 16

   * - Parameter
     - wget
     - WARC
     - InterroBot
     - Katana
     - SiteOne
   * - id
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
   * - url
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
   * - type
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
   * - status
     - ③
     - ✔
     - ✔
     - ✔
     - ✔
   * - size
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
   * - headers
     - 
     - ✔
     - ✔
     - ✔
     - 
   * - content
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔

①②③ wget (--mirror) does not index HTTP status beyond 200 OK (HTTP errors not saved to disk).
wget and SiteOne crawlers do not support queryable HTTP headers. When used in 
WARC mode (as opposed to simple mirror), wget is capable of collecting HTTP headers 
and status.

Crawlers have strengths and weaknesses, judge them on how well they
fit your needs. Don't worry too
much about field support. You probably don't need HTTP headers, except for
specialized web-dev, honestly. They all support fulltext boolean search
across the crawl data.