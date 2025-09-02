Installation
============

Install the package via pip:

.. code-block:: bash

   pip install mcp-server-webcrawl

Requirements
------------

To use mcp-server-webcrawl effectively, you need:

* An MCP-capable LLM host such as `Claude Desktop`_
* `Python`_ installed on your command line interface
* Basic familiarity with running Python packages

After ensuring these prerequisites are met, run the pip install command above to add the package to your environment.

MCP Configuration
-----------------

To enable your LLM host to access your web crawl data, you'll need to add an MCP server configuration. From Claude's developer settings, locate the MCP configuration section and add the appropriate configuration for your crawler type.

Below are configurations for each supported crawler type. Choose the one that matches your crawler and modify the ``--datasrc`` path to point to your specific data location.

wget
~~~~~~~~~~~~~~~~~~~

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

**Tested wget commands:**

.. code-block:: bash

   # (macOS Terminal/Windows WSL)
   # --adjust-extension for file extensions, e.g. *.html
   $ wget --mirror https://example.com
   $ wget --mirror https://example.com --adjust-extension


WARC
~~~~~~~~~~~~~~~~~~~

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

**Tested WARC commands:**

.. code-block:: bash

   # (macOS Terminal/Windows WSL)
   $ wget --warc-file=example --recursive https://example.com
   $ wget --warc-file=example --recursive --page-requisites https://example.com


InterroBot
~~~~~~~~~~~~~~~~~~~

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

**Notes for InterroBot:**

* Crawls must be executed in InterroBot (windowed application)
* On Windows: replace [homedir] with /Users/...
* On macOS: path is provided on InterroBot settings page


Katana
~~~~~~~~~~~~~~~~~~~

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

**Tested Katana commands:**

.. code-block:: bash

   # (macOS Terminal/Powershell/WSL)
   # -store-response to save crawl contents
   # -store-response-dir for expansion of hosts
   # &nbsp; consistent with default Katana behavior to
   # &nbsp; spread assets across origin host directories

   $ katana -u https://example.com -store-response -store-response-dir crawls/example.com/


SiteOne
~~~~~~~~~~~~~~~~~~~

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

**Notes for SiteOne:**

* Crawls must be executed in SiteOne (windowed application)
* *Generate offline website* must be checked

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



.. _Claude Desktop: https://claude.ai
.. _Python: https://python.org