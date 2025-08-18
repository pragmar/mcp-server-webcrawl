from pathlib import Path

from mcp_server_webcrawl.crawlers.base.indexed import IndexedCrawler
from mcp_server_webcrawl.crawlers.siteone.adapter import get_sites, get_resources
from mcp_server_webcrawl.utils.logger import get_logger

logger = get_logger()

class SiteOneCrawler(IndexedCrawler):
    """
    A crawler implementation for SiteOne captured sites.
    Provides functionality for accessing and searching web content from SiteOne captures.
    SiteOne merges a wget archive with a custom SiteOne generated log to aquire more
    fields than wget can alone.
    """

    def __init__(self, datasrc: Path):
        """
        Initialize the SiteOne crawler with a data source directory.

        Args:
            datasrc: The input argument as Path, it must be a directory containing
                SiteOne captures organized as subdirectories

        Raises:
            AssertionError: If datasrc is None or not a directory
        """
        assert datasrc is not None, f"SiteOneCrawler needs a datasrc, regardless of action"
        assert datasrc.is_dir(), "SiteOneCrawler datasrc must be a directory"

        super().__init__(datasrc, get_sites, get_resources)
