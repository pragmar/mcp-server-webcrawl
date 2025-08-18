from pathlib import Path

from mcp_server_webcrawl.crawlers.base.indexed import IndexedCrawler
from mcp_server_webcrawl.crawlers.wget.adapter import get_sites, get_resources
from mcp_server_webcrawl.utils.logger import get_logger

logger = get_logger()

class WgetCrawler(IndexedCrawler):
    """
    A crawler implementation for wget captured sites.
    Provides functionality for accessing and searching web content from wget captures.
    """

    def __init__(self, datasrc: Path):
        """
        Initialize the wget crawler with a data source directory.

        Args:
            datasrc: the input argument as Path, it must be a directory containing
                wget captures organized as subdirectories

        Raises:
            AssertionError: If datasrc is None or not a directory
        """
        assert datasrc is not None, f"WgetCrawler needs a datasrc, regardless of action"
        assert datasrc.is_dir(), "WgetCrawler datasrc must be a directory"

        super().__init__(datasrc, get_sites, get_resources)
