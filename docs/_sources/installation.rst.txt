Installation
============

Install the package via pip:

.. code-block:: bash

   pip install mcp-server-webcrawl

Requirements
------------

To use mcp-server-webcrawl effectively, you need:

* An MCP-capable LLM host such as Claude Desktop [1]
* Python [2] installed on your command line interface
* Basic familiarity with running Python packages

After ensuring these prerequisites are met, run the pip install command above to add the package to your environment.

MCP Configuration
-----------------

To enable your LLM host to access your web crawl data, you'll need to add an MCP server configuration. From Claude's developer settings, locate the MCP configuration section and add the appropriate configuration for your crawler type.

Setup guides and videos are available for each supported crawler:

* :doc:`ArchiveBox <guides/archivebox>`
* :doc:`HTTrack <guides/httrack>`
* :doc:`InterroBot <guides/interrobot>`
* :doc:`Katana <guides/katana>`
* :doc:`SiteOne <guides/siteone>`
* :doc:`WARC <guides/warc>`
* :doc:`Wget <guides/wget>`

Multiple Configurations
-----------------------

You can set up multiple **mcp-server-webcrawl** connections under the ``mcpServers`` section if you want to access different crawler data sources simultaneously.

.. code-block:: json

   {
     "mcpServers": {
       "webcrawl_warc": {
         "command": "/path/to/mcp-server-webcrawl",
          "args": ["--crawler", "warc", "--datasrc", "/path/to/warc/archives/"]
       },
       "webcrawl_wget": {
         "command": "/path/to/mcp-server-webcrawl",
          "args": ["--crawler", "wget", "--datasrc", "/path/to/wget/archives/"]
       }
     }
   }

After adding the configuration, save the file and restart your LLM host to apply the changes.

References
----------

[1] Claude Desktop: https://claude.ai
[2] Python: https://python.org