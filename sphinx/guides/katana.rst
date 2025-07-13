Katana MCP Setup Guide
======================

Instructions for setting up `mcp-server-webcrawl <https://pragmar.com/mcp-server-webcrawl/>`_ with `Katana <https://github.com/projectdiscovery/katana>`_ crawler.
This allows your LLM (e.g. Claude Desktop) to search content and metadata from websites you've crawled using Katana.

.. raw:: html

   <iframe width="560" height="315" src="https://www.youtube.com/embed/sOMaojm0R0Y" frameborder="0" allowfullscreen></iframe>

Follow along with the video, or the step-action guide below.

Requirements
------------

Before you begin, ensure you have:

- `Claude Desktop <https://claude.ai/download>`_ installed
- `Python <https://python.org>`_ 3.10 or later installed
- `Go programming language <https://go.dev/doc/install>`_ installed
- `Katana crawler <https://github.com/projectdiscovery/katana>`_ installed

- Basic familiarity with command line interfaces

What is Katana?
---------------

Katana is an open-source web crawler from Project Discovery that offers:

- Fast and efficient web crawling capabilities
- Command-line interface for flexibility and automation
- Highly configurable crawling parameters
- Ability to store complete HTTP responses for analysis

Installation Steps
------------------

1. Install MCP Server Web Crawl
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Open your terminal or command line and install the package::

    pip install mcp-server-webcrawl

Verify installation was successful::

    mcp-server-webcrawl --help

2. Install and Run Katana
~~~~~~~~~~~~~~~~~~~~~~~~~

1. Verify Go is installed and on your PATH::

    go version

2. Install Katana using Go::

    go install github.com/projectdiscovery/katana/cmd/katana@latest

3. Create a directory for your crawls and run Katana with storage options::

    # Create a directory for storing crawls
    mkdir crawls

    # Run Katana with storage options
    katana -u https://example.com -store-response -store-response-dir archives/example.com/

4. Repeat for additional websites as needed::

    katana -u https://pragmar.com -store-response -store-response-dir archives/pragmar.com/

In this case, the ./archives directory is the datasrc. The crawler will create
a separate host directory for each unique host within
the specified directory. This is consistent with the behavior of Katana,
example.com/example.com is expected. Sites with external dependencies will branch
out by origin host in the -store-response-dir, and continue to be searchable as a
singular site search.

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
          "args": ["--crawler", "katana", "--datasrc",
            "/path/to/katana/crawls/"]
        }
      }
    }

.. note::
   - On Windows, use ``"mcp-server-webcrawl"`` as the command
   - On macOS, use the absolute path (output of ``which mcp-server-webcrawl``)
   - Change ``/path/to/katana/crawls/`` to the actual path where you stored your Katana crawls

4. Save the file and **completely exit** Claude Desktop (not just close the window)
5. Restart Claude Desktop

4. Verify and Use
~~~~~~~~~~~~~~~~~

1. In Claude Desktop, you should now see MCP tools available under Search and Tools
2. Ask Claude to list your crawled sites::

    Can you list the crawled sites available?

3. Try searching content from your crawls::

    Can you find information about [topic] on [crawled site]?

4. Try specialized searches that use Katana's comprehensive data collection::

    Can you find all the help pages on this site and tell me how they're different?

Troubleshooting
---------------

- If Claude doesn't show MCP tools after restart, verify your configuration file is correctly formatted
- Ensure Python and mcp-server-webcrawl are properly installed
- Check that your Katana crawls directory path in the configuration is correct
- Make sure the ``-store-response`` flag was used during crawling, as this is required to save content
- Verify that each crawl completed successfully and files were saved to the expected location
- Remember that the first time you use a function, Claude will ask for permission

For more details, including API documentation and other crawler options, visit the `mcp-server-webcrawl documentation <https://github.com/pragmar/mcp-server-webcrawl>`_.