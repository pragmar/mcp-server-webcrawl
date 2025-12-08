.. raw:: html

   <style>
   .wy-table-responsive table td, .wy-table-responsive table th {
     white-space: normal !important;
   }
   table th.head {
    font-size: 80%;
    word-break: break-word;
    }
    table td, table th {
        text-align: center;
        vertical-align: middle;
    }
    table td:first-of-type, table th:first-of-type {
        text-align: left;
        white-space: nowrap !important;
    }
   </style>

Usage
=====

Once installed, **mcp-server-webcrawl** can leverage search and retrieval capabilities to pull
your website crawl data as needed, using advanced filtering. Use it to help manage your website,
as an on-demand resource database (marketing, SEO, etc.), or anything else.

The truth of the matter is, you don't need to know the API behind the MCP server, as it is
designed to be consumed by the LLM. It is, however, useful to understand for advanced use cases.

Available Tools
---------------

The API is *supposed* to stay out your way, and to a large degree
it can be navigated autonomously by your MCP client. Sometimes
you may need to nudge the LLM to the correct field or search strategy. The
following is the currect API interface for your reference.

webcrawl_sites
~~~~~~~~~~~~~~

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
     - List of additional fields to include beyond defaults (id, type, name, urls). Empty list means default fields only. Options include created (ISO 8601), modified (ISO 8601).

webcrawl_search
~~~~~~~~~~~~~~~

This tool searches for resources (webpages, CSS, images, etc.) across projects and retrieves specified fields.

.. list-table::
   :header-rows: 1
   :widths: 15 15 15 55

   * - Parameter
     - Type
     - Required
     - Description
   * - sites
     - array<int>
     - No
     - Optional list of project IDs to filter search results to specific sites. In most scenarios, you'd filter to only one site.
   * - query
     - string
     - No
     - Fulltext search query string. Leave empty to return all resources when filtering on other fields for better precision. Supports fulltext and boolean operators (AND, OR, NOT), quoted phrases, and suffix wildcards, but not prefix wildcards. See below for complete boolean and field search capabilities.
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
   * - extras
     - array<string>
     - No
     - Array of extra features to include in results. Options include markdown, snippets, thumbnails, regex, and xpath. (see extras table)
   * - extrasRegex
     - array<string>
     - No
     - Array of regular expression patterns to extract content. One or more regex patterns can be requested. Only used when 'regex' is included in the extras array.
   * - extrasXpath
     - array<string>
     - No
     - Array of XPath expressions to extract specific content from HTML resources. One or more XPath selectors can be requested. Only used when 'xpath' is included in the extras array.


Crawler Features Support
~~~~~~~~~~~~~~~~~~~~~~~~

API support, by parameter, across crawler type.

.. list-table::
   :header-rows: 1
   :widths: 13 12 12 13 12 12 13 13
   :class: featuresgrid

   * - Parameter
     - Archive­Box
     - HT­Track
     - Interro­Bot
     - Ka­tana
     - Site­One
     - WARC
     - wget
   * - Sites/ids
     - ✔
     - ✔
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
     - ✔
     - ✔
   * - Search/ids
     - ✔
     - ✔
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
     - ✔
     - ✔
   * - Search/query
     - ✔
     - ✔
     - ✔
     - ✔
     - ①
     - ✔
     - ①
   * - Search/fields
     - ✔
     - ✔
     - ✔
     - ✔
     - ②
     - ✔
     - ②
   * - Search/sort
     - ✔
     - ✔
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
     - ✔
     - ✔
   * - Search/offset
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
   * - Search/extras
     - ✔
     - ✔
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
   :widths: 13 12 12 13 12 12 13 13
   :class: featuresgrid

   * - Parameter
     - Archive­Box
     - HT­Track
     - Interro­Bot
     - Ka­tana
     - Site­One
     - WARC
     - wget
   * - site.id
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
   * - site.name
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
   * - site.type
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
   * - site.urls
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
   * - resource.id
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
   * - resource.url
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
   * - resource.type
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
   * - resource.status
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
     - ③
   * - resource.size
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
   * - resource.headers
     - ✔
     - ✔
     - ✔
     - ✔
     -
     - ✔
     -
   * - resource.content
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔
     - ✔

①②③ wget (--mirror) does not index HTTP status beyond 200 OK (HTTP errors not saved to disk).
wget and SiteOne crawler implementations do not support field searchable HTTP headers. When used in
WARC mode (as opposed to simple mirror), wget is capable of collecting HTTP headers
and status.

Crawlers all have strengths and weaknesses, judge them on how well they
fit your needs, and don't be all that concerned over headers field support. They all
support fulltext boolean search across the crawl data.

Boolean Search Syntax
~~~~~~~~~~~~~~~~~~~~~

The query engine supports field-specific (``field: value``) searches and complex boolean
expressions. Fulltext is supported as a combination of the url, content, and headers fields.

While the API interface is designed to be consumed by the LLM directly, it can be helpful
to familiarize yourself with the search syntax. Searches generated by the LLM are
inspectable, but generally collapsed in the UI. If you need to see the query, expand
the MCP collapsable.

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Query Example
     - Description
   * - privacy
     - fulltext single keyword match
   * - "privacy policy"
     - fulltext match exact phrase
   * - boundar*
     - fulltext wildcard matches results starting with *boundar* (boundary, boundaries)
   * - id: 12345
     - id field matches a specific resource by ID
   * - url: example.com/*
     - url field matches results with URL containing example.com/
   * - type: html
     - type field matches for HTML pages only
   * - status: 200
     - status field matches specific HTTP status codes (equal to 200)
   * - status: >=400
     - status field matches specific HTTP status code (greater than or equal to 400)
   * - content: h1
     - content field matches content (HTTP response body, often, but not always HTML)
   * - headers: text/xml
     - headers field matches HTTP response headers
   * - privacy AND policy
     - fulltext matches both
   * - privacy OR policy
     - fulltext matches either
   * - policy NOT privacy
     - fulltext matches policies not containing privacy
   * - (login OR signin) AND form
     - fulltext matches fullext login or signin with form
   * - type: html AND status: 200
     - fulltext matches only HTML pages with HTTP success

Field Search Definitions
~~~~~~~~~~~~~~~~~~~~~~~~

Field search provides search precision, allowing you to specify which columns of the search index to filter.
Rather than searching the entire content, you can restrict your query to specific attributes like URLs,
headers, or content body. This approach improves efficiency when looking for
specific attributes or patterns within crawl data.

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Field
     - Description
   * - id
     - resource database ID
   * - url
     - resource URL
   * - type
     - enumerated list of types (see types table)
   * - size
     - resource size in bytes
   * - status
     - HTTP response codes
   * - headers
     - HTTP response headers
   * - content
     - HTTP body—HTML, CSS, JS, and more

Field Content
~~~~~~~~~~~~~

A subset of fields can be independently requested with results, while core fields are always on. Use of headers and content can consume tokens quickly. Use judiciously, or use extras to crunch more results into the context window. Fields are a top level argument, independent of any field searching taking place in the query.

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Field
     - Description
   * - id
     - always available
   * - url
     - always available
   * - type
     - always available
   * - status
     - always available
   * - created
     - on request
   * - modified
     - on request
   * - size
     - on request
   * - headers
     - on request
   * - content
     - on request

Content Types
~~~~~~~~~~~~~

Crawls contain a multitude of resource types beyond HTML pages. The ``type:`` field search
allows filtering by broad content type groups, particularly useful when filtering images without complex extension queries.
For example, you might search for ``type: html NOT content: login``
to find pages without "login," or ``type: img`` to analyze image resources. The table below lists all
supported content types in the search system.

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Type
     - Description
   * - html
     - webpages
   * - iframe
     - iframes
   * - img
     - web images
   * - audio
     - web audio files
   * - video
     - web video files
   * - font
     - web font files
   * - style
     - CSS stylesheets
   * - script
     - JavaScript files
   * - rss
     - RSS syndication feeds
   * - text
     - plain text content
   * - pdf
     - PDF files
   * - doc
     - MS Word documents
   * - other
     - uncategorized

Extras
~~~~~~

The ``extras`` parameter provides additional processing options, transforming result data (markdown, snippets), or connecting the LLM to external data (thumbnails). These options can be combined as needed to achieve the desired result format.

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Extra
     - Description
   * - thumbnails
     - Generates base64 encoded images to be viewed and analyzed by AI models. Enables image description, content analysis, and visual understanding while keeping token output minimal. Works with images, which can be filtered using ``type: img`` in queries. SVG is not supported.
   * - markdown
     - Provides the HTML content field as concise Markdown, reducing token usage and improving readability for LLMs. Works with HTML, which can be filtered using ``type: html`` in queries.
   * - snippets
     - Matches fulltext queries to contextual keyword usage within the content. When used without requesting the content field (or markdown extra), it can provide an efficient means of refining a search without pulling down the complete page contents. Also great for rendering old school hit-highlighted results as a list, like Google search in 1999. Works with HTML, CSS, JS, or any text-based, crawled file.
   * - regex
     - Extracts regular expression matches from crawled files such as HTML, CSS, JavaScript, etc. Not as precise a tool as XPath for HTML, but supports any text file as a data source. One or more regex patterns can be requested, using the ``extrasRegex`` argument.
   * - xpath
     - Extracts XPath selector data, used in scraping HTML content. Use XPath's text() selector for text-only, element selectors return outerHTML. Only supported with ``type: html``, other types will be ignored. One or more XPath selectors (//h1, count(//h1), etc.) can be requested, using the ``extrasXpath`` argument.

Extras provide a means of producing token-efficient HTTP content responses. Markdown produces roughly 1/3 the bytes of the source HTML, snippets are generally 500 or so bytes per result, and XPath can be as specific or broad as you choose. The more focused your requests, the more results you can fit into your LLM session.

The idea, of course, is that the LLM takes care of this for you. If you notice your LLM developing an affinity to the "content" field (full HTML), a nudge in chat to budget tokens using the extras feature should be all that is needed.