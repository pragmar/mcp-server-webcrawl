# Prompt Routines

**mcp-server-webcrawl** provides the toolkit necessary to search web crawl data freestyle, figuring it out as you go, reacting to each query. This is what it was designed for.

It is also capable of running routines (as prompts). You can write these yourself, or use the ones provided. These prompts are **copy and paste**, and used as raw Markdown. They are enabled by the advanced search provided to the LLM; queries and logic can be embedded in a procedural set of instructions, or even an input loop as is the case with Gopher Service.

If you want to shortcut the site selection (one less query), paste the Markdown and in the same request, type "run pasted for [site name or URL]." It will figure it out. When pasted without additional context, you will be prompted to select a site (if no site is in context).

| Prompt | Download | Category | Description |
|--------|----------|----------|-------------|
|🔍 **SEO Audit** | [`auditseo.md`](https://raw.githubusercontent.com/pragmar/mcp-server-webcrawl/master/prompts/auditseo.md) | audit | Technical SEO (search engine optimization) analysis. Covers the basics, with options to dive deeper. |
|🔗 **404 Audit** | [`audit404.md`](https://raw.githubusercontent.com/pragmar/mcp-server-webcrawl/master/prompts/audit404.md) | audit | Broken link detection and pattern analysis. Not only finds issues, but suggests fixes. |
|⚡&nbsp;**Performance&nbsp;Audit** | [`auditperf.md`](https://raw.githubusercontent.com/pragmar/mcp-server-webcrawl/master/prompts/auditperf.md) | audit | Website speed and optimization analysis. Real talk. |
|📁 **File Audit** | [`auditfiles.md`](https://raw.githubusercontent.com/pragmar/mcp-server-webcrawl/master/prompts/auditfiles.md) | audit | File organization and asset analysis. Discover the composition of your website. |
|🌐 **Gopher Interface** | [`gopher.md`](https://raw.githubusercontent.com/pragmar/mcp-server-webcrawl/master/prompts/gopher.md) | interface | An old-fashioned search interface inspired by the Gopher clients of yesteryear. |
|⚙️ **Search Test** | [`testsearch.md`](https://raw.githubusercontent.com/pragmar/mcp-server-webcrawl/master/prompts/testsearch.md) | self-test | A battery of tests to check for Boolean logical inconsistencies in the search query parser and subsequent FTS5 conversion. |

