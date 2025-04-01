# mcp-server-webcrawl

Bridge the gap between your web crawl and AI language models using Model Context Protocol (MCP). With mcp-server-webcrawl, your AI client filters and analyzes web content under your direction or autonomously, extracting insights from your web content.

Support for WARC, wget, InterroBot, Katana, and SiteOne crawlers is available out of the gate. The server includes a full-text search interface with boolean support, resource filtering by type, HTTP status, and more. mcp-server-webcrawl provides the LLM a complete menu with which to search your web content.

mcp-server-webcrawl requires Claude Desktop, Python (>=3.10), and can be installed via pip install:

pip install mcp-server-webcrawl

Features:

* Claude Desktop ready
* Fulltext search support
* Filter by type, status, and more
* Multi-crawler compatible
* Quick MCP configuration
* ChatGPT support coming soon

## MCP Configuration

From the Claude Desktop menu, navigate to File > Settings > Developer. Click Edit Config to locate the configuration file, open in the editor of your choice and modify the example to reflect your datasrc path.

You can set up more mcp-server-webcrawl connections under mcpServers as needed.

```
{ 
  "mcpServers": {
    "webcrawl": {
      "command": "mcp-server-webcrawl",
       "args": [varies by crawler, see below]
    }
  }
}
```

### wget (using --mirror)

The datasrc argument should be set to the parent directory of the mirrors.

`"args": ["--crawler", "wget", "--datasrc", "/path/to/wget/archives/"]`

### WARC

The datasrc argument should be set to the parent directory of the WARC files.

`"args": ["--crawler", "warc", "--datasrc", "/path/to/warc/archives/"]`

### InterroBot

The datasrc argument should be set to the direct path to the database.

`"args": ["--crawler", "interrobot", "--datasrc", "/path/to/Documents/InterroBot/interrobot.v2.db"]`

### Katana

The datasrc argument should be set to the parent directory of the text cache files.

`"args": ["--crawler", "katana", "--datasrc", "/path/to/katana/archives/"]`

### SiteOne (using archiving)

The datasrc argument should be set to the parent directory of the archives, archiving must be enabled.

`"args": ["--crawler", "katana", "--datasrc", "/path/to/SiteOne/archives/"]`