WARC MCP Setup Guide
====================

Instructions for setting up `mcp-server-webcrawl <https://pragmar.com/mcp-server-webcrawl/>`_ with 
`WARC <https://en.wikipedia.org/wiki/WARC_\(file_format\)>`_ files. This allows your LLM (e.g. 
Claude Desktop) to search content and metadata from websites you've archived in WARC format.

.. raw:: html

   <iframe width="560" height="315" src="https://www.youtube.com/embed/fx-4WZu-UT8" frameborder="0" allowfullscreen></iframe>

Follow along with the video, or the step-action guide below.

Requirements
------------

Before you begin, ensure you have:

- `Claude Desktop <https://claude.ai/download>`_ installed
- `Python <https://python.org>`_ 3.10 or later installed
- Basic familiarity with command line interfaces
- wget installed (macOS users can install via Homebrew, Windows users need WSL/Ubuntu)

What are WARC Files?
--------------------

WARC (Web ARChive) files are single-file web archives that store complete crawl data including:

- HTTP status codes
- HTTP headers
- Response content

Compared to wget mirror mode:

- **WARC**: More comprehensive (preserves status codes and headers) but slower crawling
- **wget mirror**: Faster crawling but doesn't preserve status codes or headers

Installation Steps
------------------

1. Install MCP Server Web Crawl
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Open your terminal or command line and install the package::

    pip install mcp-server-webcrawl

Verify installation was successful::

    mcp-server-webcrawl --version

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
          "args": ["--crawler", "warc", "--datasrc", 
            "/path/to/warc/archives/"]
        }
      }
    }

.. note::
   - On Windows, use ``"mcp-server-webcrawl"`` as the command
   - On macOS, use the absolute path (output of ``which mcp-server-webcrawl``)
   - Change ``/path/to/warc/archives/`` to your actual directory path where WARC files are stored

4. Save the file and **completely exit** Claude Desktop (not just close the window)
5. Restart Claude Desktop

3. Create WARC Files with Wget
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. Open Terminal (macOS) or Ubuntu/WSL (Windows)
2. Navigate to your target directory for storing WARC files
3. Run wget with WARC options:

.. code-block:: bash

    # Basic WARC capture
    wget --warc-file=example --recursive https://example.com

    # More comprehensive capture with page requirements (CSS, images, etc.)
    wget --warc-file=example --recursive --page-requisites https://example.com

Your WARC files will be created with a .warc.gz extension in your current directory.

4. Verify and Use
~~~~~~~~~~~~~~~~~

1. In Claude Desktop, you should now see MCP tools available under Search and Tools
2. Ask Claude to list your crawled sites::

    Can you list the crawled sites available?

3. Try searching content from your crawls::

    Can you find information about [topic] on [crawled site]?

Troubleshooting
---------------

- If Claude doesn't show MCP tools after restart, verify your configuration file is correctly formatted
- Ensure Python and mcp-server-webcrawl are properly installed
- Check that your WARC directory path in the configuration is correct
- Make sure your WARC files have the correct extension (typically .warc.gz)
- Remember that the first time you use each function, Claude will ask for permission
- For large WARC files, initial indexing may take some time

For more details, including API documentation and other crawler options, visit the `mcp-server-webcrawl documentation <https://github.com/pragmar/mcp_server_webcrawl>`_.