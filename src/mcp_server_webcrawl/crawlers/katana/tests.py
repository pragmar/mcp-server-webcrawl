from logging import Logger
from mcp_server_webcrawl.crawlers.katana.crawler import KatanaCrawler
from mcp_server_webcrawl.crawlers.katana.adapter import KatanaManager
from mcp_server_webcrawl.crawlers.base.adapter import SitesGroup
from mcp_server_webcrawl.crawlers.base.tests import BaseCrawlerTests
from mcp_server_webcrawl.crawlers import get_fixture_directory
from mcp_server_webcrawl.utils.logger import get_logger

# calculate ids for test directories using the same hash function as adapter
EXAMPLE_SITE_ID = KatanaManager.string_to_id("example.com")
PRAGMAR_SITE_ID = KatanaManager.string_to_id("pragmar.com")

logger: Logger = get_logger()

class KatanaTests(BaseCrawlerTests):
    """
    test suite for the HTTP text crawler implementation.
    tests parsing and retrieval of web content from HTTP text files.
    """

    def setUp(self):
        """
        set up the test environment with fixture data.
        """
        super().setUp()
        self._datasrc = get_fixture_directory() / "katana"

    def test_katana_pulse(self):
        """
        basic crawler initialization.
        """
        crawler = KatanaCrawler(self._datasrc)
        self.assertIsNotNone(crawler)
        self.assertTrue(self._datasrc.is_dir())

    def test_katana_sites(self):
        """
        site retrieval API functionality.
        """
        crawler = KatanaCrawler(self._datasrc)
        self.run_pragmar_site_tests(crawler, PRAGMAR_SITE_ID)

    def test_katana_search(self):
        """
        boolean search tests
        """
        crawler = KatanaCrawler(self._datasrc)
        self.run_pragmar_search_tests(crawler, PRAGMAR_SITE_ID)

    def test_pragmar_tokenizer(self):
        """
        tokenizer search tests
        """
        crawler = KatanaCrawler(self._datasrc)
        self.run_pragmar_tokenizer_tests(crawler, PRAGMAR_SITE_ID)


    def test_katana_resources(self):
        """
        resource retrieval API functionality with various parameters.
        """
        crawler = KatanaCrawler(self._datasrc)
        self.run_sites_resources_tests(crawler, PRAGMAR_SITE_ID, EXAMPLE_SITE_ID)

    def test_interrobot_images(self):
        """
        Test InterroBot-specific image handling and thumbnails.
        """
        crawler = KatanaCrawler(self._datasrc)
        self.run_pragmar_image_tests(crawler, PRAGMAR_SITE_ID)

    def test_katana_random_sort(self):
        """
        random sort functionality using the '?' sort parameter.
        """
        crawler = KatanaCrawler(self._datasrc)
        self.run_pragmar_sort_tests(crawler, PRAGMAR_SITE_ID)

    def test_katana_content_parsing(self):
        """
        content type detection and parsing for HTTP text files.
        """
        crawler = KatanaCrawler(self._datasrc)
        self.run_pragmar_content_tests(crawler, PRAGMAR_SITE_ID, False)

    def test_report(self):
        """
        Test thumbnail generation functionality (InterroBot-specific).
        """
        crawler = KatanaCrawler(self._datasrc)
        logger.info(self.run_pragmar_report(crawler, PRAGMAR_SITE_ID, "Katana"))
