ArchiveBox MCP Setup Guide
==========================

Instructions for setting up `mcp-server-webcrawl <https://pragmar.com/mcp-server-webcrawl/>`_ with `ArchiveBox <https://archivebox.io/>`_.
This allows your LLM (e.g. Claude Desktop) to search content and metadata from websites you've archived using ArchiveBox.

.. raw:: html

   <iframe width="560" height="315" src="https://www.youtube.com/embed/0KFqhSYf3f4" frameborder="0" allowfullscreen></iframe>

Follow along with the video, or the step-action guide below.

Requirements
------------

Before you begin, ensure you have:

- `Claude Desktop <https://claude.ai/download>`_ installed
- `Python <https://python.org>`_ 3.10 or later installed
- `ArchiveBox <https://archivebox.io/>`_ installed
- Basic familiarity with command line interfaces

What is ArchiveBox?
-------------------

ArchiveBox is a powerful open-source web archiving solution that offers:

- Multiple output formats (HTML, PDF, screenshots, WARC, etc.)
- Comprehensive metadata
- CLI + webadmin for browsing and managing archives
- Support for various input sources (URLs, browser bookmarks, RSS feeds)
- Self-hosted solution for long-term web content preservation

Installation Steps
------------------

1. Install mcp-server-webcrawl
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Open your terminal or command line and install the package::

    pip install mcp-server-webcrawl

Verify installation was successful::

    mcp-server-webcrawl --help

2. Install and Set Up ArchiveBox
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

macOS/Linux only, Windows may work under Docker but is untested.

1. Install ArchiveBox (macOS/Linux)::

    pip install archivebox

2. macOS only, install brew and wget::

    brew install wget

3. Create ArchiveBox collections. Unlike other crawlers that focus on single websites, ArchiveBox uses a collection-based approach where each collection can contain multiple URLs. You can create separate content for different projects or group related URLs together::

    # Create a directory structure for your collections
    mkdir ~/archivebox-data

    # Create an "example" collection
    mkdir ~/archivebox-data/example
    cd ~/archivebox-data/example
    archivebox init
    archivebox add https://example.com

    # Create a "pragmar" collection
    mkdir ~/archivebox-data/pragmar
    cd ~/archivebox-data/pragmar
    archivebox init
    archivebox add https://pragmar.com

4. Each ``archivebox init`` creates a complete ArchiveBox instance with its own database and archive directory structure. The typical structure includes::

    collection-name/
    ├── archive/          # Archived content organized by timestamp
    ├── logs/            # ArchiveBox operation logs
    ├── sources/         # Source URL lists and metadata
    └── index.sqlite3    # Database containing all metadata

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
          "args": ["--crawler", "archivebox", "--datasrc",
            "/path/to/archivebox-data/"]
        }
      }
    }

.. note::
   - On Windows, use ``"mcp-server-webcrawl"`` as the command
   - On macOS/Linux, use the absolute path (output of ``which mcp-server-webcrawl``)
   - The datasrc path should point to the parent directory containing your ArchiveBox collections (e.g., ``~/archivebox-data/``), not to individual collection directories
   - Each collection directory (example, pragmar, etc.) will appear as a separate "site" in MCP

4. Save the file and **completely exit** Claude Desktop (not just close the window)
5. Restart Claude Desktop

4. Verify and Use
~~~~~~~~~~~~~~~~~

1. In Claude Desktop, you should now see MCP tools available under Search and Tools
2. Ask Claude to list your archived sites::

    Can you list the crawled sites available?

3. Try searching content from your archives::

    Can you find information about [topic] on [archived site]?

4. Use the rich metadata for content discovery::

    Can you find all the archived pages related to [keyword] from [archive]?

Troubleshooting
---------------

- If Claude doesn't show MCP tools after restart, verify your configuration file is correctly formatted
- Ensure Python and mcp-server-webcrawl are properly installed
- Check that your ArchiveBox archive directory path in the configuration is correct
- Make sure ArchiveBox has successfully archived the websites and created the database
- Verify that files exist in your archive/[timestamp] directories
- Remember that the first time you use a function, Claude will ask for permission
- For large archives, initial indexing may take some time during the first search

ArchiveBox's comprehensive archiving capabilities combined with mcp-server-webcrawl provide powerful tools for content preservation, research, and analysis across your archived web content.

For more details, including API documentation and other crawler options, visit the `mcp-server-webcrawl documentation <https://github.com/pragmar/mcp-server-webcrawl>`_.