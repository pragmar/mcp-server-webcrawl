
from pathlib import Path

VALID_CRAWLER_CHOICES: list[str] = ["archivebox", "httrack", "interrobot", "katana", "siteone", "warc", "wget"]

def get_fixture_directory():
    modroot: Path = Path(__file__).parent.parent.parent.parent
    # assumes git project structure to locate fixtures
    assert modroot.name == "mcp-server-webcrawl", f"expected modroot mcp_server_webcrawl, got {modroot.name}"
    return modroot / "fixtures"

def get_crawler(crawler_name: str) -> str | None:
    """
    lazy load crawler, some classes have additional package dependencies
    """
    if crawler_name is None:
        return None
    crawler_name = crawler_name.lower()
    if crawler_name == "archivebox":
        from mcp_server_webcrawl.crawlers.archivebox.crawler import ArchiveBoxCrawler
        return ArchiveBoxCrawler
    elif crawler_name == "httrack":
        from mcp_server_webcrawl.crawlers.httrack.crawler import HtTrackCrawler
        return HtTrackCrawler
    elif crawler_name == "interrobot":
        from mcp_server_webcrawl.crawlers.interrobot.crawler import InterroBotCrawler
        return InterroBotCrawler
    elif crawler_name == "katana":
        from mcp_server_webcrawl.crawlers.katana.crawler import KatanaCrawler
        return KatanaCrawler
    elif crawler_name == "siteone":
        from mcp_server_webcrawl.crawlers.siteone.crawler import SiteOneCrawler
        return SiteOneCrawler
    elif crawler_name == "warc":
        from mcp_server_webcrawl.crawlers.warc.crawler import WarcCrawler
        return WarcCrawler
    elif crawler_name == "wget":
        from mcp_server_webcrawl.crawlers.wget.crawler import WgetCrawler
        return WgetCrawler
    else:
        valid_choices = ", ".join(VALID_CRAWLER_CHOICES)
        raise ValueError(f"unsupported crawler '{crawler_name}' ({valid_choices})")
