from pathlib import Path

from mcp_server_webcrawl.crawlers.base.indexed import IndexedCrawler
from mcp_server_webcrawl.crawlers.katana.adapter import get_sites, get_resources
from mcp_server_webcrawl.utils.logger import get_logger

logger = get_logger()

class KatanaCrawler(IndexedCrawler):
    """
    A crawler implementation for HTTP text files.
    Provides functionality for accessing and searching web content from captured HTTP exchanges.
    """

    def __init__(self, datasrc: Path):
        """
        Initialize the HTTP text crawler with a data source directory.

        Args:
            datasrc: The input argument as Path, it must be a directory containing
                subdirectories with HTTP text files
        """
        super().__init__(datasrc, get_sites, get_resources)
