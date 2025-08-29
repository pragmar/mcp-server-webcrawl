from pathlib import Path

from mcp_server_webcrawl.crawlers.base.indexed import IndexedCrawler
from mcp_server_webcrawl.crawlers.httrack.adapter import get_sites, get_resources
from mcp_server_webcrawl.utils.logger import get_logger

logger = get_logger()

class HtTrackCrawler(IndexedCrawler):
    """
    A crawler implementation for HTTrack captured sites.
    Provides functionality for accessing and searching web content from HTTrack projects.
    HTTrack creates offline mirrors of websites with preserved directory structure
    and metadata in hts-log.txt files.
    """

    def __init__(self, datasrc: Path):
        """
        Initialize the HTTrack crawler with a data source directory.

        Args:
            datasrc: The input argument as Path, it must be a directory containing
                HTTrack project directories, each potentially containing multiple domains

        Raises:
            AssertionError: If datasrc is None or not a directory
        """
        assert datasrc is not None, f"HtTrackCrawler needs a datasrc, regardless of action"
        assert datasrc.is_dir(), "HtTrackCrawler datasrc must be a directory"

        super().__init__(datasrc, get_sites, get_resources)
