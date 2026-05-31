from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from mcp_server_webcrawl.crawlers import get_crawler
from mcp_server_webcrawl.crawlers.base.crawler import BaseCrawler
from mcp_server_webcrawl.models.sites import SiteResult

@dataclass
class AppConfig:
    """
    A crawler/datasrc pairing with live objects loaded from it.
    Produced by the requirements screen (or at startup from CLI args) and consumed
    by the session to build/rebuild UI. 
    """

    crawler_name: str
    datasrc: str
    crawler: Optional[BaseCrawler] = None
    sites: list[SiteResult] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        """
        True when a crawler was successfully built and the app can search.
        """
        return self.crawler is not None

    @classmethod
    def empty(cls) -> "AppConfig":
        """
        An unconfigured placeholder used before requirements are satisfied.
        """
        return cls(crawler_name="", datasrc="")

    @classmethod
    def load(cls, crawler_name: str, datasrc: str) -> "AppConfig":
        """
        Build a crawler from the given inputs and fetch its sites.

        Returns a not-ready config if the crawler can't be resolved or built;
        callers check .ready rather than catching here.
        """
        crawl_model = get_crawler(crawler_name)
        if crawl_model is None:
            return cls(crawler_name=crawler_name, datasrc=datasrc)

        try:
            crawler: BaseCrawler = crawl_model(Path(datasrc))
            sites: list[SiteResult] = crawler.get_sites_api().get_results()
        except Exception:
            return cls(crawler_name=crawler_name, datasrc=datasrc)

        return cls(crawler_name=crawler_name, datasrc=datasrc, crawler=crawler, sites=sites)
