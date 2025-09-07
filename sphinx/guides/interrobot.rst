InterroBot MCP Setup Guide
==========================

Instructions for setting up `mcp-server-webcrawl <https://pragmar.com/mcp-server-webcrawl/>`_ with InterroBot.
This allows your LLM (e.g. Claude Desktop) to search content and metadata from websites you've crawled with InterroBot.

.. raw:: html

   <iframe width="560" height="315" src="https://www.youtube.com/embed/55y8oKWXJLs" frameborder="0" allowfullscreen></iframe>

Follow along with the video, or the step-action guide below.

Requirements
------------

Before you begin, ensure you have:

- `Claude Desktop <https://claude.ai/download>`_ installed
- `Python <https://python.org>`_ 3.10 or later installed
- `InterroBot <https://interro.bot>`_ installed
- Basic familiarity with command line interfaces

What is InterroBot?
-------------------

InterroBot is a commercial web crawler and analyzer that works seamlessly with mcp-server-webcrawl, providing several advantages:

- User-friendly graphical interface for managing crawls
- Comprehensive data collection including page content and metadata
- Natively indexed, no first search build lag
- Cross-platform \(Windows, macOS, Android\)

Installation Steps
------------------

1. Install mcp-server-webcrawl
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Open your terminal or command line and install the package::

    pip install mcp-server-webcrawl

Verify installation was successful::

    mcp-server-webcrawl --help

2. Create Crawls with InterroBot
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. Open InterroBot
2. For a new project, you'll see an empty project screen
3. Add websites to crawl by entering URLs (e.g., example.com, pragmar.com)
4. Wait for the crawling to complete (typically takes a few seconds to minutes depending on site size)
5. Note the location of your InterroBot database file, which will be needed for configuration. It is available in InterroBot options, under Advanced section:
   - On Windows: Typically in ``[homedir]/Documents/InterroBot/interrobot.v2.db``
   - On macOS: Path can be found in InterroBot settings page

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
          "args": ["--crawler", "interrobot", "--datasrc",
            "[homedir]/Documents/InterroBot/interrobot.v2.db"]
        }
      }
    }

.. note::
   - On Windows, use ``"mcp-server-webcrawl"`` as the command
   - On macOS, use the absolute path (output of ``which mcp-server-webcrawl``)
   - Replace ``[homedir]/Documents/InterroBot/interrobot.v2.db`` with the actual path to your InterroBot database file, available in InterroBot options

4. Save the file and **completely exit** Claude Desktop (not just close the window)
5. Restart Claude Desktop

4. Verify and Use
~~~~~~~~~~~~~~~~~

1. In Claude Desktop, you should now see MCP tools available under Search and Tools
2. Ask Claude to list your crawled sites::

    Can you list the crawled sites available?

3. Try searching content from your crawls::

    Can you find information about [topic] on [crawled site]?

4. Explore specific capabilities, such as generating site reports::

    Can you give me a file type summary for [crawled site]? Which types of files are there, page count, etc.

Troubleshooting
---------------

- If Claude doesn't show MCP tools after restart, verify your configuration file is correctly formatted
- Ensure Python and mcp-server-webcrawl are properly installed
- Check that your InterroBot database path in the configuration is correct
- Make sure InterroBot has successfully completed crawling the websites
- Remember that the first time you use a function, Claude will ask for permission
- For large websites with many pages, search queries might take longer to process initially

For more details, including API documentation and other crawler options, visit the `mcp-server-webcrawl documentation <https://github.com/pragmar/mcp-server-webcrawl>`_.