from pathlib import Path

from mcp_server_webcrawl.crawlers.base.indexed import IndexedCrawler
from mcp_server_webcrawl.crawlers.warc.adapter import get_sites, get_resources
from mcp_server_webcrawl.utils.logger import get_logger

logger = get_logger()

class WarcCrawler(IndexedCrawler):
    """
    A crawler implementation for WARC (Web ARChive) files.
    Provides functionality for accessing and searching web archive content.
    """

    def __init__(self, datasrc: Path):
        """
        Initialize the WARC crawler with a data source directory.
        Supported file types: .txt, .warc, and .warc.gz

        Args:
            datasrc: the input argument as Path, must be a directory containing WARC files


        Raises:
            AssertionError: If datasrc is None or not a directory
        """
        assert datasrc is not None, f"WarcCrawler needs a datasrc, regardless of action"
        assert datasrc.is_dir(), "WarcCrawler datasrc must be a directory"
        super().__init__(datasrc, get_sites, get_resources)
