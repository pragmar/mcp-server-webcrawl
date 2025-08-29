from pathlib import Path

from mcp_server_webcrawl.crawlers.base.indexed import IndexedCrawler
from mcp_server_webcrawl.crawlers.archivebox.adapter import get_sites, get_resources
from mcp_server_webcrawl.utils.logger import get_logger

logger = get_logger()

class ArchiveBoxCrawler(IndexedCrawler):
    """
    A crawler implementation for ArchiveBox archived sites.
    Provides functionality for accessing and searching web content from ArchiveBox archives.
    ArchiveBox creates single-URL archives with metadata stored in JSON files
    and HTML content preserved in index.html files.
    """

    def __init__(self, datasrc: Path):
        """
        Initialize the ArchiveBox crawler with a data source directory.

        Args:
            datasrc: The input argument as Path, it must be a directory containing
                ArchiveBox archive directories, each containing individual URL entries

        Raises:
            AssertionError: If datasrc is None or not a directory
        """
        assert datasrc is not None, f"ArchiveBoxCrawler needs a datasrc, regardless of action"
        assert datasrc.is_dir(), "ArchiveBoxCrawler datasrc must be a directory"

        super().__init__(datasrc, get_sites, get_resources)