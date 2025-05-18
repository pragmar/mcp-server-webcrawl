from mcp_server_webcrawl.crawlers.siteone.crawler import SiteOneCrawler
from mcp_server_webcrawl.models.resources import ResourceResultType
from mcp_server_webcrawl.crawlers.base.tests import BaseCrawlerTests
from mcp_server_webcrawl.crawlers import get_fixture_directory
from mcp_server_webcrawl.crawlers.siteone.adapter import SiteOneManager

# calculate using same hash function as adapter
EXAMPLE_SITE_ID = SiteOneManager.string_to_id("example.com")
PRAGMAR_SITE_ID = SiteOneManager.string_to_id("pragmar.com")

class SiteOneTests(BaseCrawlerTests):
    """
    Test suite for the SiteOne crawler implementation.
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

    def test_siteone_resources(self):
        """
        Test resource retrieval API functionality with various parameters.
        """
        crawler = SiteOneCrawler(self._datasrc)

        resources_json = crawler.get_resources_api()
        self.assertTrue(resources_json.total > 0)

        # query
        query_resources = crawler.get_resources_api(
            sites=[PRAGMAR_SITE_ID],
            query="privacy",
            fields=["content", "headers"]
        )
        self.assertTrue(query_resources.total > 0, "Search query should return results")

        # search term exists in returned resources
        for resource in query_resources._results:
            resource_dict = resource.to_dict()
            found = False
            for field, value in resource_dict.items():
                if isinstance(value, str) and "privacy" in value.lower():
                    found = True
                    break
            self.assertTrue(found, f"Search term not found in any field of resource {resource.id}")

        # resource id filtering
        if resources_json.total > 0:
            first_resource = resources_json._results[0]
            id_resources = crawler.get_resources_api(
                sites=[first_resource.site],
                query=f"id: {first_resource.id}",
            )
            self.assertEqual(id_resources.total, 1)
            self.assertEqual(id_resources._results[0].id, first_resource.id)

        # site filtering
        site_resources = crawler.get_resources_api(sites=[PRAGMAR_SITE_ID])
        self.assertTrue(site_resources.total > 0, "Site filtering should return results")
        for resource in site_resources._results:
            self.assertEqual(resource.site, PRAGMAR_SITE_ID)

        # type filtering
        html_resources = crawler.get_resources_api(
            sites=[PRAGMAR_SITE_ID],
            query=f"html AND type: {ResourceResultType.PAGE.value}",
            fields=["content", "headers"]
        )
        self.assertTrue(html_resources.total > 0, "HTML filtering should return results")
        for resource in html_resources._results:
            self.assertTrue(
                resource.type == ResourceResultType.PAGE,
                f"Resource {resource.url} should be an HTML page"
            )

        # multiple resource types
        mixed_resources = crawler.get_resources_api(
            sites=[PRAGMAR_SITE_ID],
            query=f"type: {ResourceResultType.PAGE.value} OR type: {ResourceResultType.CSS.value}"
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
                    [ResourceResultType.PAGE, ResourceResultType.CSS]
                )

        # custom fields
        custom_fields = ["content", "headers", "time"]
        field_resources = crawler.get_resources_api(
            sites=[PRAGMAR_SITE_ID],
            fields=custom_fields
        )
        self.assertTrue(field_resources.total > 0)
        resource_dict = field_resources._results[0].to_forcefield_dict(custom_fields)

        for field in custom_fields:
            self.assertIn(field, resource_dict, f"Field '{field}' should be in response")

        # sorting (ascending)
        asc_resources = crawler.get_resources_api(sites=[PRAGMAR_SITE_ID], sort="+url")
        if asc_resources.total > 1:
            self.assertTrue(asc_resources._results[0].url <= asc_resources._results[1].url)

        # sorting (descending)
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
        status_resources_ok = crawler.get_resources_api(
            sites=[PRAGMAR_SITE_ID],
            query="status: 200"
        )
        self.assertTrue(status_resources_ok.total > 0, "Status filtering should return results")
        for resource in status_resources_ok._results:
            self.assertEqual(resource.status, 200)

        # status code numeric operator
        # note S1 finds this, but other crawlers don't always
        status_resources2 = crawler.get_resources_api(
            sites=[PRAGMAR_SITE_ID],
            query=f"status: >400",
        )
        self.assertTrue(status_resources2.total > 0, "Status filtering should return results")
        for resource in status_resources2._results:
            self.assertGreater(resource.status, 200)

        # redirects
        status_resources_redirect = crawler.get_resources_api(
            sites=[PRAGMAR_SITE_ID],
            query="status: 302"
        )
        self.assertTrue(status_resources_redirect.total > 0, "Status filtering should return results")
        for resource in status_resources_redirect._results:
            self.assertEqual(resource.status, 302)

        # 404 will not have all metadata, content likely missing, but should capture filesize
        # pragmar.com has an intentional 404, should be in the fixture
        # http://pragmar.com/internal/this/page/does/not/exist/
        status_resources_not_found = crawler.get_resources_api(
            sites=[PRAGMAR_SITE_ID],
            query="status: 404",
            fields=["size"]
        )
        self.assertTrue(status_resources_not_found.total > 0, "Status filtering should return results")
        for resource in status_resources_not_found._results:
            self.assertEqual(resource.status, 404)
        status_resources_not_found_result = status_resources_not_found._results[0].to_dict()
        self.assertTrue("size" in status_resources_not_found_result)
        self.assertGreater(status_resources_not_found_result["size"], 0, "Size should be greater than 0")

        # combined filtering
        combined_resources = crawler.get_resources_api(
            sites=[PRAGMAR_SITE_ID],
            query=f"index AND type: {ResourceResultType.PAGE.value}",
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
            query=f"type: {ResourceResultType.PAGE.value}",
            sort="+url",
            limit=100
        )

        self.assertTrue(multisite_resources.total > 0, "Multi-site search should return results")

        # which sites we find results from
        found_sites = set()
        for resource in multisite_resources._results:
            found_sites.add(resource.site)

        # we got results from both sites
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

    def test_siteone_random_sort(self):
        """
        Test the random sort functionality using the '?' sort parameter.
        """
        crawler = SiteOneCrawler(self._datasrc)

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