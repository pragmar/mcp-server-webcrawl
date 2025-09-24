Interactive Mode
================

**No AI, just classic Boolean search of your web-archives in a terminal.**

mcp-server-webcrawl can double as a terminal search for your web archives. You can run it against your local archives, but it gets more interesting when you realize you can ssh into any remote host and view archives sitting on that host. No downloads, syncs, multifactor logins, or other common drudgery required. With interactive mode, you can be in and searching a crawl sitting on a remote server in no time at all.

.. raw:: html

   <iframe width="560" height="315" style="display: block;margin-bottom:1rem;" src="https://www.youtube.com/embed/8kNkP-zNzs4" frameborder="0" allowfullscreen></iframe>

Usage
-----

Interactive mode exposes the mcp-server-webcrawl search layer as a terminal UI (TUI), bypassing MCP/AI altogether. Core field and Boolean search are supported, along with the human-friendly aspects of the search interface, such as result snippets.

You launch interactive mode from the termial, using the --interactive command line argument.

.. code-block:: bash

   mcp-server-webcrawl --crawler wget --datasrc /path/to/datasrc --interactive
   # or manually enter crawler and datasrc in the UI
   mcp-server-webcrawl --interactive

Screencaps
----------

.. figure:: _static/images/interactive.search.webp
   :alt: mcp-server-webcrawl in --interactive mode heading
   :align: center
   :width: 100%

   Search view, showing snippets with "Solar Eclipse" highlights

.. figure:: _static/images/interactive.document.webp
   :alt: mcp-server-webcrawl in --interactive mode heading
   :align: center
   :width: 100%

   Document presentated in in Markdown, with raw and HTTP headers views available.