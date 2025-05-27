import unittest
import asyncio
import sys

from logging import Logger

from mcp_server_webcrawl.crawlers.base.crawler import BaseCrawler
from mcp_server_webcrawl.models.resources import ResourceResultType
from mcp_server_webcrawl.utils.logger import get_logger

logger: Logger = get_logger()

class BaseCrawlerTests(unittest.TestCase):

    def setUp(self):
        # quiet asyncio error on tests, occurring after sucessful completion
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    def run_pragmar_search_tests(self, crawler: BaseCrawler, site_id: int):
        """
        Run a battery of database checks on the crawler and Boolean validation
        """
        resources_json = crawler.get_resources_api()
        self.assertTrue(resources_json.total > 0, "Should have some resources in database")

        site_resources = crawler.get_resources_api(sites=[site_id])
        self.assertTrue(site_resources.total > 0, "Pragmar site should have resources")

        primary_keyword = "crawler"
        secondary_keyword = "privacy"

        primary_resources = crawler.get_resources_api(
            sites=[site_id],
            query=primary_keyword,
            fields=["content", "headers"]
        )
        self.assertTrue(primary_resources.total > 0, f"Keyword '{primary_keyword}' should return results")

        for resource in primary_resources._results:
            resource_dict = resource.to_dict()
            found = False
            for field, value in resource_dict.items():
                if isinstance(value, str) and primary_keyword.rstrip("*") in value.lower():
                    found = True
                    break
            self.assertTrue(found, f"Primary keyword not found in any field of resource {resource.id}")

        secondary_resources = crawler.get_resources_api(
            sites=[site_id],
            query=secondary_keyword
        )
        self.assertTrue(secondary_resources.total > 0, f"Keyword '{secondary_keyword}' should return results")

        primary_not_secondary = crawler.get_resources_api(
            sites=[site_id],
            query=f"{primary_keyword} NOT {secondary_keyword}"
        )

        secondary_not_primary = crawler.get_resources_api(
            sites=[site_id],
            query=f"{secondary_keyword} NOT {primary_keyword}"
        )

        primary_or_secondary = crawler.get_resources_api(
            sites=[site_id],
            query=f"{primary_keyword} OR {secondary_keyword}"
        )

        self.assertTrue(primary_not_secondary.total <= primary_resources.total,
                "'crawler NOT privacy' should be subset of 'crawler'")
        self.assertTrue(secondary_not_primary.total <= secondary_resources.total,
                "'privacy NOT crawler' should be subset of 'privacy'")
        self.assertTrue(primary_or_secondary.total >= primary_resources.total,
                "OR should include all primary term results")
        self.assertTrue(primary_or_secondary.total >= secondary_resources.total,
                "OR should include all secondary term results")

        calculated_overlap = primary_resources.total + secondary_resources.total - primary_or_secondary.total
        self.assertTrue(calculated_overlap >= 0, "Overlap cannot be negative")

        reconstructed_total = primary_not_secondary.total + secondary_not_primary.total + calculated_overlap
        self.assertEqual(reconstructed_total, primary_or_secondary.total,
                "Sum of exclusive sets plus overlap should equal OR total")

        complex_and = crawler.get_resources_api(
            sites=[site_id],
            query=f"{primary_keyword} AND type:html AND status:200"
        )
        self.assertTrue(complex_and.total <= primary_resources.total,
                "Adding AND conditions should not increase results")

        grouped_or = crawler.get_resources_api(
            sites=[site_id],
            query=f"({primary_keyword} OR {secondary_keyword}) AND type:html AND status:200"
        )

        self.assertTrue(grouped_or.total <= primary_or_secondary.total,
                "Adding AND conditions to OR should not increase results")

        snippet_resources = crawler.get_resources_api(
            sites=[site_id],
            query=f"{primary_keyword} AND type: html",
            extras=["snippets"],
        )
        self.assertIn("snippets", snippet_resources._results[0].to_dict()["extras"],
                "First result should have snippets in extras")

        markdown_resources = crawler.get_resources_api(
            sites=[site_id],
            query=primary_keyword,
            extras=["markdown"],
        )
        self.assertIn("markdown", markdown_resources._results[0].to_dict()["extras"],
                "First result should have markdown in extras")

        combined_resources = crawler.get_resources_api(
            sites=[site_id],
            query=primary_keyword,
            extras=["snippets", "markdown"],
        )
        first_result = combined_resources._results[0].to_dict()
        self.assertIn("extras", first_result, "First result should have extras field")
        self.assertIn("snippets", first_result["extras"], "First result should have snippets in extras")
        self.assertIn("markdown", first_result["extras"], "First result should have markdown in extras")
        self.assertTrue(primary_resources.total <= site_resources.total,
                "Search should return less than or equivalent results to site total")
        self.assertTrue(secondary_resources.total <= site_resources.total,
                "Search should return less than or equivalent results to site total")

    def run_pragmar_image_tests(self, crawler: BaseCrawler, pragmar_site_id: int):
        """
        Test InterroBot-specific image handling and thumbnails.
        """
        img_results = crawler.get_resources_api(sites=[pragmar_site_id], query="type: img", limit=5)
        self.assertTrue(img_results.total > 0, "Image type filter should return results")
        self.assertTrue(
            all(r.type.value == "img" for r in img_results._results),
            "All filtered resources should have type 'img'"
        )

    def run_sites_resources_tests(self, crawler: BaseCrawler, pragmar_site_id: int, example_site_id: int):

        resources_json = crawler.get_resources_api()
        self.assertTrue(resources_json.total > 0, "Should have some resources in database")

        site_resources = crawler.get_resources_api(sites=[pragmar_site_id])
        self.assertTrue(site_resources.total > 0, "Pragmar site should have resources")

        # basic resource retrieval
        resources_json = crawler.get_resources_api()
        self.assertTrue(resources_json.total > 0)

        # fulltext keyword search
        query_keyword1 = "privacy"

        timestamp_resources = crawler.get_resources_api(
            sites=[pragmar_site_id],
            query=query_keyword1,
            fields=["created", "modified", "time"]
        )
        self.assertTrue(timestamp_resources.total > 0, "Search query should return results")
        for resource in timestamp_resources._results:
            resource_dict = resource.to_dict()
            self.assertIsNotNone(resource_dict["created"], "Created timestamp should not be None")
            self.assertIsNotNone(resource_dict["modified"], "Modified timestamp should not be None")
            self.assertIsNotNone(resource_dict["time"], "Modified timestamp should not be None")

        # resource ID filtering
        if resources_json.total > 0:
            first_resource = resources_json._results[0]
            id_resources = crawler.get_resources_api(
                sites=[first_resource.site],
                query=f"id: {first_resource.id}",
            )
            self.assertEqual(id_resources.total, 1)
            self.assertEqual(id_resources._results[0].id, first_resource.id)

        # site filtering
        site_resources = crawler.get_resources_api(sites=[pragmar_site_id])
        self.assertTrue(site_resources.total > 0, "Site filtering should return results")
        for resource in site_resources._results:
            self.assertEqual(resource.site, pragmar_site_id)

        # type filtering for HTML pages
        html_resources = crawler.get_resources_api(
            sites=[pragmar_site_id],
            query= f"type: {ResourceResultType.PAGE.value}",
        )
        self.assertTrue(html_resources.total > 0, "HTML filtering should return results")
        for resource in html_resources._results:
            self.assertEqual(resource.type, ResourceResultType.PAGE)

        # type filtering for multiple resource types
        mixed_resources = crawler.get_resources_api(
            sites=[pragmar_site_id],
            query= f"type: {ResourceResultType.PAGE.value} OR type: {ResourceResultType.SCRIPT.value}",
            # types=[ResourceResultType.PAGE.value, ResourceResultType.SCRIPT.value]
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
            query="type: html",
            sites=[pragmar_site_id],
            fields=custom_fields,
        )
        self.assertTrue(field_resources.total > 0)
        resource_dict = field_resources._results[0].to_dict()
        for field in custom_fields:
            self.assertIn(field, resource_dict, f"Field '{field}' should be in response")

        asc_resources = crawler.get_resources_api(sites=[pragmar_site_id], sort="+url")
        if asc_resources.total > 1:
            self.assertTrue(asc_resources._results[0].url <= asc_resources._results[1].url)

        desc_resources = crawler.get_resources_api(sites=[pragmar_site_id], sort="-url")
        if desc_resources.total > 1:
            self.assertTrue(desc_resources._results[0].url >= desc_resources._results[1].url)

        limit_resources = crawler.get_resources_api(sites=[pragmar_site_id], limit=3)
        self.assertTrue(len(limit_resources._results) <= 3)

        offset_resources = crawler.get_resources_api(sites=[pragmar_site_id], offset=2, limit=2)
        self.assertTrue(len(offset_resources._results) <= 2)
        if resources_json.total > 4:
            self.assertNotEqual(
                resources_json._results[0].id,
                offset_resources._results[0].id,
                "Offset results should differ from first page"
            )

        # status code filtering
        status_resources = crawler.get_resources_api(
            sites=[pragmar_site_id],
            query=f"status: 200",
        )
        self.assertTrue(status_resources.total > 0, "Status filtering should return results")
        for resource in status_resources._results:
            self.assertEqual(resource.status, 200)


        # status code filtering
        appstat_resources = crawler.get_resources_api(
            sites=[pragmar_site_id],
            query=f"status: 200 AND url: https://pragmar.com/appstat*",
        )
        self.assertTrue(appstat_resources.total > 0, "Status filtering should return results")
        self.assertGreaterEqual(len(appstat_resources._results), 3, f"Unexpected page count\n{len(appstat_resources._results)}")


        # multiple status codes
        multi_status_resources = crawler.get_resources_api(
            query=f"status: 200 OR status: 404",
        )
        if multi_status_resources.total > 0:
            found_statuses = {r.status for r in multi_status_resources._results}
            for status in found_statuses:
                self.assertIn(status, [200, 404])

        # combined filtering
        combined_resources = crawler.get_resources_api(
            sites=[pragmar_site_id],
            query= f"style AND type: {ResourceResultType.PAGE.value}",
            fields=["content", "headers"],
            sort="+url",
            limit=3
        )

        if combined_resources.total > 0:
            for resource in combined_resources._results:
                self.assertEqual(resource.site, pragmar_site_id)
                self.assertEqual(resource.type, ResourceResultType.PAGE)
                resource_dict = resource.to_dict()
                self.assertIn("content", resource_dict)
                self.assertIn("headers", resource_dict)

        # multi-site search
        multisite_resources = crawler.get_resources_api(
            sites=[example_site_id, pragmar_site_id],
            query= f"type: {ResourceResultType.PAGE.value}",
            sort="+url",
            limit=100
        )
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

    def run_pragmar_site_tests(self, crawler: BaseCrawler, site_id:int):

        # all sites
        sites_json = crawler.get_sites_api()
        self.assertTrue(sites_json.total >= 2)

        # single site
        site_one_json = crawler.get_sites_api(ids=[site_id])
        self.assertTrue(site_one_json.total == 1)

        # site with fields
        site_field_json = crawler.get_sites_api(ids=[site_id], fields=["created", "modified"])
        site_field_result = site_field_json._results[0].to_dict()
        self.assertTrue("created" in site_field_result)
        self.assertTrue("modified" in site_field_result)

    def run_pragmar_sort_tests(self, crawler: BaseCrawler, site_id:int):

        random1_resources = crawler.get_resources_api(sites=[site_id], sort="?", limit=20)
        self.assertTrue(random1_resources.total > 0, "Database should contain resources")
        random1_ids = [r.id for r in random1_resources._results]
        random2_resources = crawler.get_resources_api(sites=[site_id], sort="?", limit=20)
        self.assertTrue(random2_resources.total > 0, "Random sort should return results")
        random2_ids = [r.id for r in random2_resources._results]
        if random2_resources.total >= 10:
            self.assertNotEqual(
                random1_ids,
                random2_ids,
                "Random sort should produce different order than standard sort.\nStandard: "
                f"{random1_ids}\nRandom: {random2_ids}"
            )
        else:
            logger.info(f"Skip randomness verification: Not enough resources ({random2_resources.total})")

    def run_pragmar_content_tests(self, crawler: BaseCrawler, site_id:int, html_leniency: bool):

        html_resources = crawler.get_resources_api(
            sites=[site_id],
            query= f"type: {ResourceResultType.PAGE.value}",
            fields=["content", "headers"]
        )

        self.assertTrue(html_resources.total > 0, "Should find HTML resources")
        for resource in html_resources._results:
            resource_dict = resource.to_dict()
            if "content" in resource_dict:
                content =  resource_dict["content"].lower()
                self.assertTrue(
                    "<!DOCTYPE html>" in content or
                    "<html" in content or
                    "<meta" in content or
                    html_leniency,
                    f"HTML content should contain HTML markup: {resource.url}\n\n{resource.content}"
                )

            if "headers" in resource_dict and resource_dict["headers"]:
                self.assertTrue(
                    "Content-Type:" in resource_dict["headers"],
                    f"Headers should contain Content-Type: {resource.url}"
                )

        # script content detection
        script_resources = crawler.get_resources_api(
            sites=[site_id],
            query= f"type: {ResourceResultType.SCRIPT.value}",
            fields=["content", "headers"]
        )
        if script_resources.total > 0:
            for resource in script_resources._results:
                self.assertEqual(resource.type, ResourceResultType.SCRIPT)

        # css content detection
        css_resources = crawler.get_resources_api(
            sites=[site_id],
            query= f"type: {ResourceResultType.CSS.value}",
            fields=["content", "headers"]
        )
        if css_resources.total > 0:
            for resource in css_resources._results:
                self.assertEqual(resource.type, ResourceResultType.CSS)
