from mcp_server_webcrawl.crawlers.warc.crawler import WarcCrawler
from mcp_server_webcrawl.crawlers.warc.adapter import WarcManager
from mcp_server_webcrawl.models.resources import ResourceResultType
from mcp_server_webcrawl.crawlers.base.tests import BaseCrawlerTests
from mcp_server_webcrawl.crawlers import get_fixture_directory

EXAMPLE_WARC_ID: int = WarcManager.string_to_id("example.com.warc.txt")
PRAGMAR_WARC_ID: int =  WarcManager.string_to_id("pragmar.com.warc.txt") # 50126081961606

class WarcTests(BaseCrawlerTests):
    """
    Test suite for the WARC crawler implementation.
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

    def test_warc_sites(self):
        """
        Test site retrieval API functionality.
        """
        crawler = WarcCrawler(self._datasrc)
        sites_json = crawler.get_sites_api()
        self.assertTrue(sites_json.total >= 2)
        site_one_json = crawler.get_sites_api(ids=[EXAMPLE_WARC_ID])
        self.assertTrue(site_one_json.total == 1)

        pragmar_field_json = crawler.get_sites_api(ids=[PRAGMAR_WARC_ID], fields=["created", "modified"])
        pragmar_field_result = pragmar_field_json._results[0].to_dict()
        self.assertTrue("created" in pragmar_field_result)
        self.assertTrue("modified" in pragmar_field_result)

    def test_warc_resources(self):
        """
        Test resource retrieval API functionality with various parameters.
        """
        crawler = WarcCrawler(self._datasrc)

        # basic resource retrieval with default parameters
        resources_json = crawler.get_resources_api()
        self.assertTrue(resources_json.total > 0)

        # fulltext keyword search
        query_keyword = "privacy"
        keyword_resources = crawler.get_resources_api(
            sites=[PRAGMAR_WARC_ID],
            query=query_keyword,
            fields=["content", "headers"]
        )
        self.assertTrue(keyword_resources.total > 0, "Keyword query should return results")

        # search term exists in returned resources
        for resource in keyword_resources._results:
            resource_dict = resource.to_dict()
            found = False
            for field, value in resource_dict.items():
                if isinstance(value, str) and query_keyword in value.lower():
                    found = True
                    break
            self.assertTrue(found, f"Search term not found in any field of resource {resource.id}")

        # fulltext OR search
        or_resources = crawler.get_resources_api(
            sites=[PRAGMAR_WARC_ID],
            query="qbit OR appstat",
            fields=[]
        )
        self.assertTrue(or_resources.total > 0, "Fulltext OR query should return results")

        # fulltext AND search
        and_resources = crawler.get_resources_api(
            sites=[PRAGMAR_WARC_ID],
            query="monitor AND appstat",
            fields=[]
        )
        self.assertTrue(and_resources.total > 0, "Fulltext AND query should return results")
        self.assertTrue(or_resources.total >= and_resources.total, "Fulltext OR counts should be >= AND counts")

        # retrieving resources by specific ids
        if resources_json.total > 0:
            first_id = resources_json._results[0].id
            id_resources = crawler.get_resources_api(
                sites=[PRAGMAR_WARC_ID],
                query=f"id: {first_id}",
            )
            self.assertEqual(id_resources.total, 1)
            self.assertEqual(id_resources._results[0].id, first_id)

        # site filtering
        site_resources = crawler.get_resources_api(sites=[PRAGMAR_WARC_ID])
        self.assertTrue(site_resources.total > 0, "Site filtering should return results")
        for resource in site_resources._results:
            self.assertEqual(resource.site, PRAGMAR_WARC_ID)

        # type filtering for HTML pages
        html_resources = crawler.get_resources_api(
            sites=[PRAGMAR_WARC_ID],
            query=f"type: {ResourceResultType.PAGE.value}"
        )
        self.assertTrue(html_resources.total > 0, "HTML filtering should return results")
        for resource in html_resources._results:
            self.assertEqual(resource.type, ResourceResultType.PAGE)

        # custom fields in response
        custom_fields = ["content", "headers", "time"]
        field_resources = crawler.get_resources_api(sites=[PRAGMAR_WARC_ID], fields=custom_fields)
        self.assertTrue(field_resources.total > 0)
        resource_dict = field_resources._results[0].to_dict()
        for field in custom_fields:
            self.assertIn(field, resource_dict, f"Field '{field}' should be in response")

        # sorting (ascending and descending)
        asc_resources = crawler.get_resources_api(sites=[PRAGMAR_WARC_ID], sort="+url")
        if asc_resources.total > 1:
            self.assertTrue(asc_resources._results[0].url <= asc_resources._results[1].url)

        desc_resources = crawler.get_resources_api(sites=[PRAGMAR_WARC_ID], sort="-url")
        if desc_resources.total > 1:
            self.assertTrue(desc_resources._results[0].url >= desc_resources._results[1].url)

        limit_resources = crawler.get_resources_api(sites=[PRAGMAR_WARC_ID], limit=3)
        self.assertTrue(len(limit_resources._results) <= 3)

        offset_resources = crawler.get_resources_api(sites=[PRAGMAR_WARC_ID], offset=2, limit=2)
        self.assertTrue(len(offset_resources._results) <= 2)
        if resources_json.total > 4:
            self.assertNotEqual(
                resources_json._results[0].id,
                offset_resources._results[0].id,
                "Offset results should differ from first page"
            )

        # single field filtering
        status_resources = crawler.get_resources_api(
            sites=[PRAGMAR_WARC_ID],
            query="status: 200"
        )
        self.assertTrue(status_resources.total > 0, "Status filtering should return results")
        for resource in status_resources._results:
            self.assertEqual(resource.status, 200)

        # combined filtering
        combined_resources = crawler.get_resources_api(
            sites=[PRAGMAR_WARC_ID],
            query=f"privacy AND type: {ResourceResultType.PAGE.value}",
            fields=["content", "headers"],
            sort="+url",
            limit=3
        )

        if combined_resources.total > 0:
            for resource in combined_resources._results:
                self.assertEqual(resource.site, PRAGMAR_WARC_ID)
                self.assertEqual(resource.type, ResourceResultType.PAGE)
                resource_dict = resource.to_dict()
                self.assertIn("content", resource_dict)
                self.assertIn("headers", resource_dict)

        # multisite
        multisite_resources = crawler.get_resources_api(
            sites=[EXAMPLE_WARC_ID, PRAGMAR_WARC_ID],
            query=f"type: {ResourceResultType.PAGE.value}",
            sort="+url",
            limit=100
        )

        self.assertTrue(multisite_resources.total > 0, "Multi-site search should return results")

        # track which sites we find results from
        found_sites = set()
        for resource in multisite_resources._results:
            found_sites.add(resource.site)

        # verify we got results from both sites
        self.assertEqual(
            len(found_sites),
            2,
            "Should have results from both sites"
        )
        self.assertIn(
            EXAMPLE_WARC_ID,
            found_sites,
            "Should have results from example.com"
        )
        self.assertIn(
            PRAGMAR_WARC_ID,
            found_sites,
            "Should have results from pragmar.com"
        )