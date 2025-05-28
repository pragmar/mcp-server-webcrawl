from mcp_server_webcrawl.crawlers.siteone.crawler import SiteOneCrawler
from mcp_server_webcrawl.crawlers.base.tests import BaseCrawlerTests
from mcp_server_webcrawl.crawlers import get_fixture_directory
from mcp_server_webcrawl.crawlers.siteone.adapter import SiteOneManager
from mcp_server_webcrawl.utils.logger import get_logger

logger = get_logger()

# calculate using same hash function as adapter
EXAMPLE_SITE_ID = SiteOneManager.string_to_id("example.com")
PRAGMAR_SITE_ID = SiteOneManager.string_to_id("pragmar.com")

class SiteOneTests(BaseCrawlerTests):
    """
    Test suite for the SiteOne crawler implementation.
    Uses all wrapped test methods from BaseCrawlerTests plus SiteOne-specific features.
    """

    def setUp(self):
        """
        Set up the test environment with fixture data.
        """
        super().setUp()
        self._datasrc = get_fixture_directory() / "siteone"

    def test_siteone_pulse(self):
        """
        Test basic crawler initialization.
        """
        crawler = SiteOneCrawler(self._datasrc)
        self.assertIsNotNone(crawler)
        self.assertTrue(self._datasrc.is_dir())

    def test_siteone_sites(self):
        """
        Test site retrieval API functionality.
        """
        crawler = SiteOneCrawler(self._datasrc)
        self.run_pragmar_site_tests(crawler, PRAGMAR_SITE_ID)

    def test_siteone_search(self):
        """
        Test boolean search functionality
        """
        crawler = SiteOneCrawler(self._datasrc)
        self.run_pragmar_search_tests(crawler, PRAGMAR_SITE_ID)

    def test_siteone_resources(self):
        """
        Test resource retrieval API functionality with various parameters.
        """
        crawler = SiteOneCrawler(self._datasrc)
        self.run_sites_resources_tests(crawler, PRAGMAR_SITE_ID, EXAMPLE_SITE_ID)

    def test_interrobot_images(self):
        """
        Test InterroBot-specific image handling and thumbnails.
        """
        crawler = SiteOneCrawler(self._datasrc)
        self.run_pragmar_image_tests(crawler, PRAGMAR_SITE_ID)

    def test_siteone_random_sort(self):
        """
        Test random sort functionality using the '?' sort parameter.
        """
        crawler = SiteOneCrawler(self._datasrc)
        self.run_pragmar_sort_tests(crawler, PRAGMAR_SITE_ID)

    def test_siteone_content_parsing(self):
        """
        Test content type detection and parsing.
        """
        crawler = SiteOneCrawler(self._datasrc)
        self.run_pragmar_content_tests(crawler, PRAGMAR_SITE_ID, False)

    def test_siteone_advanced_features(self):
        """
        Test SiteOne-specific advanced features not covered by base tests.
        """
        crawler = SiteOneCrawler(self._datasrc)

        # numeric status operators (SiteOne-specific feature)
        status_resources_gt = crawler.get_resources_api(
            sites=[PRAGMAR_SITE_ID],
            query="status: >400",
        )
        self.assertTrue(status_resources_gt.total > 0, "Numeric status operator should return results")
        for resource in status_resources_gt._results:
            self.assertGreater(resource.status, 400)

        # redirect status codes
        status_resources_redirect = crawler.get_resources_api(
            sites=[PRAGMAR_SITE_ID],
            query="status: 301"
        )
        self.assertTrue(status_resources_redirect.total > 0, "301 status filtering should return results")
        for resource in status_resources_redirect._results:
            self.assertEqual(resource.status, 301)

        # 404 with size validation
        status_resources_not_found = crawler.get_resources_api(
            sites=[PRAGMAR_SITE_ID],
            query="status: 404",
            fields=["size"]
        )
        self.assertTrue(status_resources_not_found.total > 0, "404 status filtering should return results")
        for resource in status_resources_not_found._results:
            self.assertEqual(resource.status, 404)

        not_found_result = status_resources_not_found._results[0].to_dict()
        self.assertIn("size", not_found_result)
        self.assertGreater(not_found_result["size"], 0, "404 responses should still have size > 0")

        custom_fields = ["content", "headers", "time"]
        field_resources = crawler.get_resources_api(
            sites=[PRAGMAR_SITE_ID],
            fields=custom_fields
        )
        self.assertTrue(field_resources.total > 0)

        # Test the SiteOne-specific forcefield dict method
        resource_dict = field_resources._results[0].to_forcefield_dict(custom_fields)
        for field in custom_fields:
            self.assertIn(field, resource_dict, f"Field '{field}' should be in forcefield response")

    def test_report(self):
        """
        Test thumbnail generation functionality (InterroBot-specific).
        """
        crawler = SiteOneCrawler(self._datasrc)
        logger.info(self.run_pragmar_report(crawler, PRAGMAR_SITE_ID, "SiteOne"))
