import asyncio

from mcp_server_webcrawl.crawlers.base.tests import BaseCrawlerTests
from mcp_server_webcrawl.crawlers.interrobot.crawler import InterroBotCrawler
from mcp_server_webcrawl.models.resources import ResourceResultType
from mcp_server_webcrawl.crawlers import get_fixture_directory

class InterroBotTests(BaseCrawlerTests):
    """
    Test suite for the InterroBot crawler implementation.
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

    def test_interrobot_mcp(self):
        """
        Test MCP tool functionality.
        """
        crawler = InterroBotCrawler(self.fixture_path)
        list_tools_result = asyncio.run(crawler.mcp_list_tools())
        self.assertIsNotNone(list_tools_result)
        # print(list_tools_result)

    def test_interrobot_thumbnail(self):
        """
        Test thumbnail generation for image resources.
        """
        crawler = InterroBotCrawler(self.fixture_path)
        image_id = 3  # https://www.dolekemp96.org/left.gif
        thumbnail_resources = crawler.get_resources_api(
            ids=[image_id],
        )
        self.assertEqual(thumbnail_resources.total, 1, "Should find exactly one resource")
        # TODO needs rewrite
        # print(asyncio.run(crawler.mcp_call_tool(
        #     name="webcrawl_search",
        #     arguments={"fields": ["created", "modified"], "types": ["img"], "thumbnails": True, "limit": 2}
        # )))
    
    def test_interrobot_sites(self):
        """
        Test site retrieval API functionality.
        """
        crawler = InterroBotCrawler(self.fixture_path)

        sites_json = crawler.get_sites_api()
        self.assertTrue(sites_json.total == 2)

        # example.com
        site_one_json = crawler.get_sites_api(ids=[1])
        self.assertTrue(site_one_json.total == 1)

        # example.com + fields
        site_one_field_json = crawler.get_sites_api(ids=[1], fields=["robots"])
        self.assertTrue("robots" in site_one_field_json._results[0].to_dict())

        site_multiple_fields_json = crawler.get_sites_api(ids=[1], fields=["robots", "created"])
        result = site_multiple_fields_json._results[0].to_dict()
        self.assertTrue("robots" in result, "robots field should be present in response")
        self.assertTrue("created" in result, "created field should be present in response")

    def test_interrobot_resources(self):
        """
        Test resource retrieval API functionality with various parameters.
        """
        crawler = InterroBotCrawler(self.fixture_path)

        # basic resource retrieval with default parameters
        resources_json = crawler.get_resources_api()
        self.assertTrue(resources_json.total > 0)
        # pprint(resources_json.to_dict())

        # query parameter
        query_resources = crawler.get_resources_api(query="example")
        self.assertTrue(query_resources.total > 0, "Search query should return results")
        # pprint(query_resources.to_dict())

        # retrieving resources by specific IDs
        if resources_json.total > 0:
            first_id = resources_json._results[0].id
            id_resources = crawler.get_resources_api(ids=[first_id])
            self.assertEqual(id_resources.total, 1)
            self.assertEqual(id_resources._results[0].id, first_id)

        # site filtering
        site_resources = crawler.get_resources_api(sites=[1])  # Filter to site with ID 1
        # pprint(site_resources.to_dict())
        self.assertTrue(site_resources.total > 0, "Site filtering should return results")
        for resource in site_resources._results:
            self.assertEqual(resource.site, 1)

        # type filtering
        type_resources = crawler.get_resources_api(types=[ResourceResultType.PAGE])
        if type_resources.total > 0:
            for resource in type_resources._results:
                self.assertEqual(resource.type, ResourceResultType.PAGE)

        # custom fields in response
        custom_fields = ["content", "headers", "time"]
        field_resources = crawler.get_resources_api(fields=custom_fields)
        if field_resources.total > 0:
            resource_dict = field_resources._results[0].to_dict()
            for field in custom_fields:
                self.assertIn(field, resource_dict, f"Field '{field}' should be in response")

        # sorting (ascending and descending)
        asc_resources = crawler.get_resources_api(sort="+url")
        if asc_resources.total > 1:
            self.assertTrue(asc_resources._results[0].url <= asc_resources._results[1].url)

        desc_resources = crawler.get_resources_api(sort="-url")
        if desc_resources.total > 1:
            self.assertTrue(desc_resources._results[0].url >= desc_resources._results[1].url)

        # pagination (limit and offset)
        limit_resources = crawler.get_resources_api(limit=5)
        self.assertTrue(len(limit_resources._results) <= 5)

        offset_resources = crawler.get_resources_api(offset=5, limit=5)
        # offset results are different from first page
        if resources_json.total > 10:
            self.assertNotEqual(
                resources_json._results[0].id,
                offset_resources._results[0].id,
                "Offset results should differ from first page"
            )

        # combining multiple parameters
        combined_resources = crawler.get_resources_api(
            sites=[1],
            query="example",
            types=[ResourceResultType.PAGE],
            fields=["content", "headers"],
            sort="+url",
            limit=3
        )

        # results exist, verify they meet all criteria
        if combined_resources.total > 0:
            for resource in combined_resources._results:
                self.assertEqual(resource.site, 1)
                self.assertEqual(resource.type, ResourceResultType.PAGE)
                resource_dict = resource.to_dict()
                self.assertIn("content", resource_dict)
                self.assertIn("headers", resource_dict)

        html_resources = crawler.get_resources_api(types=[ResourceResultType.PAGE, ResourceResultType.PDF])
        self.assertTrue(html_resources.total > 0, "No HTML resources found when filtering for 'html' type")
        self.assertTrue(all(r.type.value in ("html", "pdf") for r in html_resources._results),
                "Not all resources have type 'html' or 'pdf' when filtering for those types")
        # print(html_resources.to_json())

        # status filtering
        status_resources = crawler.get_resources_api(statuses=[200])
        self.assertTrue(status_resources.total > 0, "Status filtering should return results")
        for resource in status_resources._results:
            self.assertEqual(resource.status, 200, "All resources should have status 200")
        
        # multiple statuses
        multi_status_resources = crawler.get_resources_api(statuses=[200, 404, 500])
        self.assertTrue(multi_status_resources.total > 0, "Multiple status filtering should return results")
        for resource in multi_status_resources._results:
            self.assertIn(resource.status, [200, 404, 500], "Resources should have one of the filtered statuses")

    def test_interrobot_random_sort(self):
        """
        Test the random sort functionality using the '?' sort parameter.
        """
        crawler = InterroBotCrawler(self.fixture_path)

        random1_resources = crawler.get_resources_api(sort="?", limit=20)
        self.assertTrue(random1_resources.total > 0, "Database should contain resources")
        random1_ids = [r.id for r in random1_resources._results]
        
        random2_resources = crawler.get_resources_api(sort="?", limit=20)
        self.assertTrue(random2_resources.total > 0, "Random sort should return results")
        random2_ids = [r.id for r in random2_resources._results]
        
        if random2_resources.total >= 10:
            self.assertNotEqual(
                random1_ids, 
                random2_ids,
                f"Random sort should produce different order than standard sort.\nStandard: {random1_ids}\nRandom: {random2_ids}"
            )
        else:
            print(f"Skip randomness verification: Not enough resources ({random2_resources.total})")


