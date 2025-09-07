SiteOne MCP Setup Guide
=======================

Instructions for setting up `mcp-server-webcrawl <https://pragmar.com/mcp-server-webcrawl/>`_ with SiteOne crawler.
This allows your LLM (e.g. Claude Desktop) to search content and metadata from websites you've crawled using SiteOne.

.. raw:: html

   <iframe width="560" height="315" src="https://www.youtube.com/embed/JOGRYbo6WwI" frameborder="0" allowfullscreen></iframe>

Follow along with the video, or the step-action guide below.

Requirements
------------

Before you begin, ensure you have:

- `Claude Desktop <https://claude.ai/download>`_ installed
- `Python <https://python.org>`_ 3.10 or later installed
- `SiteOne Crawler <https://crawler.siteone.io>`_ installed
- Basic familiarity with command line interfaces

What is SiteOne?
----------------

SiteOne is a GUI crawler that offers:

- User-friendly desktop interface for setting up and managing crawls
- Offline website generation capabilities
- Comprehensive crawl reporting
- Intuitive controls for non-technical users

Installation Steps
------------------

1. Install mcp-server-webcrawl
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Open your terminal or command line and install the package::

    pip install mcp-server-webcrawl

Verify installation was successful::

    mcp-server-webcrawl --help

2. Create Crawls with SiteOne
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. Open SiteOne Crawler application
2. Enter a URL to crawl (e.g., example.com)
3. **Important**: Check the "Generate offline website" option (this is required for MCP integration)
4. Click the start button to begin crawling
5. Repeat for additional sites as needed (e.g., pragmar.com)
6. Note the directory where SiteOne is storing the generated offline content (this is shown in the application)

3. Configure Claude Desktop
~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. Open Claude Desktop
2. Go to **File → Settings → Developer → Edit Config**
3. Add the following configuration (modify paths as needed):

.. code-block:: json

    {
      "mcpServers": {
        "webcrawl": {
          "command": "/path/to/mcp-server-webcrawl",
          "args": ["--crawler", "siteone", "--datasrc",
            "/path/to/siteone/archives/"]
        }
      }
    }

.. note::
   - On Windows, use ``"mcp-server-webcrawl"`` as the command
   - On macOS, use the absolute path (output of ``which mcp-server-webcrawl``)
   - Change ``/path/to/siteone/archives/`` to the actual path where SiteOne stores offline website content

4. Save the file and **completely exit** Claude Desktop (not just close the window)
5. Restart Claude Desktop

4. Verify and Use
~~~~~~~~~~~~~~~~~

1. In Claude Desktop, you should now see MCP tools available under Search and Tools
2. Ask Claude to list your crawled sites::

    Can you list the crawled sites available?

3. Try searching content from your crawls::

    Can you find information about [topic] on [crawled site]?

4. Explore specific topics on your crawled sites::

    I'm interested in [keyword] in [crawled domain]. Can you tell me about it?

Troubleshooting
---------------

- If Claude doesn't show MCP tools after restart, verify your configuration file is correctly formatted
- Ensure Python and mcp-server-webcrawl are properly installed
- Check that your SiteOne archives path in the configuration is correct
- Make sure the "Generate offline website" option was checked when creating crawls
- Verify that each crawl completed successfully and files were saved to the expected location
- Remember that the first time you use a function, Claude will ask for permission

For more details, including API documentation and other crawler options, visit the `mcp-server-webcrawl documentation <https://github.com/pragmar/mcp-server-webcrawl>`_.