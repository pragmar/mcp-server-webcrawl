from mcp_server_webcrawl.crawlers import get_fixture_directory
from mcp_server_webcrawl.crawlers.wget.adapter import WgetManager
from mcp_server_webcrawl.crawlers.wget.crawler import WgetCrawler
from mcp_server_webcrawl.crawlers.base.tests import BaseCrawlerTests
from mcp_server_webcrawl.utils.logger import get_logger

logger = get_logger()

EXAMPLE_SITE_ID = WgetManager.string_to_id("example.com")
PRAGMAR_SITE_ID = WgetManager.string_to_id("pragmar.com")

class WgetTests(BaseCrawlerTests):
    """
    Test suite for the wget crawler implementation.
    Uses all wrapped test methods from BaseCrawlerTests.
    """

    def setUp(self):
        """
        Set up the test environment with fixture data.
        """
        super().setUp()
        self._datasrc = get_fixture_directory() / "wget"

    def test_wget_pulse(self):
        """
        Test basic crawler initialization.
        """
        crawler = WgetCrawler(self._datasrc)
        self.assertIsNotNone(crawler)
        self.assertTrue(self._datasrc.is_dir())

    def test_wget_sites(self):
        """
        Test site retrieval API functionality.
        """
        crawler = WgetCrawler(self._datasrc)
        self.run_pragmar_site_tests(crawler, PRAGMAR_SITE_ID)

    def test_wget_search(self):
        """
        Test boolean search functionality
        """
        crawler = WgetCrawler(self._datasrc)
        self.run_pragmar_search_tests(crawler, PRAGMAR_SITE_ID)

    def test_wget_resources(self):
        """
        Test resource retrieval API functionality with various parameters.
        """
        crawler = WgetCrawler(self._datasrc)
        self.run_sites_resources_tests(crawler, PRAGMAR_SITE_ID, EXAMPLE_SITE_ID)


    def test_wget_random_sort(self):
        """
        Test random sort functionality using the '?' sort parameter.
        """
        crawler = WgetCrawler(self._datasrc)
        self.run_pragmar_sort_tests(crawler, PRAGMAR_SITE_ID)

    def test_wget_content_parsing(self):
        """
        Test content type detection and parsing.
        """
        crawler = WgetCrawler(self._datasrc)
        self.run_pragmar_content_tests(crawler, PRAGMAR_SITE_ID, False)

    def test_report(self):
        """
        Test thumbnail generation functionality (InterroBot-specific).
        """
        crawler = WgetCrawler(self._datasrc)
        logger.info(self.run_pragmar_report(crawler, PRAGMAR_SITE_ID, "wget"))
