from pathlib import Path

from mcp.server.stdio import stdio_server

from mcp_server_webcrawl.crawlers.base.crawler import BaseCrawler
from mcp_server_webcrawl.utils.logger import get_logger, initialize_logger
from mcp_server_webcrawl.utils.server import initialize_mcp_server

logger = get_logger()

async def main(crawler: BaseCrawler, datasrc: Path):
    initialize_logger()
    initialize_mcp_server()
    async with stdio_server() as (read_stream, write_stream):
        crawler = crawler(datasrc)
        logger.info(f"MCP webcrawl server initialized with adapter {crawler.__class__.__name__}")
        logger.info(f"datasrc: {datasrc.absolute()}")
        await crawler.serve(read_stream, write_stream)
        logger.info("MCP webcrawl server exited")
