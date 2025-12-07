from mcp_server_webcrawl.crawlers.httrack.crawler import HtTrackCrawler
from mcp_server_webcrawl.crawlers.httrack.adapter import HtTrackManager
from mcp_server_webcrawl.crawlers.base.tests import BaseCrawlerTests
from mcp_server_webcrawl.crawlers import get_fixture_directory
from mcp_server_webcrawl.utils.logger import get_logger

logger = get_logger()

# Calculate using same hash function as adapter
EXAMPLE_SITE_ID = HtTrackManager.string_to_id("example")
PRAGMAR_SITE_ID = HtTrackManager.string_to_id("pragmar")

class HtTrackTests(BaseCrawlerTests):
    """
    Test suite for the HTTrack crawler implementation.
    Uses all wrapped test methods from BaseCrawlerTests plus HTTrack-specific features.
    """

    def setUp(self):
        """
        Set up the test environment with fixture data.
        """
        super().setUp()
        self._datasrc = get_fixture_directory() / "httrack"

    def test_httrack_pulse(self):
        """
        Test basic crawler initialization.
        """
        crawler = HtTrackCrawler(self._datasrc)
        self.assertIsNotNone(crawler)
        self.assertTrue(self._datasrc.is_dir())

    def test_httrack_sites(self):
        """
        Test site retrieval API functionality.
        """
        crawler = HtTrackCrawler(self._datasrc)
        self.run_pragmar_site_tests(crawler, PRAGMAR_SITE_ID)

    def test_httrack_search(self):
        """
        Test boolean search functionality
        """
        crawler = HtTrackCrawler(self._datasrc)
        self.run_pragmar_search_tests(crawler, PRAGMAR_SITE_ID)
        pass

    def test_httrack_resources(self):
        """
        Test resource retrieval API functionality with various arguments.
        """
        crawler = HtTrackCrawler(self._datasrc)
        self.run_sites_resources_tests(crawler, PRAGMAR_SITE_ID, EXAMPLE_SITE_ID)

    def test_httrack_images(self):
        """
        Test HTTrack image handling and thumbnails.
        """
        crawler = HtTrackCrawler(self._datasrc)
        self.run_pragmar_image_tests(crawler, PRAGMAR_SITE_ID)

    def test_httrack_sorts(self):
        """
        Test random sort functionality using the sort argument.
        """
        crawler = HtTrackCrawler(self._datasrc)
        self.run_pragmar_sort_tests(crawler, PRAGMAR_SITE_ID)

    def test_httrack_content_parsing(self):
        """
        Test content type detection and parsing.
        """
        crawler = HtTrackCrawler(self._datasrc)
        self.run_pragmar_content_tests(crawler, PRAGMAR_SITE_ID, False)

    def test_httrack_tokenizer(self):
        """
        Test HTTrack-specific tokenizer functionality for hyphenated terms.
        """
        crawler = HtTrackCrawler(self._datasrc)
        self.run_pragmar_tokenizer_tests(crawler, PRAGMAR_SITE_ID)

    def test_httrack_log_parsing_features(self):
        """
        Test HTTrack-specific features related to hts-log.txt parsing.
        """
        crawler = HtTrackCrawler(self._datasrc)

        # Test that 404 errors from log are properly indexed
        error_resources = crawler.get_resources_api(
            sites=[PRAGMAR_SITE_ID],
            query="status: 404"
        )
        if error_resources.total > 0:
            for resource in error_resources._results:
                self.assertEqual(resource.status, 404, "404 status should be preserved from log parsing")

        # Test that redirects are properly indexed
        redirect_resources = crawler.get_resources_api(
            sites=[PRAGMAR_SITE_ID],
            query="status: 302"
        )
        if redirect_resources.total > 0:
            for resource in redirect_resources._results:
                self.assertEqual(resource.status, 302, "Redirect status should be detected from log")

        # Test successful resources default to 200
        success_resources = crawler.get_resources_api(
            sites=[PRAGMAR_SITE_ID],
            query="status: 200",
            limit=5
        )
        self.assertTrue(success_resources.total > 0, "Should have successful resources with status 200")
        for resource in success_resources._results:
            self.assertEqual(resource.status, 200)

    def test_httrack_url_reconstruction(self):
        """
        Test HTTrack URL reconstruction from project and domain structure.
        """
        crawler = HtTrackCrawler(self._datasrc)

        # Get all resources to test URL patterns
        all_resources = crawler.get_resources_api(
            sites=[PRAGMAR_SITE_ID],
            limit=10
        )
        self.assertTrue(all_resources.total > 0, "Should have resources with reconstructed URLs")

        for resource in all_resources._results:
            # URLs should be properly formatted
            self.assertTrue(resource.url.startswith("https://"),
                          f"URL should start with https://: {resource.url}")

            # URLs should not contain file system artifacts
            self.assertNotIn("\\", resource.url, "URLs should not contain backslashes")
            self.assertNotIn("hts-", resource.url, "URLs should not contain HTTrack artifacts")

    def test_httrack_domain_detection(self):
        """
        Test HTTrack domain directory detection and multi-domain handling.
        """
        crawler = HtTrackCrawler(self._datasrc)
        sites_result = crawler.get_sites_api()
        self.assertTrue(sites_result.total > 0, "Should detect HTTrack project directories as sites")

        specific_site = crawler.get_sites_api(ids=[PRAGMAR_SITE_ID])
        if specific_site.total > 0:
            site_data = specific_site._results[0].to_dict()
            self.assertIn("urls", site_data, "Site should have URLs")
            self.assertTrue(len(site_data["urls"]) > 0, "Site should have at least one valid URL")

    def test_httrack_file_exclusion(self):
        """
        Test that HTTrack-generated files are properly excluded.
        """
        crawler = HtTrackCrawler(self._datasrc)

        # Search for any resources that might be HTTrack artifacts
        all_resources = crawler.get_resources_api(
            sites=[PRAGMAR_SITE_ID],
            query="",
            limit=50
        )

        for resource in all_resources._results:
            # Should not find project-level index.html (HTTrack-generated)
            if resource.url.endswith("/index.html"):
                # This should be domain-level index.html, not project-level
                self.assertNotEqual(resource.url, "https://pragmar/index.html",
                                  "Should not index project-level HTTrack-generated index.html")

            # Should not find hts-log.txt as a resource
            self.assertNotIn("hts-log.txt", resource.url, "Should not index hts-log.txt as resource")
            self.assertNotIn("hts-cache", resource.url, "Should not index hts-cache contents as resources")

    def test_httrack_advanced_features(self):
        """
        Test HTTrack-specific advanced features not covered by base tests.
        """
        crawler = HtTrackCrawler(self._datasrc)

        # Test field retrieval with HTTrack-specific metadata
        field_resources = crawler.get_resources_api(
            sites=[PRAGMAR_SITE_ID],
            query="type: html",
            fields=["content", "headers", "created", "modified"],
            limit=3
        )

        if field_resources.total > 0:
            resource_dict = field_resources._results[0].to_dict()

            # Test timestamps from file system
            self.assertIn("created", resource_dict, "Should have created timestamp from file stat")
            self.assertIn("modified", resource_dict, "Should have modified timestamp from file stat")

            # Test headers generation
            if "headers" in resource_dict and resource_dict["headers"]:
                headers = resource_dict["headers"]
                self.assertIn("Content-Type:", headers, "Should have generated Content-Type header")
                self.assertIn("Content-Length:", headers, "Should have generated Content-Length header")

        # Test that resources have proper size information
        size_resources = crawler.get_resources_api(
            sites=[PRAGMAR_SITE_ID],
            fields=["size"],
            limit=5
        )

        if size_resources.total > 0:
            for resource in size_resources._results:
                resource_dict = resource.to_dict()
                self.assertIn("size", resource_dict, "Resource should have size field")
                self.assertGreaterEqual(resource_dict["size"], 0, "Size should be non-negative")

    def test_report(self):
        """
        Run test report, save to data directory.
        """
        crawler = HtTrackCrawler(self._datasrc)
        logger.info(self.run_pragmar_report(crawler, PRAGMAR_SITE_ID, "HTTrack"))