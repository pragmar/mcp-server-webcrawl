HTTrack MCP Setup Guide
========================

Instructions for setting up `mcp-server-webcrawl <https://pragmar.com/mcp-server-webcrawl/>`_ with `HTTrack Website Copier <https://www.httrack.com/>`_.
This allows your LLM (e.g. Claude Desktop) to search content and metadata from websites you've mirrored using HTTrack.

.. raw:: html

   <iframe width="560" height="315" src="https://www.youtube.com/embed/HAVfvmrZjRk" frameborder="0" allowfullscreen></iframe>

Follow along with the video, or the step-action guide below.

Requirements
------------

Before you begin, ensure you have:

- `Claude Desktop <https://claude.ai/download>`_ installed
- `Python <https://python.org>`_ 3.10 or later installed
- `HTTrack Website Copier <https://www.httrack.com/>`_ installed
- Basic familiarity with command line interfaces

What is HTTrack?
----------------

HTTrack is a well-established open source website mirror tool that offers:

- Complete website mirroring with organized project directories
- User-friendly wizard-style interface for setup
- Comprehensive content capture including HTML, CSS, images, and other assets
- Ability to manage multiple site mirrors efficiently
- Cross-platform support (Windows, macOS, Linux)

Installation Steps
------------------

1. Install MCP Server Web Crawl
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Open your terminal or command line and install the package::

    pip install mcp-server-webcrawl

Verify installation was successful::

    mcp-server-webcrawl --help

2. Create Website Mirrors with HTTrack
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. Open HTTrack Website Copier application
2. Create a new project (e.g., "example") and specify where to save it
3. Add the URL you want to mirror (e.g., https://example.com)
4. Use the wizard interface to configure your crawling options
5. Start the mirroring process and wait for completion
6. Repeat for additional sites as needed (e.g., create another project for pragmar.com)

HTTrack will create organized project directories under your specified location (typically "My Web Sites" on Windows or "websites" on macOS/Linux). Each project contains the complete website mirror with all HTML files, images, CSS, and other assets properly organized.

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
          "args": ["--crawler", "httrack", "--datasrc",
            "/path/to/httrack/projects/"]
        }
      }
    }

.. note::
   - On macOS/Linux, use the absolute path (output of ``which mcp-server-webcrawl``), and the default path is typically ``"~/websites"``
   - The datasrc path should point to your HTTrack project directory containing all your mirrored sites

4. Save the file and **completely exit** Claude Desktop (not just close the window)
5. Restart Claude Desktop

4. Verify and Use
~~~~~~~~~~~~~~~~~

1. In Claude Desktop, you should now see MCP tools available under Search and Tools
2. Ask Claude to list your crawled sites::

    Can you list the crawled sites available?

3. Try searching content from your crawls::

    Can you find information about [topic] on [crawled site]?

4. Conduct content audits and SEO analysis::

    Can you analyze the content structure and SEO elements for [crawled site]?

Troubleshooting
---------------

- If Claude doesn't show MCP tools after restart, verify your configuration file is correctly formatted
- Ensure Python and mcp-server-webcrawl are properly installed
- Check that your HTTrack project directory path in the configuration is correct
- Make sure HTTrack has successfully completed mirroring the websites and created the project directories
- Remember that the first time you use a function, Claude will ask for permission
- For large websites, initial indexing may take some time during the first search

HTTrack's project structure makes it easy to manage multiple site mirrors, and when combined with mcp-server-webcrawl, provides for content analysis, SEO audits, and searchable archives.

For more details, including API documentation and other crawler options, visit the `mcp-server-webcrawl documentation <https://github.com/pragmar/mcp-server-webcrawl>`_.