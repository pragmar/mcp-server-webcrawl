# Specialty Prompts

A collection of prompts for site analysis using mcp-server-webcrawl. The prompts are cut and paste, used as raw markdown.

If you want to shorcut the site selection (one less query), paste the prompt, adding "Can you audit [site name or URL]?" I don't know if these belong in the MCP layer or not. I think it may be more important to have the ability to adapt them easily. For now, at least, they're cut and paste.

## Available Website Audits

### 🔍 SEO Audit ([`auditseo.md`](https://raw.githubusercontent.com/pragmar/mcp-server-webcrawl/master/prompts/auditseo.md))

Technical search engine optimization analysis. Covers the basics, with options to dive deeper.

### 🔗 404 Audit ([`audit404.md`](https://raw.githubusercontent.com/pragmar/mcp-server-webcrawl/master/prompts/audit404.md))

Systematic broken link detection and pattern analysis. Not only finds issues, but suggests fixes.

### ⚡ Performance Audit ([`auditperf.md`](https://raw.githubusercontent.com/pragmar/mcp-server-webcrawl/master/prompts/auditperf.md))

Website speed and optimization analysis. Real talk.

### 📁 File Type Audit ([`auditfiles.md`](https://raw.githubusercontent.com/pragmar/mcp-server-webcrawl/master/prompts/auditfiles.md))

File organization and asset analysis. Discover the composition of your website.

## Available Interactive Modes

### 🌐 Gopher Service ([`gopher.md`](https://raw.githubusercontent.com/pragmar/mcp-server-webcrawl/master/prompts/gopher.md))

An old-fashioned search interface inspired by the Gopher clients of yesteryear.

## Available Tests

### ⚙️ **Boolean Search Self-Test** ([`testsearch.md`](https://raw.githubusercontent.com/pragmar/mcp-server-webcrawl/master/prompts/testsearch.md))

A battery of tests to check for Boolean logical inconsistencies in the search query parser and subsequent FTS5 conversion.