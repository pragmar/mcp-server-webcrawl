import unittest
import asyncio
import sys

from datetime import datetime
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
        hyphenated_keyword = "one-click"

        primary_resources = crawler.get_resources_api(
            sites=[site_id],
            query=primary_keyword,
            fields=["content", "headers"],
            limit=1,
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
            query=secondary_keyword,
            limit=1,
        )
        self.assertTrue(secondary_resources.total > 0, f"Keyword '{secondary_keyword}' should return results")

        hyphenated_resources = crawler.get_resources_api(
            sites=[site_id],
            query=hyphenated_keyword,
            limit=1,
        )
        self.assertTrue(hyphenated_resources.total > 0, f"Keyword '{hyphenated_keyword}' should return results")

        # triple OR bug turns out to be a translation issue condensing to one
        # fulltext MATCH statement.
        all_resources = crawler.get_resources_api(
            sites=[site_id],
            query="",  # empty query returns all resources
        )
        triple_or_resources = crawler.get_resources_api(
            sites=[site_id],
            query=f"({primary_keyword} OR {secondary_keyword} OR moffitor)"
        )
        self.assertGreater(
            triple_or_resources.total, 0,
            f"Triple OR query returned 0 resources instead of filtered subset"
        )

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
            limit=1,
        )
        self.assertIn("snippets", snippet_resources._results[0].to_dict()["extras"],
                "First result should have snippets in extras")

        markdown_resources = crawler.get_resources_api(
            sites=[site_id],
            query=primary_keyword,
            extras=["markdown"],
            limit=1,
        )
        self.assertIn("markdown", markdown_resources._results[0].to_dict()["extras"],
                "First result should have markdown in extras")

        combined_resources = crawler.get_resources_api(
            sites=[site_id],
            query=primary_keyword,
            extras=["snippets", "markdown"],
            limit=1,
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
            fields=["created", "modified", "time"],
            limit=5,
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
                limit=1,
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
            limit=1,
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
            limit=5,
        )
        self.assertTrue(status_resources.total > 0, "Status filtering should return results")
        for resource in status_resources._results:
            self.assertEqual(resource.status, 200)

        # status code filtering
        appstat_resources = crawler.get_resources_api(
            sites=[pragmar_site_id],
            query=f"status: 200 AND url: https://pragmar.com/appstat*",
            limit=5,
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
            limit=3,
        )

        if combined_resources.total > 0:
            for resource in combined_resources._results:
                self.assertEqual(resource.site, pragmar_site_id)
                self.assertEqual(resource.type, ResourceResultType.PAGE)
                resource_dict = resource.to_dict()
                self.assertIn("content", resource_dict)
                self.assertIn("headers", resource_dict)

        # multi-site search, verify we got results from both sites
        multisite_resources = crawler.get_resources_api(
            sites=[example_site_id, pragmar_site_id],
            query= f"type: {ResourceResultType.PAGE.value}",
            sort="+url",
            limit=10,
        )
        found_sites = set()
        for resource in multisite_resources._results:
            found_sites.add(resource.site)
        self.assertEqual(len(found_sites), 2, "Should have results from both sites")

        # Boolean workout
        # result counts are fragile, intersections should not be
        # counts are worth the fragility, for now

        claude_resources = crawler.get_resources_api(
            sites=[pragmar_site_id],
            query=f"type: html AND (claude)",
            limit=4,
        )

        # varies by crawler, katana doesn't crawl /help/ depth by default
        self.assertTrue(claude_resources.total in [1,2,3,4,5,6], f"Claude search returned {claude_resources.total}, expected 3/4/5 results")

        mcp_resources = crawler.get_resources_api(
            sites=[pragmar_site_id],
            query=f"type: html AND (mcp)",
            limit=12,
        )
        # varies by crawler, katana doesn't crawl /help/ depth by default
        self.assertTrue(mcp_resources.total in [2, 3, 4, 5, 6, 7, 8, 12, 13, 16, 17], f"MCP returned {mcp_resources.total}, expected")

        # AND
        claude_and_mcp_resources = crawler.get_resources_api(
            sites=[pragmar_site_id],
            query=f"type: html AND (claude AND mcp)",
            limit=1,
        )
        self.assertTrue(claude_resources.total in [1,2,3,4,5,6], f"Claude AND MCP returned {claude_resources.total}, expected 3/4")

        # OR
        claude_or_mcp_resources = crawler.get_resources_api(
            sites=[pragmar_site_id],
            query=f"type: html AND (claude OR mcp)",
            limit=1,
        )
        self.assertTrue(claude_or_mcp_resources.total in [2,3,4,5,6,12,13,15,16,17], f"Claude OR MCP returned {claude_or_mcp_resources.total}, expected 16 results (union)")

        # NOT
        claude_not_mcp_resources = crawler.get_resources_api(
            sites=[pragmar_site_id],
            query=f"type: html AND (claude NOT mcp)",
            limit=1,
        )

        self.assertEqual(claude_not_mcp_resources.total, 0, "Claude NOT MCP should return 0 results")

        mcp_not_claude_resources = crawler.get_resources_api(
            sites=[pragmar_site_id],
            query=f"type: html AND (mcp NOT claude)",
            limit=1,
        )
        self.assertTrue(mcp_not_claude_resources.total in [1,2,3,4,7,8,9,10,11,12,13], f"MCP NOT Claude returned {mcp_not_claude_resources.total}, expected 11/12/13")

        # logical relationships
        self.assertEqual(
            claude_and_mcp_resources.total,
            claude_resources.total + mcp_resources.total - claude_or_mcp_resources.total,
            "Intersection should equal A + B - Union (inclusion-exclusion principle)"
        )

        self.assertEqual(
            claude_not_mcp_resources.total + claude_and_mcp_resources.total,
            claude_resources.total,
            "Claude NOT MCP + Claude AND MCP should equal total Claude results"
        )

        self.assertEqual(
            mcp_not_claude_resources.total + claude_and_mcp_resources.total,
            mcp_resources.total,
            "MCP NOT Claude + Claude AND MCP should equal total MCP results"
        )

        self.assertEqual(
            claude_not_mcp_resources.total + mcp_not_claude_resources.total + claude_and_mcp_resources.total,
            claude_or_mcp_resources.total,
            "Sum of exclusive sets plus intersection should equal union"
        )

        # complex boolean with field constraints
        # url: pragmar used without .com to support WARC too
        claude_and_html_resources = crawler.get_resources_api(
            sites=[pragmar_site_id],
            query=f"type: html AND (claude)",
            limit=1,
        )
        self.assertTrue(claude_and_html_resources.total in [1,2,3,4,5,6], f"Claude AND type:html returned {claude_and_html_resources.total}, expected 3/6")
        self.assertTrue(
            claude_and_html_resources.total <= claude_resources.total,
            "Adding AND constraints should not increase result count"
        )

        # Parentheses grouping
        grouped_resources = crawler.get_resources_api(
            sites=[pragmar_site_id],
            query=f"type: html AND (claude OR mcp)",
            limit=1,
        )
        self.assertTrue(grouped_resources.total in [2, 3, 4, 5, 6, 11, 12, 13], f"Grouped OR with HTML filter returned {grouped_resources.total}, expected 3/6")

    def run_pragmar_tokenizer_tests(self, crawler: BaseCrawler, site_id:int):
        """
        fts hyphens and underscores are particularly challenging, thus
        have a dedicated test. these must be configured in multiple places
        including CREATE TABLE ... tokenizer, as well as handled by the query
        parser.
        """

        mcp_resources_keyword = crawler.get_resources_api(
            sites=[site_id],
            query='"mcp-server-webcrawl"',
            fields=[],
            limit=1,
        )
        mcp_resources_quoted = crawler.get_resources_api(
            sites=[site_id],
            query='"mcp-server-webcrawl"',
            fields=[],
            limit=1,
        )
        self.assertTrue(mcp_resources_keyword.total > 0, "Should find mcp-server-webcrawl in HTML")
        self.assertTrue(mcp_resources_quoted.total > 0, "Should find \"mcp-server-webcrawl\" (phrase) in HTML")
        self.assertTrue(mcp_resources_quoted.total == mcp_resources_keyword.total, "Quoted and unquoted equivalence expected")
        mcp_resources_wildcarded = crawler.get_resources_api(
            sites=[site_id],
            query='mcp*',
            fields=[],
            limit=1,
        )
        self.assertTrue(mcp_resources_wildcarded.total > 0, "Should find mcp-server-* in HTML")

        combo_and_resources_keyword = crawler.get_resources_api(
            sites=[site_id],
            query='"mcp-server-webcrawl" AND "one-click"',
            fields=[],
            limit=1,
        )
        combo_and_resources_quoted = crawler.get_resources_api(
            sites=[site_id],
            query='mcp-server-webcrawl AND one-click',
            fields=[],
            limit=1,
        )
        self.assertTrue(combo_and_resources_keyword.total > 0, "Should find mcp-server-webcrawl in HTML")
        self.assertTrue(combo_and_resources_quoted.total > 0, "Should find \"mcp-server-webcrawl\" (phrase) in HTML")
        self.assertTrue(combo_and_resources_keyword.total == combo_and_resources_quoted.total, "Quoted and unquoted equivalence expected")

        combo_or_resources_keyword = crawler.get_resources_api(
            sites=[site_id],
            query='"mcp-server-webcrawl" OR "one-click"',
            fields=[],
            limit=1,
        )
        combo_or_resources_quoted = crawler.get_resources_api(
            sites=[site_id],
            query='mcp-server-webcrawl OR one-click',
            fields=[],
            limit=1,
        )
        self.assertTrue(combo_or_resources_keyword.total > 0, "Should find mcp-server-webcrawl in HTML")
        self.assertTrue(combo_or_resources_quoted.total > 0, "Should find \"mcp-server-webcrawl\" (phrase) in HTML")
        self.assertTrue(combo_or_resources_keyword.total == combo_or_resources_quoted.total, "Quoted and unquoted equivalence expected")

        combo_not_resources_keyword = crawler.get_resources_api(
            sites=[site_id],
            query='"mcp-server-webcrawl" NOT "one-click"',
            fields=[],
            limit=1,
        )
        combo_not_resources_quoted = crawler.get_resources_api(
            sites=[site_id],
            query='mcp-server-webcrawl NOT one-click',
            fields=[],
            limit=1,
        )
        combo_and_not_resources_quoted = crawler.get_resources_api(
            sites=[site_id],
            query='mcp-server-webcrawl AND NOT one-click',
            fields=[],
            limit=1,
        )
        self.assertTrue(combo_not_resources_keyword.total > 0, "Should find mcp-server-webcrawl in HTML")
        self.assertTrue(combo_not_resources_quoted.total > 0, "Should find \"mcp-server-webcrawl\" (phrase) in HTML")
        self.assertTrue(combo_not_resources_keyword.total == combo_not_resources_quoted.total, "Quoted and unquoted equivalence expected")
        self.assertTrue(combo_not_resources_keyword.total == combo_and_not_resources_quoted.total, f"NOT ({combo_not_resources_keyword.total}) and AND NOT ({combo_and_not_resources_quoted.total}) equivalence expected")
        self.assertTrue(mcp_resources_keyword.total >= combo_and_resources_keyword.total, "Total records should be greater or equal to ANDs.")
        self.assertTrue(mcp_resources_keyword.total <= combo_or_resources_keyword.total, "Total records should be less than or equal to ORs.")
        self.assertTrue(mcp_resources_keyword.total > combo_not_resources_keyword.total, "Total records should be greater than to NOTs.")

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
            fields=["content", "headers"],
            limit=1,
        )
        if script_resources.total > 0:
            for resource in script_resources._results:
                self.assertEqual(resource.type, ResourceResultType.SCRIPT)

        # css content detection
        css_resources = crawler.get_resources_api(
            sites=[site_id],
            query= f"type: {ResourceResultType.CSS.value}",
            fields=["content", "headers"],
            limit=1,
        )
        if css_resources.total > 0:
            for resource in css_resources._results:
                self.assertEqual(resource.type, ResourceResultType.CSS)

    def run_pragmar_report(self, crawler: BaseCrawler, site_id: int, heading: str):
        """
        Generate a comprehensive report of all resources for a site.
        Returns a formatted string with counts and URLs by type.
        """

        all_resources = crawler.get_resources_api(
            sites=[site_id],
            query="",
            limit=100,
        )

        html_resources = crawler.get_resources_api(
            sites=[site_id],
            query=f"type: {ResourceResultType.PAGE.value}",
            limit=100,
        )

        css_resources = crawler.get_resources_api(
            sites=[site_id],
            query=f"type: {ResourceResultType.CSS.value}",
            limit=100,
        )

        js_resources = crawler.get_resources_api(
            sites=[site_id],
            query=f"type: {ResourceResultType.SCRIPT.value}",
            limit=100,
        )

        image_resources = crawler.get_resources_api(
            sites=[site_id],
            query=f"type: {ResourceResultType.IMAGE.value}",
            limit=100,
        )

        mcp_resources = crawler.get_resources_api(
            sites=[site_id],
            query=f"type: html AND (mcp)",
            limit=100,
        )

        report_lines = []
        sections = [
            ("Total pages", all_resources),
            ("Total HTML", html_resources),
            ("Total MCP search hits", mcp_resources),
            ("Total CSS", css_resources),
            ("Total JS", js_resources),
            ("Total Images", image_resources)
        ]

        for i, (section_name, resource_obj) in enumerate(sections):
            report_lines.append(f"{section_name}: {resource_obj.total}")
            for resource in resource_obj._results:
                report_lines.append(resource.url)
            if i < len(sections) - 1:
                report_lines.append("")

        now = datetime.now()
        lines_together = "\n".join(report_lines)

        return f"""
**********************************************************************************
* {heading} {now.isoformat()}                                                    *
**********************************************************************************
{lines_together}
"""