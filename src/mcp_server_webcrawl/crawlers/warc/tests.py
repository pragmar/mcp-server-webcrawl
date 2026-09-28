import io
import tempfile

from pathlib import Path
from warcio.statusandheaders import StatusAndHeaders
from warcio.warcwriter import WARCWriter

from mcp_server_webcrawl.crawlers.warc.crawler import WarcCrawler
from mcp_server_webcrawl.crawlers.warc.adapter import WarcManager
from mcp_server_webcrawl.crawlers.base.tests import BaseCrawlerTests
from mcp_server_webcrawl.crawlers import get_fixture_directory
from mcp_server_webcrawl.utils.logger import get_logger

EXAMPLE_WARC_ID: int = WarcManager.string_to_id("example.warc.gz")
PRAGMAR_WARC_ID: int = WarcManager.string_to_id("pragmar.warc.gz")

logger = get_logger()

class WarcTests(BaseCrawlerTests):
    """
    Test suite for the WARC crawler implementation.
    Uses all wrapped test methods from BaseCrawlerTests.
    """

    def setUp(self):
        """
        Set up the test environment with fixture data.
        """
        super().setUp()
        self._datasrc = get_fixture_directory() / "warc"

    def test_warc_pulse(self):
        """
        Test basic crawler initialization.
        """
        crawler = WarcCrawler(self._datasrc)
        self.assertIsNotNone(crawler)
        self.assertTrue(self._datasrc.is_dir())

    def test_warc_sites(self):
        """
        Test site retrieval API functionality.
        """
        crawler = WarcCrawler(self._datasrc)
        self.run_pragmar_site_tests(crawler, PRAGMAR_WARC_ID)

    def test_warc_search(self):
        """
        Test boolean search functionality
        """
        crawler = WarcCrawler(self._datasrc)
        self.run_pragmar_search_tests(crawler, PRAGMAR_WARC_ID)

    def test_warc_resources(self):
        """
        Test resource retrieval API functionality with various parameters.
        """
        crawler = WarcCrawler(self._datasrc)
        self.run_sites_resources_tests(crawler, PRAGMAR_WARC_ID, EXAMPLE_WARC_ID)

    # pragmar WARC fixture legit contains no images
    # may be default behavior of wget WARC gen, not sure
    # this is a blind spot
    # def test_interrobot_images(self):
    #     """
    #     Test InterroBot-specific image handling and thumbnails.
    #     """
    #     crawler = WarcCrawler(self._datasrc)
    #     self.run_pragmar_image_tests(crawler, PRAGMAR_WARC_ID)

    def test_warc_duplicate_urls(self):
        """
        Two snapshots of one website, searched together, and a repeated capture within
        one file. A duplicate URL once failed the batch insert, and the rollback took
        every other resource in the batch with it.
        """
        with tempfile.TemporaryDirectory() as temp_directory:
            datasrc: Path = Path(temp_directory)
            self.__write_warc(datasrc / "snapshot-2025.warc", [
                ("https://example.com/", "old home"),
                ("https://example.com/about", "old about"),
            ])
            self.__write_warc(datasrc / "snapshot-2026.warc", [
                ("https://example.com/", "new home"),
                ("https://example.com/about", "new about"),
                ("https://example.com/about", "about, captured twice"),
                ("https://example.com/new", "brand new page"),
            ])
            crawler = WarcCrawler(datasrc)
            snapshot_2025: int = WarcManager.string_to_id("snapshot-2025.warc")
            snapshot_2026: int = WarcManager.string_to_id("snapshot-2026.warc")

            all_results = crawler.get_resources_api(fields=["content"], limit=20).get_results()
            contents: set[tuple[int, str]] = {(r.site, r.content) for r in all_results}
            self.assertEqual(contents, {
                (snapshot_2025, "old home"), (snapshot_2025, "old about"),
                (snapshot_2026, "new home"), (snapshot_2026, "new about"), (snapshot_2026, "brand new page"),
            }, "both snapshots indexed in full, first capture of a repeated URL wins")

    def __write_warc(self, path: Path, pages: list[tuple[str, str]]) -> None:
        with open(path, "wb") as output:
            writer: WARCWriter = WARCWriter(output, gzip=False)
            for url, body in pages:
                http_headers = StatusAndHeaders("200 OK", [("Content-Type", "text/html")], protocol="HTTP/1.1")
                record = writer.create_warc_record(url, "response", payload=io.BytesIO(body.encode("utf-8")),
                        http_headers=http_headers)
                writer.write_record(record)

    def test_warc_sorts(self):
        """
        Test random sort functionality using the '?' sort parameter.
        """
        crawler = WarcCrawler(self._datasrc)
        self.run_pragmar_sort_tests(crawler, PRAGMAR_WARC_ID)

    def test_warc_content_parsing(self):
        """
        Test content type detection and parsing for WARC files.
        """
        crawler = WarcCrawler(self._datasrc)
        self.run_pragmar_content_tests(crawler, PRAGMAR_WARC_ID, True)

    def test_report(self):
        """
        Run test report, save to data directory.
        """
        crawler = WarcCrawler(self._datasrc)
        logger.info(self.run_pragmar_report(crawler, PRAGMAR_WARC_ID, "WARC"))
