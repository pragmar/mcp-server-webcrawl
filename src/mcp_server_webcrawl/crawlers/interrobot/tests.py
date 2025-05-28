import asyncio
from logging import Logger
from mcp.types import EmbeddedResource, ImageContent, TextContent
from mcp_server_webcrawl.crawlers.base.tests import BaseCrawlerTests
from mcp_server_webcrawl.crawlers.interrobot.crawler import InterroBotCrawler
from mcp_server_webcrawl.models.resources import RESOURCES_TOOL_NAME
from mcp_server_webcrawl.crawlers import get_fixture_directory
from mcp_server_webcrawl.utils.logger import get_logger

# these IDs belong to a db fixture, static for testing
EXAMPLE_SITE_ID = 1
PRAGMAR_SITE_ID = 2

logger: Logger = get_logger()

class InterroBotTests(BaseCrawlerTests):
    """
    Test suite for the InterroBot crawler implementation.
    Uses all wrapped test methods from BaseCrawlerTests plus InterroBot-specific features.
    """

    def setUp(self):
        """
        Set up the test environment with fixture data.
        """
        super().setUp()
        self.fixture_path = get_fixture_directory() / "interrobot" / "interrobot.v2.db"

    def test_interrobot_pulse(self):
        """
        Test basic crawler initialization.
        """
        crawler = InterroBotCrawler(self.fixture_path)
        self.assertIsNotNone(crawler)

    def test_interrobot_sites(self):
        """
        Test site retrieval API functionality.
        """
        crawler = InterroBotCrawler(self.fixture_path)
        # Note: InterroBot uses site ID 2 for pragmar instead of calculating from string
        self.run_pragmar_site_tests(crawler, PRAGMAR_SITE_ID)

    def test_interrobot_search(self):
        """
        Test boolean search functionality
        """
        crawler = InterroBotCrawler(self.fixture_path)
        self.run_pragmar_search_tests(crawler, PRAGMAR_SITE_ID)

    def test_interrobot_resources(self):
        """
        Test resource retrieval API functionality with various parameters.
        """
        crawler = InterroBotCrawler(self.fixture_path)
        self.run_sites_resources_tests(crawler, PRAGMAR_SITE_ID, EXAMPLE_SITE_ID)

    def test_interrobot_images(self):
        """
        Test InterroBot-specific image handling and thumbnails.
        """
        crawler = InterroBotCrawler(self.fixture_path)
        self.run_pragmar_image_tests(crawler, PRAGMAR_SITE_ID)

    def test_interrobot_random_sort(self):
        """
        Test random sort functionality using the '?' sort parameter.
        """
        crawler = InterroBotCrawler(self.fixture_path)
        self.run_pragmar_sort_tests(crawler, PRAGMAR_SITE_ID)

    def test_interrobot_content_parsing(self):
        """
        Test content type detection and parsing.
        """
        crawler = InterroBotCrawler(self.fixture_path)
        self.run_pragmar_content_tests(crawler, PRAGMAR_SITE_ID, False)

    def test_interrobot_mcp_features(self):
        """
        Test InterroBot-specific MCP tool functionality.
        """
        crawler = InterroBotCrawler(self.fixture_path)
        list_tools_result = asyncio.run(crawler.mcp_list_tools())
        self.assertIsNotNone(list_tools_result)

    def test_thumbnails_sync(self):
        """
        Test thumbnail generation functionality (InterroBot-specific).
        """
        asyncio.run(self.__test_thumbnails())

    async def __test_thumbnails(self):
        """
        Test thumbnails are a special case for InterroBot
        """
        crawler = InterroBotCrawler(self.fixture_path)
        thumbnail_args = {
            "datasrc": crawler.datasrc,
            "sites": [2],
            "extras": ["thumbnails"],
            "query": "type: img AND url: *.png",
            "limit": 4,
        }
        thumbnail_result: list[TextContent | ImageContent | EmbeddedResource] = await crawler.mcp_call_tool(
            RESOURCES_TOOL_NAME, thumbnail_args
        )
        if len(thumbnail_result) > 1:
            self.assertTrue(
                thumbnail_result[1].type == "image",
                "ImageContent should be included in thumbnails response"
            )

    def test_interrobot_advanced_site_features(self):
        """
        Test InterroBot-specific site features like robots field.
        """
        crawler = InterroBotCrawler(self.fixture_path)

        # robots field retrieval
        site_one_field_json = crawler.get_sites_api(ids=[1], fields=["robots"])
        if site_one_field_json.total > 0:
            result_dict = site_one_field_json._results[0].to_dict()
            self.assertIn("robots", result_dict, "robots field should be present in response")

        # multiple custom fields
        site_multiple_fields_json = crawler.get_sites_api(ids=[1], fields=["robots", "created"])
        if site_multiple_fields_json.total > 0:
            result = site_multiple_fields_json._results[0].to_dict()
            self.assertIn("robots", result, "robots field should be present in response")
            self.assertIn("created", result, "created field should be present in response")

    def test_report(self):
        """
        Test thumbnail generation functionality (InterroBot-specific).
        """
        crawler = InterroBotCrawler(self.fixture_path)
        logger.info(self.run_pragmar_report(crawler, PRAGMAR_SITE_ID, "InterroBot"))
