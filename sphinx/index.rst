.. image:: _static/images/mcpswc.svg
   :alt: mcp-server-webcrawl heading
   :align: center
   :width: 100%

.. raw:: html

   <div style="text-align: center; margin-bottom: 2em;">
     <a href="https://pragmar.com/mcp-server-webcrawl/" style="margin: 0 4px;">Website</a> |
     <a href="https://github.com/pragmar/mcp-server-webcrawl" style="margin: 0 4px;">Github</a> |
     <a href="https://pragmar.github.io/mcp-server-webcrawl/" style="margin: 0 4px;">Docs</a> |
     <a href="https://pypi.org/project/mcp-server-webcrawl/" style="margin: 0 4px;">PyPi</a>

   </div>

mcp-server-webcrawl
===============================================

Bridge the gap between your web crawl and AI language models using Model Context Protocol (MCP). 
With **mcp-server-webcrawl**, your AI client filters and analyzes web content under your direction or autonomously. The 
server includes a full-text search interface with boolean support, resource filtering by type, HTTP status, 
and more. 

**mcp-server-webcrawl** provides the LLM a complete menu with which to search your web content, and works with
a variety of web crawlers:

* `WARC <https://en.wikipedia.org/wiki/WARC_(file_format)>`_
* `wget <https://en.wikipedia.org/wiki/Wget>`_
* `InterroBot <https://interro.bot>`_
* `Katana <https://github.com/projectdiscovery/katana>`_
* `SiteOne <https://crawler.siteone.io>`_

**mcp-server-webcrawl** is free and open source, and requires Claude Desktop, Python (>=3.10). It is installed on the command line, via pip install:

.. code-block:: bash

   pip install mcp-server-webcrawl


.. toctree::
   :maxdepth: 1
   :caption: Contents:

   installation
   guides
   usage
   modules

Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`