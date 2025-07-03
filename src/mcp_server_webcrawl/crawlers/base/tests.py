import sys
import unittest
import asyncio

from typing import Final
from datetime import datetime
from logging import Logger

from mcp_server_webcrawl.crawlers.base.crawler import BaseCrawler
from mcp_server_webcrawl.models.resources import ResourceResultType
from mcp_server_webcrawl.crawlers.base.api import BaseJsonApi
from mcp_server_webcrawl.utils.logger import get_logger

logger: Logger = get_logger()


class BaseCrawlerTests(unittest.TestCase):

    __PRAGMAR_PRIMARY_KEYWORD: Final[str] = "crawler"
    __PRAGMAR_SECONDARY_KEYWORD: Final[str] = "privacy"
    __PRAGMAR_HYPHENATED_KEYWORD: Final[str] = "one-click"

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

        primary_resources = crawler.get_resources_api(
            sites=[site_id],
            query=self.__PRAGMAR_PRIMARY_KEYWORD,
            fields=["content", "headers"],
            limit=1,
        )
        self.assertTrue(primary_resources.total > 0, f"Keyword '{self.__PRAGMAR_PRIMARY_KEYWORD}' should return results")

        secondary_resources = crawler.get_resources_api(
            sites=[site_id],
            query=self.__PRAGMAR_SECONDARY_KEYWORD,
            limit=1,
        )
        self.assertTrue(secondary_resources.total > 0, f"Keyword '{self.__PRAGMAR_SECONDARY_KEYWORD}' should return results")

        self.__run_pragmar_search_tests_fulltext(crawler, site_id, site_resources)
        self.__run_pragmar_search_tests_field_status(crawler, site_id)
        self.__run_pragmar_search_tests_field_headers(crawler, site_id)
        self.__run_pragmar_search_tests_field_content(crawler, site_id)
        self.__run_pragmar_search_tests_field_type(crawler, site_id, site_resources)
        self.__run_pragmar_search_tests_extras(crawler, site_id, site_resources, primary_resources, secondary_resources)


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

        site_resources = crawler.get_resources_api(
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
            ("Total pages", site_resources),
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
    def __run_pragmar_search_tests_field_status(self, crawler: BaseCrawler, site_id: int) -> None:

        # status code filtering
        status_resources = crawler.get_resources_api(
            sites=[site_id],
            query=f"status: 200",
            limit=5,
        )
        self.assertTrue(status_resources.total > 0, "Status filtering should return results")
        for resource in status_resources._results:
            self.assertEqual(resource.status, 200)

        # status code filtering
        appstat_resources = crawler.get_resources_api(
            sites=[site_id],
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

    def __run_pragmar_search_tests_field_headers(self, crawler: BaseCrawler, site_id: int) -> None:

        # supported crawls only (genuine headers data)
        if not self.__class__.__name__ in ("InterroBotTests","KatanaTests", "WarcTests"):
            return

        appstat_any = crawler.get_resources_api(
            sites=[site_id],
            query=f"appstat",
            extras=[],
            limit=1,
        )

        appstat_headers_js = crawler.get_resources_api(
            sites=[site_id],
            query=f"appstat AND headers: javascript",
            extras=[],
            limit=1,
        )

        # https://pragmar.com/media/static/scripts/js/appstat.min.js
        self.assertEqual(appstat_headers_js.total, 1, "Should have exactly one resource in database (appstat.min.js)")

        appstat_headers_nojs = crawler.get_resources_api(
            sites=[site_id],
            query=f"appstat NOT headers: javascript",
            extras=[],
            limit=1,
        )
        self.assertGreater(appstat_headers_nojs.total, 1, "Should have many appstat non-js resources in database")

        appstat_sum: int = appstat_headers_js.total + appstat_headers_nojs.total
        self.assertEqual(appstat_sum, appstat_any.total, "appstat non-js + js resources should sum to all appstat")

    def __run_pragmar_search_tests_field_content(self, crawler: BaseCrawler, site_id: int) -> None:

        mcp_any = crawler.get_resources_api(
            sites=[site_id],
            query=f"mcp",
            extras=[],
            limit=1,
        )

        mcp_content_configuration = crawler.get_resources_api(
            sites=[site_id],
            query=f"mcp AND content: configuration",
            extras=[],
            limit=1,
        )

        # https://pragmar.com/mcp-server-webcrawl/
        self.assertGreaterEqual(mcp_content_configuration.total, 1, "Should have one, possibly more resources (mcp-server-webcrawl)")

        mcp_content_no_configuration = crawler.get_resources_api(
            sites=[site_id],
            query=f"mcp NOT content: configuration",
            extras=[],
            limit=1,
        )
        self.assertGreater(mcp_content_no_configuration.total, 1, "Should have many mcp non-configuration resources")

        mcp_sum: int = mcp_content_configuration.total + mcp_content_no_configuration.total
        self.assertEqual(mcp_sum, mcp_any.total, "mcp non-config + config resources should sum to all mcp")

        mcp_html_content_config = crawler.get_resources_api(
            sites=[site_id],
            query=f"type: html AND mcp AND content: configuration",
            extras=[],
            limit=1,
        )
        self.assertTrue(
            mcp_html_content_config.total <= mcp_content_configuration.total,
            "Adding type constraint should not increase results"
        )

        wildcard_content_search = crawler.get_resources_api(
            sites=[site_id],
            query=f'content: config*',
            extras=[],
            limit=1,
        )
        exact_config_search = crawler.get_resources_api(
            sites=[site_id],
            query=f'content: configuration',
            extras=[],
            limit=1,
        )
        self.assertTrue(
            wildcard_content_search.total >= exact_config_search.total,
            "Wildcard content search should return at least as many results as exact match"
        )

    def __run_pragmar_search_tests_field_type(self, crawler: BaseCrawler, site_id: int, site_resources:BaseJsonApi) -> None:

        html_resources = crawler.get_resources_api(
            sites=[site_id],
            query="type: html",
            extras=[],
            limit=1,
        )

        # page count varies by crawler, 10 is conservative low end
        self.assertGreater(html_resources.total, 10, "Should have exactly 34 HTML resources")

        not_html_resources = crawler.get_resources_api(
            sites=[site_id],
            query="NOT type: html",
            extras=[],
            limit=1,
        )
        self.assertGreater(not_html_resources.total, 10, "Should have exactly 48 non-HTML resources")

        html_sum: int = html_resources.total + not_html_resources.total
        self.assertEqual(html_sum, site_resources.total, "HTML + non-HTML should sum to all resources")

        # keyword + type combination
        appstat_any = crawler.get_resources_api(
            sites=[site_id],
            query="appstat",
            extras=[],
            limit=1,
        )

        appstat_script = crawler.get_resources_api(
            sites=[site_id],
            query="appstat AND type: script",
            extras=[],
            limit=1,
        )

        # https://pragmar.com/media/static/scripts/js/appstat.min.js
        self.assertEqual(appstat_script.total, 1, "Should have exactly one appstat script (appstat.min.js)")

        appstat_not_script = crawler.get_resources_api(
            sites=[site_id],
            query="appstat NOT type: script",
            extras=[],
            limit=1,
        )
        self.assertGreater(appstat_not_script.total, 1, "Should have many appstat non-script resources")

        appstat_sum: int = appstat_script.total + appstat_not_script.total
        self.assertEqual(appstat_sum, appstat_any.total, "appstat script + non-script should sum to all appstat")

        # type OR combinations
        html_or_img = crawler.get_resources_api(
            sites=[site_id],
            query="type: html OR type: img",
            extras=[],
            limit=1,
        )
        self.assertGreater(html_or_img.total, 20, "HTML + IMG should equal 66 resources (34+32)")

        img_resources = crawler.get_resources_api(
            sites=[site_id],
            query="type: img",
            extras=[],
            limit=1,
        )
        self.assertTrue(
            html_or_img.total >= html_resources.total,
            "OR should include all HTML resources"
        )
        self.assertTrue(
            html_or_img.total >= img_resources.total,
            "OR should include all IMG resources"
        )

        # combined filtering
        combined_resources = crawler.get_resources_api(
            sites=[site_id],
            query= f"style AND type: {ResourceResultType.PAGE.value}",
            fields=[],
            sort="+url",
            limit=3,
        )

        if combined_resources.total > 0:
            for resource in combined_resources._results:
                self.assertEqual(resource.site, site_id)
                self.assertEqual(resource.type, ResourceResultType.PAGE)

    def __run_pragmar_search_tests_fulltext(
            self,
            crawler: BaseCrawler,
            site_id: int,
            site_resources:BaseJsonApi
        ) -> None:

        # Boolean workout
        # result counts are fragile, intersections should not be
        # counts are worth the fragility, for now

        boolean_primary_resources  = crawler.get_resources_api(
            sites=[site_id],
            query=f"type: html AND ({self.__PRAGMAR_PRIMARY_KEYWORD})",
            limit=4,
        )

        # varies by crawler, katana doesn't crawl /help/ depth by default
        self.assertTrue(boolean_primary_resources .total > 0, f"Primary search returned {boolean_primary_resources .total}, expected results")

        boolean_secondary_resources = crawler.get_resources_api(
            sites=[site_id],
            query=f"type: html AND ({self.__PRAGMAR_SECONDARY_KEYWORD})",
            limit=12,
        )

        # re: all these > 0 checks, result counts vary by crawler, all have default crawl behaviors/depths/externals
        self.assertTrue(boolean_secondary_resources.total > 0, f"Secondary returned {boolean_secondary_resources.total}, expected results")

        # AND
        primary_and_secondary_resources = crawler.get_resources_api(
            sites=[site_id],
            query=f"type: html AND ({self.__PRAGMAR_PRIMARY_KEYWORD} AND {self.__PRAGMAR_SECONDARY_KEYWORD})",
            limit=1,
        )
        self.assertTrue(primary_and_secondary_resources.total >= 0, f"Primary AND Secondary returned {primary_and_secondary_resources.total}, expected results")

        # OR
        primary_or_secondary_resources = crawler.get_resources_api(
            sites=[site_id],
            query=f"type: html AND ({self.__PRAGMAR_PRIMARY_KEYWORD} OR {self.__PRAGMAR_SECONDARY_KEYWORD})",
            limit=1,
        )
        self.assertTrue(primary_or_secondary_resources.total > 0, f"Primary OR Secondary returned {primary_or_secondary_resources.total}, expected results (union)")

        # NOT
        primary_not_secondary_resources = crawler.get_resources_api(
            sites=[site_id],
            query=f"type: html AND ({self.__PRAGMAR_PRIMARY_KEYWORD} NOT {self.__PRAGMAR_SECONDARY_KEYWORD})",
            limit=1,
        )

        secondary_not_primary_resources = crawler.get_resources_api(
            sites=[site_id],
            query=f"type: html AND ({self.__PRAGMAR_SECONDARY_KEYWORD} NOT {self.__PRAGMAR_PRIMARY_KEYWORD})",
            limit=1,
        )
        self.assertTrue(secondary_not_primary_resources.total >= 0, f"Secondary NOT Primary returned {secondary_not_primary_resources.total}, expected results")

        # logical relationships
        self.assertEqual(
            primary_and_secondary_resources.total,
            boolean_primary_resources .total + boolean_secondary_resources.total - primary_or_secondary_resources.total,
            "Intersection should equal A + B - Union (inclusion-exclusion principle)"
        )

        self.assertEqual(
            primary_not_secondary_resources.total + primary_and_secondary_resources.total,
            boolean_primary_resources .total,
            "Primary NOT Secondary + Primary AND Secondary should equal total Primary results"
        )

        self.assertEqual(
            secondary_not_primary_resources.total + primary_and_secondary_resources.total,
            boolean_secondary_resources.total,
            "Secondary NOT Primary + Primary AND Secondary should equal total Secondary results"
        )

        self.assertEqual(
            primary_not_secondary_resources.total + secondary_not_primary_resources.total + primary_and_secondary_resources.total,
            primary_or_secondary_resources.total,
            "Sum of exclusive sets plus intersection should equal union"
        )

        # complex boolean with field constraints
        primary_and_html_resources = crawler.get_resources_api(
            sites=[site_id],
            query=f"type: html AND ({self.__PRAGMAR_PRIMARY_KEYWORD})",
            limit=1,
        )
        self.assertTrue(primary_and_html_resources.total > 0, f"Primary AND type:html returned {primary_and_html_resources.total}, expected results")
        self.assertTrue(
            primary_and_html_resources.total <= boolean_primary_resources .total,
            "Adding AND constraints should not increase result count"
        )

        # Parentheses grouping
        grouped_resources = crawler.get_resources_api(
            sites=[site_id],
            query=f"type: html AND ({self.__PRAGMAR_PRIMARY_KEYWORD} OR {self.__PRAGMAR_SECONDARY_KEYWORD})",
            limit=1,
        )
        self.assertTrue(grouped_resources.total > 0, f"Grouped OR with HTML filter returned {grouped_resources.total}, expected results")


        hyphenated_resources = crawler.get_resources_api(
            sites=[site_id],
            query=self.__PRAGMAR_HYPHENATED_KEYWORD,
            limit=1,
        )
        self.assertTrue(hyphenated_resources.total > 0, f"Keyword '{self.__PRAGMAR_HYPHENATED_KEYWORD}' should return results")

        double_or_resources = crawler.get_resources_api(
            sites=[site_id],
            query=f"({self.__PRAGMAR_PRIMARY_KEYWORD} OR {self.__PRAGMAR_SECONDARY_KEYWORD} OR moffitor)"
        )
        self.assertGreater(
            double_or_resources.total, 0,
            f"OR query should return some results"
        )
        self.assertLess(
            double_or_resources.total, site_resources.total,
            f"OR query should be less than all results"
        )
        parens_or_and_resources = crawler.get_resources_api(
            sites=[site_id],
            query=f"({self.__PRAGMAR_PRIMARY_KEYWORD} OR {self.__PRAGMAR_SECONDARY_KEYWORD}) AND collaborations "
        )
        # respect the AND, there should be only one result
        # (A OR B) AND C vs. A OR B AND C
        self.assertEqual(
            parens_or_and_resources.total, 1,
            f"(A OR B) AND C should be 1 result (AND collaborations, unless fixture changed)"
        )

        parens_or_and_resources_reverse = crawler.get_resources_api(
            sites=[site_id],
            query=f"collaborations AND ({self.__PRAGMAR_PRIMARY_KEYWORD} OR {self.__PRAGMAR_SECONDARY_KEYWORD}) "
        )
        # respect the AND, there should be only one result
        # (A OR B) AND C vs. A OR B AND C
        self.assertEqual(
            parens_or_and_resources_reverse.total, 1,
            f"A AND (B OR C) should be 1 result (collaborations AND, unless fixture changed)"
        )

        wide_type_resources = crawler.get_resources_api(
            sites=[site_id],
            query=f"type: script OR type: style OR type: iframe OR type: font OR type: text OR type: rss OR type: other"
        )
        self.assertLess(
            wide_type_resources.total, site_resources.total,
            f"A long chained OR should not return all results"
        )
        self.assertGreater(
            wide_type_resources.total, 0,
            f"A long chained OR should return some results"
        )

        complex_and = crawler.get_resources_api(
            sites=[site_id],
            query=f"{self.__PRAGMAR_PRIMARY_KEYWORD} AND type:html AND status:200"
        )

        self.assertTrue(complex_and.total <= boolean_primary_resources .total,
                "Adding AND conditions should not increase results")

        grouped_or = crawler.get_resources_api(
            sites=[site_id],
            query=f"({self.__PRAGMAR_PRIMARY_KEYWORD} OR {self.__PRAGMAR_SECONDARY_KEYWORD}) AND type:html AND status:200"
        )

        self.assertTrue(grouped_or.total <= primary_or_secondary_resources.total,
                "Adding AND conditions to OR should not increase results")

    def __run_pragmar_search_tests_extras(
            self,
            crawler: BaseCrawler,
            site_id: int,
            site_resources:BaseJsonApi,
            primary_resources:BaseJsonApi,
            secondary_resources:BaseJsonApi,
        ) -> None:

        snippet_resources = crawler.get_resources_api(
            sites=[site_id],
            query=f"{self.__PRAGMAR_PRIMARY_KEYWORD} AND type: html",
            extras=["snippets"],
            limit=1,
        )
        self.assertIn("snippets", snippet_resources._results[0].to_dict()["extras"],
                "First result should have snippets in extras")

        xpath_count_resources = crawler.get_resources_api(
            sites=[site_id],
            query=self.__PRAGMAR_PRIMARY_KEYWORD,
            extras=["markdown"],
            limit=1,
        )
        self.assertIn("markdown", xpath_count_resources._results[0].to_dict()["extras"],
                "First result should have markdown in extras")

        xpath_count_resources = crawler.get_resources_api(
            sites=[site_id],
            query="url: pragmar.com AND status: 200",
            extras=["xpath"],
            extrasXpath=["count(//h1)"],
            limit=1,
            sort="-url"
        )
        self.assertIn("xpath", xpath_count_resources._results[0].to_dict()["extras"],
                "First result should have xpath in extras")
        self.assertEqual(len(xpath_count_resources._results[0].to_dict()["extras"]["xpath"]),
                1, "Should be exactly one H1 hit in xpath extras")

        xpath_h1_text_resources = crawler.get_resources_api(
            sites=[site_id],
            query="url: https://pragmar.com AND status: 200",
            extras=["xpath"],
            extrasXpath=["//h1/text()"],
            limit=1,
            sort="+url"
        )
        self.assertIn("xpath", xpath_h1_text_resources._results[0].to_dict()["extras"],
                "First result should have xpath in extras")
        self.assertTrue( xpath_h1_text_resources._results[0].to_dict()["extras"] is not None,
                "Should have pragmar in fixture h1")

        # should be pragmar homepage, assert "pragmar" in h1
        first_xpath_result = xpath_h1_text_resources._results[0].to_dict()["extras"]["xpath"][0]["value"].lower()
        self.assertTrue("pragmar" in first_xpath_result,
                f"Should have pragmar in fixture homepage h1 ({first_xpath_result})")

        combined_resources = crawler.get_resources_api(
            sites=[site_id],
            query=self.__PRAGMAR_PRIMARY_KEYWORD,
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
