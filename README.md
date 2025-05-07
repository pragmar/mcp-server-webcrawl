<p align="center">
  <img src="sphinx/_static/images/mcpswc.svg" alt="MCP Server Webcrawl" width="100%">
</p>

<p align="center">
  <a href="https://pragmar.com/mcp-server-webcrawl/" style="margin: 0 10px;">Website</a> |
  <a href="https://github.com/pragmar/mcp_server_webcrawl" style="margin: 0 10px;">Github</a> |
  <a href="https://pragmar.github.io/mcp_server_webcrawl/" style="margin: 0 10px;">Docs</a>
</p>

# mcp-server-webcrawl

Bridge the gap between your web crawl and AI language models using Model Context Protocol (MCP). 
With **mcp-server-webcrawl**, your AI client filters and analyzes web content under your direction or autonomously. The server includes a full-text search interface with boolean support, resource filtering by type, HTTP status, 
and more. 

**mcp-server-webcrawl** provides the LLM a complete menu with which to search your web content, and works with
a variety of web crawlers:

* [WARC](https://en.wikipedia.org/wiki/WARC_(file_format))
* [wget](https://en.wikipedia.org/wiki/Wget)
* [InterroBot](https://interro.bot)
* [Katana](https://github.com/projectdiscovery/katana)
* [SiteOne](https://crawler.siteone.io)

**mcp-server-webcrawl** is free and open source, and requires Claude Desktop, Python (>=3.10). It is installed on the command line, via pip install:

```bash
pip install mcp-server-webcrawl
```

## Features

* Claude Desktop ready
* Fulltext search support
* Filter by type, status, and more
* Multi-crawler compatible
* Quick MCP configuration
* ChatGPT support coming soon

## MCP Configuration

From the Claude Desktop menu, navigate to File > Settings > Developer. Click Edit Config to locate the configuration file, open in the editor of your choice and modify the example to reflect your datasrc path.

You can set up more mcp-server-webcrawl connections under mcpServers as needed.

```json
{ 
  "mcpServers": {
    "webcrawl": {
      "command": "mcp-server-webcrawl",
       "args": [varies by crawler, see below]
    }
  }
}
```

### Important Note for macOS Users

On macOS, you must use the absolute path to the `mcp-server-webcrawl` executable in the `command` field, rather than just the command name. This is different from Windows/Linux configuration.

For example:

```json
{ 
  "mcpServers": {
    "webcrawl": {
      "command": "/Users/yourusername/.local/bin/mcp-server-webcrawl",
      "args": [varies by crawler, see below]
    }
  }
}
```

To find the absolute path of the `mcp-server-webcrawl` executable on your system:

1. Open Terminal
2. Run `which mcp-server-webcrawl`
3. Copy the full path returned and use it in your config file

The location may vary depending on how Python and pip are configured on your system, but common locations include:
* `/Users/yourusername/.local/bin/mcp-server-webcrawl`
* `/usr/local/bin/mcp-server-webcrawl`
* `/opt/homebrew/bin/mcp-server-webcrawl` (if installed via Homebrew)

### wget (using --mirror)

The datasrc argument should be set to the parent directory of the mirrors.

```
"args": ["--crawler", "wget", "--datasrc", "/path/to/wget/archives/"]
```

### WARC

The datasrc argument should be set to the parent directory of the WARC files.

```
"args": ["--crawler", "warc", "--datasrc", "/path/to/warc/archives/"]
```

### InterroBot

The datasrc argument should be set to the direct path to the database.

```
"args": ["--crawler", "interrobot", "--datasrc", "/path/to/Documents/InterroBot/interrobot.v2.db"]
```

### Katana

The datasrc argument should be set to the parent directory of the text cache files.

```
"args": ["--crawler", "katana", "--datasrc", "/path/to/katana/archives/"]
```

### SiteOne (using archiving)

The datasrc argument should be set to the parent directory of the archives, archiving must be enabled.

```
"args": ["--crawler", "siteone", "--datasrc", "/path/to/SiteOne/archives/"]
```
