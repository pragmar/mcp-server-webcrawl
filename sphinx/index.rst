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

Advanced search and retrieval for web crawler data. With **mcp-server-webcrawl**, your AI client filters
and analyzes web content under your direction or autonomously. The server includes a full-text search
interface with boolean support, and resource filtering by type, HTTP status, and more.

**mcp-server-webcrawl** provides the LLM a complete menu with which to search your web content, and works with
a variety of web crawlers:

.. list-table:: Supported Crawlers
   :header-rows: 1
   :widths: 30 50 20

   * - Crawler/Format
     - Description
     - Setup Guide
   * - `ArchiveBox <https://archivebox.io>`_
     - Self-hosted web archiving tool
     - `Setup Guide <https://pragmar.github.io/mcp-server-webcrawl/guides/archivebox.html>`_
   * - `HTTrack <https://www.httrack.com>`_
     - GUI/CLI website mirroring tool
     - `Setup Guide <https://pragmar.github.io/mcp-server-webcrawl/guides/httrack.html>`_
   * - `InterroBot <https://interro.bot>`_
     - GUI crawler and analyzer
     - `Setup Guide <https://pragmar.github.io/mcp-server-webcrawl/guides/interrobot.html>`_
   * - `Katana <https://github.com/projectdiscovery/katana>`_
     - CLI security-focused crawler
     - `Setup Guide <https://pragmar.github.io/mcp-server-webcrawl/guides/katana.html>`_
   * - `SiteOne <https://crawler.siteone.io>`_
     - GUI crawler and analyzer
     - `Setup Guide <https://pragmar.github.io/mcp-server-webcrawl/guides/siteone.html>`_
   * - `WARC <https://en.wikipedia.org/wiki/WARC_(file_format)>`_
     - Standard web archive format
     - `Setup Guide <https://pragmar.github.io/mcp-server-webcrawl/guides/warc.html>`_
   * - `wget <https://en.wikipedia.org/wiki/Wget>`_
     - CLI website mirroring tool
     - `Setup Guide <https://pragmar.github.io/mcp-server-webcrawl/guides/wget.html>`_

**mcp-server-webcrawl** is free and open source, and requires Claude Desktop, Python (>=3.10). It is installed on the command line, via pip install:

.. code-block:: bash

   pip install mcp-server-webcrawl

.. raw:: html

   <iframe width="560" height="315" style="display: block;margin-bottom:1rem;" src="https://www.youtube.com/embed/Sid-GBxII1o" frameborder="0" allowfullscreen></iframe>


.. toctree::
   :maxdepth: 1
   :caption: Contents:

   installation
   guides
   usage
   prompts
   interactive
   modules

Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`