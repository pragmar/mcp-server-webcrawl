wget MCP Setup Guide
====================

Instructions for setting up `mcp-server-webcrawl <https://pragmar.com/mcp-server-webcrawl/>`_ with
`wget <https://en.wikipedia.org/wiki/Wget>`_.
This allows your LLM (e.g. Claude Desktop) to search content and metadata from websites you've crawled.

.. raw:: html

   <iframe width="560" height="315" src="https://www.youtube.com/embed/uqEEqVsofhc" frameborder="0" allowfullscreen></iframe>

Follow along with the video, or the step-action guide.

Requirements
------------

Before you begin, ensure you have:

- `Claude Desktop <https://claude.ai/download>`_ installed
- `Python <https://python.org>`_ 3.10 or later installed
- Basic familiarity with command line interfaces
- wget installed (macOS users can install via Homebrew, Windows users need WSL/Ubuntu)

Installation Steps
------------------

1. Install mcp-server-webcrawl
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Open your terminal or command line and install the package:

.. code-block:: bash

    pip install mcp-server-webcrawl

Verify installation was successful by checking the version:

.. code-block:: bash

    mcp-server-webcrawl --help

2. Configure Claude Desktop
~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. Open Claude Desktop
2. Go to **File → Settings → Developer → Edit Config**

3. Add the following configuration (modify paths as needed):

.. code-block:: json

    {
      "mcpServers": {
        "webcrawl": {
          "command": "/path/to/mcp-server-webcrawl",
          "args": ["--crawler", "wget", "--datasrc",
            "/path/to/wget/archives/"]
        }
      }
    }

.. note::
   - On Windows, use ``"mcp-server-webcrawl"`` as the command
   - On macOS, use the absolute path (output of ``which mcp-server-webcrawl``)
   - Change ``/path/to/wget/archives/`` to your actual directory path

4. Save the file and **completely exit** Claude Desktop (not just close the window)
5. Restart Claude Desktop

3. Crawl Websites with wget
~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. Open Terminal (macOS) or Ubuntu/WSL (Windows)
2. Navigate to your target directory for storing crawls
3. Run wget with the mirror option:

.. code-block:: bash

    wget --mirror https://example.com

4. Verify and Use
~~~~~~~~~~~~~~~~~

1. In Claude Desktop, you should now see an MCP tool option under Search and Tools
2. Ask Claude to list your crawled sites:

.. code-block:: text

    Can you list the crawled sites available?

3. Try searching content from your crawls:

.. code-block:: text

    Can you find information about [topic] on [crawled site]?

Troubleshooting
---------------

- If Claude doesn't show MCP tools after restart, verify your configuration file is correctly formatted
- Ensure Python and mcp-server-webcrawl are properly installed, and on PATH or using absolute paths
- Check that your crawl directory path in the configuration is correct
- Remember that the first time you use a function, Claude will ask for permission
- Indexing for file-based archives (wget included) requires build time on first search, time is dependent on archive size

For more details, including API documentation and other crawler options, visit the `mcp-server-webcrawl documentation <https://github.com/pragmar/mcp-server-webcrawl>`_.