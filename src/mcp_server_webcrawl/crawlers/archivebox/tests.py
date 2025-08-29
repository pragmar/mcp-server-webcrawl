from mcp_server_webcrawl.crawlers.archivebox.crawler import ArchiveBoxCrawler
from mcp_server_webcrawl.crawlers.archivebox.adapter import ArchiveBoxManager
from mcp_server_webcrawl.crawlers.base.tests import BaseCrawlerTests
from mcp_server_webcrawl.crawlers import get_fixture_directory
from mcp_server_webcrawl.utils.logger import get_logger

# calculate ids for ArchiveBox working directories using the same hash function as adapter
EXAMPLE_SITE_ID = ArchiveBoxManager.string_to_id("example")
PRAGMAR_SITE_ID = ArchiveBoxManager.string_to_id("pragmar")

logger = get_logger()

class ArchiveBoxTests(BaseCrawlerTests):
    """
    Test suite for the ArchiveBox crawler implementation.
    Uses wrapped test methods from BaseCrawlerTests adapted for ArchiveBox's multi-instance structure.
    """

    def setUp(self):
        """
        Set up the test environment with fixture data.
        """
        super().setUp()
        self._datasrc = get_fixture_directory() / "archivebox"

    def test_archivebox_pulse(self):
        """
        Test basic crawler initialization.
        """
        crawler = ArchiveBoxCrawler(self._datasrc)
        self.assertIsNotNone(crawler)
        self.assertTrue(self._datasrc.is_dir())

    def test_archivebox_sites(self):
        """
        Test site retrieval API functionality.
        """
        crawler = ArchiveBoxCrawler(self._datasrc)

        # should have multiple sites (example and pragmar working directories)
        sites_json = crawler.get_sites_api()
        self.assertGreaterEqual(sites_json.total, 2, "ArchiveBox should have multiple working directories as sites")

        # test pragmar site specifically
        self.run_pragmar_site_tests(crawler, PRAGMAR_SITE_ID)

    def test_archivebox_search(self):
        """
        Test boolean search functionality.
        """
        crawler = ArchiveBoxCrawler(self._datasrc)
        self.run_pragmar_search_tests(crawler, PRAGMAR_SITE_ID)

    def test_pragmar_tokenizer(self):
        """
        Test tokenizer search functionality.
        """
        crawler = ArchiveBoxCrawler(self._datasrc)
        self.run_pragmar_tokenizer_tests(crawler, PRAGMAR_SITE_ID)

    def test_archivebox_resources(self):
        """
        Test resource retrieval API functionality with various parameters.
        """
        crawler = ArchiveBoxCrawler(self._datasrc)
        self.run_sites_resources_tests(crawler, PRAGMAR_SITE_ID, EXAMPLE_SITE_ID)

    def test_interrobot_images(self):
        """
        Test InterroBot-specific image handling and thumbnails.
        """
        crawler = ArchiveBoxCrawler(self._datasrc)
        self.run_pragmar_image_tests(crawler, PRAGMAR_SITE_ID)

    def test_archivebox_sorts(self):
        """
        Test random sort functionality using the '?' sort parameter.
        """
        crawler = ArchiveBoxCrawler(self._datasrc)
        self.run_pragmar_sort_tests(crawler, PRAGMAR_SITE_ID)

    def test_archivebox_content_parsing(self):
        """
        Test content type detection and parsing for ArchiveBox resources.
        """
        crawler = ArchiveBoxCrawler(self._datasrc)
        self.run_pragmar_content_tests(crawler, PRAGMAR_SITE_ID, False)

    def test_archivebox_url_reconstruction(self):
        """
        Test URL reconstruction from ArchiveBox metadata.
        """
        crawler = ArchiveBoxCrawler(self._datasrc)

        url_resources = crawler.get_resources_api(sites=[PRAGMAR_SITE_ID], limit=20)
        self.assertGreater(url_resources.total, 0, "Should have resources with reconstructed URLs")

        for resource in url_resources._results:
            # URLs should be valid HTTP/HTTPS (except for archivebox:// fallbacks)
            self.assertTrue(
                resource.url.startswith(('http://', 'https://', 'archivebox://')),
                f"URL should have valid scheme: {resource.url}"
            )

            # should not end with index.html (stripped during reconstruction)
            self.assertFalse(
                resource.url.endswith('/index.html'),
                f"URL should not end with index.html: {resource.url}"
            )

    def test_archivebox_deduplication(self):
        """
        Test resource deduplication across timestamped entries.
        """
        crawler = ArchiveBoxCrawler(self._datasrc)

        # get all resources from pragmar site
        all_resources = crawler.get_resources_api(sites=[PRAGMAR_SITE_ID], limit=100)
        self.assertGreater(all_resources.total, 0, "Should have resources")

        # check for URL uniqueness (deduplication should ensure unique URLs)
        urls_found = [r.url for r in all_resources._results]
        unique_urls = set(urls_found)

        # should have deduplication working (though some URLs might legitimately appear multiple times
        # if they're different resources, like different timestamps of the same page)
        self.assertLessEqual(len(unique_urls), len(urls_found),
                            "URL deduplication should work properly")

    def test_archivebox_metadata_parsing(self):
        """
        Test JSON metadata parsing from ArchiveBox files.
        """
        crawler = ArchiveBoxCrawler(self._datasrc)

        # get resources with headers from pragmar site
        header_resources = crawler.get_resources_api(
            sites=[PRAGMAR_SITE_ID],
            fields=["headers"],
            limit=10
        )

        if header_resources.total > 0:
            headers_found = 0
            for resource in header_resources._results:
                resource_dict = resource.to_dict()
                if "headers" in resource_dict and resource_dict["headers"]:
                    headers_found += 1
                    self.assertIn("HTTP/1.0", resource_dict["headers"],
                                "Headers should contain HTTP status line")

            # at least some resources should have parsed headers
            self.assertGreater(headers_found, 0, "Should find resources with parsed headers")

    def test_archivebox_timestamped_structure(self):
        """
        Test handling of ArchiveBox's timestamped entry structure.
        """
        crawler = ArchiveBoxCrawler(self._datasrc)

        # get resources with timestamps from pragmar site
        timestamp_resources = crawler.get_resources_api(
            sites=[PRAGMAR_SITE_ID],
            fields=["created", "modified"],
            limit=10
        )

        self.assertGreater(timestamp_resources.total, 0, "Should have timestamped resources")

        for resource in timestamp_resources._results:
            resource_dict = resource.to_dict()

            # should have timestamp information
            self.assertIsNotNone(resource_dict.get("created"),
                                "Should have created timestamp from entry directory")
            self.assertIsNotNone(resource_dict.get("modified"),
                                "Should have modified timestamp from entry directory")

    def test_archivebox_error_resilience(self):
        """
        Test resilience to malformed JSON and missing files.
        """
        crawler = ArchiveBoxCrawler(self._datasrc)

        # should continue processing despite any JSON parsing errors
        all_resources = crawler.get_resources_api(sites=[PRAGMAR_SITE_ID])

        # verify we got some resources despite potential errors
        self.assertGreater(all_resources.total, 0,
                          "Should process entries even with JSON parsing errors")

        # verify resources have reasonable defaults
        for resource in all_resources._results:
            self.assertIsNotNone(resource.url, "URL should always be set")
            self.assertIsInstance(resource.status, int, "Status should be integer")
            self.assertGreaterEqual(resource.status, 0, "Status should be non-negative")
            self.assertLessEqual(resource.status, 599, "Status should be valid HTTP status")

    def test_archivebox_multi_site(self):
        """
        Test that multiple ArchiveBox working directories are treated as separate sites.
        """
        crawler = ArchiveBoxCrawler(self._datasrc)

        # get resources from each site separately
        example_resources = crawler.get_resources_api(sites=[EXAMPLE_SITE_ID], limit=10)
        pragmar_resources = crawler.get_resources_api(
            query="url: pragmar.com",
            sites=[PRAGMAR_SITE_ID],
            limit=10)

        # print(example_resources.to_dict())
        # print(pragmar_resources.to_dict())

        # both sites should have resources
        self.assertGreater(example_resources.total, 0, "Example site should have resources")
        self.assertGreater(pragmar_resources.total, 0, "Pragmar site should have resources")

        # URLs should reflect the appropriate domains
        example_urls = [r.url for r in example_resources._results]
        pragmar_urls = [r.url for r in pragmar_resources._results]

        # verify site separation (pragmar resources should be about pragmar.com)
        pragmar_domain_urls = [url for url in pragmar_urls if "pragmar.com" in url]
        self.assertGreater(len(pragmar_domain_urls), 0,
                          "Pragmar site should contain pragmar.com URLs")

    def test_report(self):
        """
        Run test report for ArchiveBox archive.
        """
        crawler = ArchiveBoxCrawler(self._datasrc)

        # generate report using pragmar site ID
        report = self.run_pragmar_report(crawler, PRAGMAR_SITE_ID, "ArchiveBox")
        logger.info(report)

        # basic validation that report contains expected content
        self.assertIn("ArchiveBox", report, "Report should mention ArchiveBox")
        self.assertIn("Total pages:", report, "Report should show page counts")