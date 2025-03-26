from mcp_server_webcrawl.crawlers.katana.crawler import KatanaCrawler
from mcp_server_webcrawl.crawlers.katana.adapter import KatanaManager
from mcp_server_webcrawl.models.resources import ResourceResultType
from mcp_server_webcrawl.crawlers.base.tests import BaseCrawlerTests
from mcp_server_webcrawl.crawlers import get_fixture_directory

# calculate ids for test directories using the same hash function as adapter
EXAMPLE_SITE_ID = KatanaManager.string_to_id("example.com")
PRAGMAR_SITE_ID = KatanaManager.string_to_id("pragmar.com")

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
        
        # all sites
        sites_json = crawler.get_sites_api()
        self.assertTrue(sites_json.total >= 2)
        
        # single site
        site_one_json = crawler.get_sites_api(ids=[EXAMPLE_SITE_ID])
        self.assertTrue(site_one_json.total == 1)

        # site with fields
        site_field_json = crawler.get_sites_api(ids=[PRAGMAR_SITE_ID], fields=["created", "modified"])
        site_field_result = site_field_json._results[0].to_dict()
        self.assertTrue("created" in site_field_result)
        self.assertTrue("modified" in site_field_result)

    def test_katana_resources(self):
        """
        resource retrieval API functionality with various parameters.
        """
        crawler = KatanaCrawler(self._datasrc)
        
        # basic resource retrieval
        resources_json = crawler.get_resources_api()
        self.assertTrue(resources_json.total > 0)

        # query parameter for content search
        query_resources = crawler.get_resources_api(
            sites=[PRAGMAR_SITE_ID],
            query="qbit",
            fields=["content", "headers"]
        )
        self.assertTrue(query_resources.total > 0, "Search query should return results")
        
        # verify search term exists in returned resources
        for resource in query_resources._results:
            resource_dict = resource.to_dict()
            found = False
            for field, value in resource_dict.items():
                if isinstance(value, str) and "qbit" in value.lower():
                    found = True
                    break
            self.assertTrue(found, f"Search term not found in any field of resource {resource.id}")

        # resource ID filtering
        if resources_json.total > 0:
            first_resource = resources_json._results[0]
            id_resources = crawler.get_resources_api(
                sites=[first_resource.site],
                ids=[first_resource.id]
            )
            self.assertEqual(id_resources.total, 1)
            self.assertEqual(id_resources._results[0].id, first_resource.id)

        # site filtering
        site_resources = crawler.get_resources_api(sites=[PRAGMAR_SITE_ID])
        self.assertTrue(site_resources.total > 0, "Site filtering should return results")
        for resource in site_resources._results:
            self.assertEqual(resource.site, PRAGMAR_SITE_ID)

        # type filtering for HTML pages
        html_resources = crawler.get_resources_api(
            sites=[PRAGMAR_SITE_ID],
            types=[ResourceResultType.PAGE]
        )
        self.assertTrue(html_resources.total > 0, "HTML filtering should return results")
        for resource in html_resources._results:
            self.assertEqual(resource.type, ResourceResultType.PAGE)

        # type filtering for multiple resource types
        mixed_resources = crawler.get_resources_api(
            sites=[PRAGMAR_SITE_ID],
            types=[ResourceResultType.PAGE, ResourceResultType.SCRIPT]
        )
        if mixed_resources.total > 0:
            types_found = {r.type for r in mixed_resources._results}
            self.assertTrue(
                len(types_found) > 0,
                "Should find at least one of the requested resource types"
            )
            for resource_type in types_found:
                self.assertIn(
                    resource_type,
                    [ResourceResultType.PAGE, ResourceResultType.SCRIPT]
                )

        # custom fields in response
        custom_fields = ["content", "headers", "time"]
        field_resources = crawler.get_resources_api(
            sites=[PRAGMAR_SITE_ID],
            fields=custom_fields
        )
        self.assertTrue(field_resources.total > 0)
        resource_dict = field_resources._results[0].to_dict()
        for field in custom_fields:
            self.assertIn(field, resource_dict, f"Field '{field}' should be in response")

        # URL sorting (ascending)
        asc_resources = crawler.get_resources_api(sites=[PRAGMAR_SITE_ID], sort="+url")
        if asc_resources.total > 1:
            self.assertTrue(asc_resources._results[0].url <= asc_resources._results[1].url)

        # URL sorting (descending)
        desc_resources = crawler.get_resources_api(sites=[PRAGMAR_SITE_ID], sort="-url")
        if desc_resources.total > 1:
            self.assertTrue(desc_resources._results[0].url >= desc_resources._results[1].url)

        # pagination (limit)
        limit_resources = crawler.get_resources_api(sites=[PRAGMAR_SITE_ID], limit=3)
        self.assertTrue(len(limit_resources._results) <= 3)

        # pagination (offset)
        offset_resources = crawler.get_resources_api(sites=[PRAGMAR_SITE_ID], offset=2, limit=2)
        self.assertTrue(len(offset_resources._results) <= 2)
        if resources_json.total > 4:
            self.assertNotEqual(
                resources_json._results[0].id,
                offset_resources._results[0].id,
                "Offset results should differ from first page"
            )

        # status code filtering
        status_resources = crawler.get_resources_api(sites=[PRAGMAR_SITE_ID], statuses=[200])
        self.assertTrue(status_resources.total > 0, "Status filtering should return results")
        for resource in status_resources._results:
            self.assertEqual(resource.status, 200)

        # multiple status codes
        multi_status_resources = crawler.get_resources_api(statuses=[200, 404])
        if multi_status_resources.total > 0:
            found_statuses = {r.status for r in multi_status_resources._results}
            for status in found_statuses:
                self.assertIn(status, [200, 404])

        # combined filtering
        combined_resources = crawler.get_resources_api(
            sites=[PRAGMAR_SITE_ID],
            query="style",
            types=[ResourceResultType.PAGE],
            fields=["content", "headers"],
            sort="+url",
            limit=3
        )
        
        if combined_resources.total > 0:
            for resource in combined_resources._results:
                self.assertEqual(resource.site, PRAGMAR_SITE_ID)
                self.assertEqual(resource.type, ResourceResultType.PAGE)
                resource_dict = resource.to_dict()
                self.assertIn("content", resource_dict)
                self.assertIn("headers", resource_dict)

        # multi-site search
        multisite_resources = crawler.get_resources_api(
            sites=[EXAMPLE_SITE_ID, PRAGMAR_SITE_ID],
            types=[ResourceResultType.PAGE],
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
            EXAMPLE_SITE_ID,
            found_sites,
            "Should have results from example.com"
        )
        self.assertIn(
            PRAGMAR_SITE_ID,
            found_sites,
            "Should have results from pragmar.com"
        )

    def test_katana_random_sort(self):
        """
        random sort functionality using the '?' sort parameter.
        """
        crawler = KatanaCrawler(self._datasrc)
        random1_resources = crawler.get_resources_api(sites=[PRAGMAR_SITE_ID], sort="?", limit=20)
        self.assertTrue(random1_resources.total > 0, "Database should contain resources")
        random1_ids = [r.id for r in random1_resources._results]
        random2_resources = crawler.get_resources_api(sites=[PRAGMAR_SITE_ID], sort="?", limit=20)
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

    def test_katana_content_parsing(self):
        """
        content type detection and parsing for HTTP text files.
        """
        crawler = KatanaCrawler(self._datasrc)
        
        # HTML content detection
        html_resources = crawler.get_resources_api(
            sites=[PRAGMAR_SITE_ID],
            types=[ResourceResultType.PAGE],
            fields=["content", "headers"]
        )
        self.assertTrue(html_resources.total > 0, "Should find HTML resources")
        for resource in html_resources._results:
            resource_dict = resource.to_dict()
            if "content" in resource_dict and resource_dict["content"]:
                self.assertTrue(
                    "<!DOCTYPE html>" in resource_dict["content"] or 
                    "<html" in resource_dict["content"],
                    f"HTML content should contain HTML markups: {resource.url}"
                )
            
            if "headers" in resource_dict and resource_dict["headers"]:
                self.assertTrue(
                    "Content-Type:" in resource_dict["headers"],
                    f"Headers should contain Content-Type: {resource.url}"
                )
        
        # script content detection
        script_resources = crawler.get_resources_api(
            sites=[PRAGMAR_SITE_ID],
            types=[ResourceResultType.SCRIPT],
            fields=["content", "headers"]
        )
        if script_resources.total > 0:
            for resource in script_resources._results:
                self.assertEqual(resource.type, ResourceResultType.SCRIPT)
                
        # css content detection
        css_resources = crawler.get_resources_api(
            sites=[PRAGMAR_SITE_ID],
            types=[ResourceResultType.CSS],
            fields=["content", "headers"]
        )
        if css_resources.total > 0:
            for resource in css_resources._results:
                self.assertEqual(resource.type, ResourceResultType.CSS)