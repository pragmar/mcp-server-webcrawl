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

    def test_warc_random_sort(self):
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
        Test thumbnail generation functionality (InterroBot-specific).
        """
        crawler = WarcCrawler(self._datasrc)
        logger.info(self.run_pragmar_report(crawler, PRAGMAR_WARC_ID, "WARC"))
