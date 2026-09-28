import sys
import unittest
import asyncio
import json
import tempfile
import threading
import time
import uuid

from typing import Final
from datetime import datetime
from logging import Logger
from pathlib import Path
from unittest.mock import patch

from mcp_server_webcrawl.crawlers.base.adapter import SitesGroup, SitesStat, INDEXED_MANAGER_STATS_MAX
from mcp_server_webcrawl.crawlers.base.crawler import BaseCrawler
from mcp_server_webcrawl.crawlers.wget.adapter import WgetManager, manager as wget_manager
from mcp_server_webcrawl.crawlers.wget.crawler import WgetCrawler
from mcp_server_webcrawl.models.resources import ResourceResultType, RESOURCES_TOOL_NAME
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
        self.__run_pragmar_search_tests_grouping(crawler, site_id, site_resources)
        self.__run_pragmar_search_tests_negation(crawler, site_id)
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

    def run_sites_attribution_tests(self, crawler: BaseCrawler, pragmar_site_id: int, example_site_id: int):
        """
        Multi-site results carry the right site, whatever order the ids arrive in,
        and ids that don't exist are dropped rather than paired with another's data.
        """
        for site_ids in ([pragmar_site_id, example_site_id], [example_site_id, pragmar_site_id]):
            multi_results = crawler.get_resources_api(sites=site_ids, sort="?", limit=20).get_results()
            self.assertTrue(len(multi_results) > 0, f"multi-site search {site_ids} should return results")
            for result in multi_results:
                owned = crawler.get_resources_api(sites=[result.site], query=f"id: {result.id}", limit=1)
                self.assertEqual(owned.total, 1, f"{result.url} labeled site {result.site}, not found there ({site_ids})")

        bogus_results = crawler.get_resources_api(sites=[pragmar_site_id, 987654321], limit=20).get_results()
        self.assertTrue(len(bogus_results) > 0, "a bogus site id should not sink the valid one")
        self.assertTrue(all(r.site == pragmar_site_id for r in bogus_results), "a bogus site id must not label results")

    def run_query_error_tests(self, crawler: BaseCrawler, pragmar_site_id: int):
        """
        A query that can't run reports an error, rather than returning the whole site
        (unfiltered) or nothing (no matches) in silence.
        """
        for query in ["(privacy OR", "privacy AND", "title: privacy", "privacy \"", "status: >= "]:
            api = crawler.get_resources_api(sites=[pragmar_site_id], query=query)
            self.assertEqual(api.total, 0, f"broken query {query!r} should return nothing")
            self.assertTrue(len(api._errors) > 0, f"broken query {query!r} should report an error")

        # punctuated terms are quoted for fts5, not a syntax error
        for query in ["pragmar.com", "index.html", "c++", "AT&T", "don't", "café"]:
            api = crawler.get_resources_api(sites=[pragmar_site_id], query=query)
            self.assertEqual(api._errors, [], f"term {query!r} should run without error")

    def run_sites_resources_tests(self, crawler: BaseCrawler, pragmar_site_id: int, example_site_id: int):

        self.run_sites_attribution_tests(crawler, pragmar_site_id, example_site_id)
        self.run_query_error_tests(crawler, pragmar_site_id)

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
            self.assertIsNotNone(resource_dict["time"], "Time should not be None")

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
        # limit 100 sees all the pages, otherwise ArchiveBox needs -url
        # and everything else +url to float unique sites in a small result set
        # limit 100 is slower but more resilient
        multisite_resources = crawler.get_resources_api(
            sites=[example_site_id, pragmar_site_id],
            query= f"type: {ResourceResultType.PAGE.value}",
            sort="+url",
            limit=100,
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
        self.assertTrue(mcp_resources_keyword.total > combo_not_resources_keyword.total, "Total records should be greater than NOTs.")



    def run_pragmar_site_tests(self, crawler: BaseCrawler, site_id:int):

        # all sites
        sites_json = crawler.get_sites_api()
        self.assertTrue(sites_json.total >= 2)

        # single site
        site_json = crawler.get_sites_api(ids=[site_id])
        self.assertTrue(site_json.total == 1)

        # site with fields
        site_field_json = crawler.get_sites_api(ids=[site_id], fields=["created", "modified"])
        site_field_result = site_field_json._results[0].to_dict()
        self.assertTrue("created" in site_field_result)
        self.assertTrue("modified" in site_field_result)

    def run_pragmar_sort_tests(self, crawler: BaseCrawler, site_id: int):
        """
        Test sorting functionality with performance optimizations.
        """
        sorted_default = crawler.get_resources_api(sites=[site_id], limit=3, fields=[])
        sorted_url_ascending = crawler.get_resources_api(sites=[site_id], sort="+url", limit=3, fields=[])
        sorted_url_descending = crawler.get_resources_api(sites=[site_id], sort="-url", limit=3, fields=[])

        self.assertTrue(sorted_url_ascending.total > 0, "Database should contain resources")
        self.assertTrue(sorted_url_descending.total > 0, "Database should contain resources")
        if len(sorted_default._results) > 0 and len(sorted_url_ascending._results) > 0:
            default_urls = [r.url for r in sorted_default._results]
            ascending_urls = [r.url for r in sorted_url_ascending._results]
            self.assertEqual(default_urls, ascending_urls, "Default sort should match +url sort")

        sorted_size_ascending = crawler.get_resources_api(sites=[site_id], sort="+size", limit=3, fields=["size"])
        sorted_size_descending = crawler.get_resources_api(sites=[site_id], sort="-size", limit=3, fields=["size"])
        if len(sorted_url_ascending._results) > 1:
            for i in range(len(sorted_url_ascending._results) - 1):
                self.assertLessEqual(sorted_url_ascending._results[i].url,
                        sorted_url_ascending._results[i + 1].url, "URLs should be ascending")
        if len(sorted_url_descending._results) > 1:
            for i in range(len(sorted_url_descending._results) - 1):
                self.assertGreaterEqual(sorted_url_descending._results[i].url,
                        sorted_url_descending._results[i + 1].url, "URLs should be descending")
        if len(sorted_size_ascending._results) > 1:
            for i in range(len(sorted_size_ascending._results) - 1):
                self.assertLessEqual(sorted_size_ascending._results[i].to_dict()["size"],
                        sorted_size_ascending._results[i + 1].to_dict()["size"], "Sizes should be ascending")
        if len(sorted_size_descending._results) > 1:
            for i in range(len(sorted_size_descending._results) - 1):
                self.assertGreaterEqual(sorted_size_descending._results[i].to_dict()["size"],
                        sorted_size_descending._results[i + 1].to_dict()["size"], "Sizes should be descending")

        random_1 = crawler.get_resources_api(sites=[site_id], sort="?", limit=20, fields=[])
        random_2 = crawler.get_resources_api(sites=[site_id], sort="?", limit=20, fields=[])
        self.assertTrue(random_1.total > 0, "Random sort should return results")
        if random_1.total >= 10:
            self.assertNotEqual([r.id for r in random_1._results], [r.id for r in random_2._results],
                            "Random sort should produce different orders")
        else:
            logger.info(f"Skip randomness verification: Not enough resources ({random_1.total})")

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
        self.assertGreaterEqual(len(appstat_resources._results), 3, f"Should have at least 3 results in appstat resources")

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
        self.assertGreater(html_resources.total, 10, "Should have greater than 10 HTML resources")

        not_html_resources = crawler.get_resources_api(
            sites=[site_id],
            query="NOT type: html",
            extras=[],
            limit=1,
        )
        # wget is HTML-only fixture
        self.assertGreater(not_html_resources.total, 10, "Should have greater than 10 non-HTML resources")

        html_sum: int = html_resources.total + not_html_resources.total
        self.assertEqual(html_sum, site_resources.total, "HTML + non-HTML should sum to all resources")

        # keyword + type combination
        appstat_any = crawler.get_resources_api(
            sites=[site_id],
            query="appstat",
            limit=10,
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

        self.assertGreater(html_or_img.total, 20, "HTML + IMG should be greater than 20 resources")

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
        self.assertTrue(boolean_primary_resources .total > 0, f"Primary search should return results")

        boolean_secondary_resources = crawler.get_resources_api(
            sites=[site_id],
            query=f"type: html AND ({self.__PRAGMAR_SECONDARY_KEYWORD})",
            limit=12,
        )

        # re: all these > 0 checks, result counts vary by crawler, all have default crawl behaviors/depths/externals
        self.assertTrue(boolean_secondary_resources.total > 0, f"Secondary search should return results")

        # AND
        primary_and_secondary_resources = crawler.get_resources_api(
            sites=[site_id],
            query=f"type: html AND ({self.__PRAGMAR_PRIMARY_KEYWORD} AND {self.__PRAGMAR_SECONDARY_KEYWORD})",
            limit=1,
        )
        self.assertTrue(primary_and_secondary_resources.total > 0, f"Primary AND Secondary should return results")

        # OR
        primary_or_secondary_resources = crawler.get_resources_api(
            sites=[site_id],
            query=f"type: html AND ({self.__PRAGMAR_PRIMARY_KEYWORD} OR {self.__PRAGMAR_SECONDARY_KEYWORD})",
            limit=1,
        )
        self.assertTrue(primary_or_secondary_resources.total > 0, f"Primary OR Secondary should return results (union)")

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
        # 'privacy' pages are a subset of 'crawler' pages in this fixture, so this can be 0
        self.assertGreaterEqual(secondary_not_primary_resources.total, 0,
                "Secondary NOT Primary may be empty (privacy subset of crawler in fixture)")

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
        self.assertTrue(primary_and_html_resources.total > 0, f"Primary AND type:html should return results")
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
        self.assertTrue(grouped_resources.total > 0, f"Grouped OR with HTML filter should return results")


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
        self.assertLessEqual(
            double_or_resources.total, site_resources.total,
            f"OR query should be less than, or equal to all results"
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

        # URL OR parsing, url is a special case, an fts5 field searched with SQL LIKE
        url_or_simple = crawler.get_resources_api(
            sites=[site_id], query="url: pragmar.com OR url: example.com", limit=1)
        url_or_with_type = crawler.get_resources_api(
            sites=[site_id], query="type: html AND (url: pragmar.com OR url: example.com)", limit=1)
        html_total = crawler.get_resources_api(
            sites=[site_id], query="type: html", limit=1)
        self.assertTrue(url_or_with_type.total <= url_or_simple.total,
            f"AND constraint should not increase results")
        self.assertTrue(url_or_with_type.total <= html_total.total,
            f"URL filter should not exceed HTML total")
        # the two asserts above pass on 0, which is what a sqlite error returns
        self.assertEqual(url_or_with_type.total, html_total.total,
            f"Every pragmar HTML url contains pragmar.com, (url OR url) should keep all of them")

    def __get_search_ids(self, crawler: BaseCrawler, site_id: int, query: str, **kwargs) -> set[int]:
        """
        Complete id set for a query, for set-logic assertions (fixture queries stay under a page).
        """
        resources = crawler.get_resources_api(sites=[site_id], query=query, limit=100, **kwargs)
        self.assertLessEqual(resources.total, 100, f"Set assertions need the complete result, narrow: {query}")
        return {resource.id for resource in resources._results}

    def __run_pragmar_search_tests_grouping(self, crawler: BaseCrawler, site_id: int, site_resources:BaseJsonApi) -> None:
        """
        Parentheses and chained operators, asserted as set logic so they hold on every
        fixture. Every count here is checked against the sets it is built from, never
        just against a ceiling, because a query sqlite refuses comes back as 0 results.
        """

        # chained id ORs, the last term used to carry a dangling OR, which joined the
        # default status clause as OR status >= 100 and returned the whole site
        html_page = crawler.get_resources_api(sites=[site_id], query="type: html", sort="+url", limit=4)
        html_ids: list[int] = [resource.id for resource in html_page._results]
        self.assertEqual(len(html_ids), 4, "Need 4 HTML resources to chain")
        for chain_length in (2, 3, 4):
            chained_query: str = " OR ".join(f"id: {resource_id}" for resource_id in html_ids[:chain_length])
            chained_ids: set[int] = self.__get_search_ids(crawler, site_id, chained_query)
            self.assertEqual(chained_ids, set(html_ids[:chain_length]),
                f"{chain_length} ORed ids should return exactly those ids, not the site")

        id_a, id_b, id_c, id_d = html_ids
        chained_regex = crawler.get_resources_api(
            sites=[site_id],
            query=f"id: {id_a} OR id: {id_b} OR id: {id_c} OR id: {id_d}",
            extras=["regex"],
            extrasRegex=["pragmar"],
            limit=4,
        )
        self.assertEqual(chained_regex.total, 4, "Chained id ORs with the regex extra should return exactly 4")
        self.assertLess(chained_regex.total, site_resources.total, "Chained id ORs should not return all results")

        self.assertEqual(
            self.__get_search_ids(crawler, site_id, f"id: {id_a} OR (id: {id_b} OR id: {id_c})"),
            {id_a, id_b, id_c},
            "A OR (B OR C) over ids should return exactly A, B, C"
        )
        self.assertEqual(
            self.__get_search_ids(crawler, site_id, f"(id: {id_a} OR id: {id_b}) AND (id: {id_b} OR id: {id_c})"),
            {id_b},
            "(A OR B) AND (B OR C) over ids should return only B, adjacent groups must not merge"
        )
        self.assertEqual(
            self.__get_search_ids(crawler, site_id, f"(id: {id_a} OR id: {id_b}) NOT id: {id_a}"),
            {id_b},
            "(A OR B) NOT A over ids should return only B"
        )

        # grouped url ORs ANDed with a fulltext group, SQL precedence used to run it as
        # url OR url OR (url AND MATCH), which sqlite refuses (MATCH under an OR)
        url_group: str = "url: pragmar.com/appstat* OR url: pragmar.com/mcp-server-webcrawl*"
        keyword_group: str = f"{self.__PRAGMAR_PRIMARY_KEYWORD} OR {self.__PRAGMAR_SECONDARY_KEYWORD}"
        url_ids: set[int] = self.__get_search_ids(crawler, site_id, url_group)
        keyword_ids: set[int] = self.__get_search_ids(crawler, site_id, keyword_group)
        primary_ids: set[int] = self.__get_search_ids(crawler, site_id, self.__PRAGMAR_PRIMARY_KEYWORD)
        self.assertGreater(len(url_ids & keyword_ids), 0, "Fixture should have url group and keyword group overlap")

        self.assertEqual(
            self.__get_search_ids(crawler, site_id, f"({url_group}) AND ({keyword_group})"),
            url_ids & keyword_ids,
            "(url OR url) AND (kw OR kw) should be the intersection of its groups"
        )
        self.assertEqual(
            self.__get_search_ids(crawler, site_id, f"({keyword_group}) AND ({url_group})"),
            url_ids & keyword_ids,
            "(kw OR kw) AND (url OR url) should match the reverse order"
        )
        self.assertEqual(
            self.__get_search_ids(crawler, site_id, f"({url_group}) AND {self.__PRAGMAR_PRIMARY_KEYWORD}"),
            url_ids & primary_ids,
            "(url OR url) AND kw should be the intersection"
        )
        self.assertEqual(
            self.__get_search_ids(crawler, site_id, f"{self.__PRAGMAR_PRIMARY_KEYWORD} AND ({url_group})"),
            url_ids & primary_ids,
            "kw AND (url OR url) should be the intersection"
        )

        html_ids_all: set[int] = self.__get_search_ids(crawler, site_id, "type: html")
        self.assertEqual(
            self.__get_search_ids(crawler, site_id, f"type: html AND ({url_group})"),
            html_ids_all & url_ids,
            "type: html AND (url OR url) should be the intersection"
        )

        appstat_url_ids: set[int] = self.__get_search_ids(crawler, site_id, "url: pragmar.com/appstat*")
        url_not_appstat: set[int] = self.__get_search_ids(crawler, site_id, f"({url_group}) NOT url: pragmar.com/appstat*")
        self.assertGreater(len(url_not_appstat), 0, "(url OR url) NOT url should leave the other url")
        self.assertEqual(url_not_appstat, url_ids - appstat_url_ids,
            "(url OR url) NOT url should be the difference")

        # fulltext groups, compressed into one fts5 querystring where AND also outranks
        # OR, so adjacent and nested groups each need their own parentheses
        secondary_ids: set[int] = self.__get_search_ids(crawler, site_id, self.__PRAGMAR_SECONDARY_KEYWORD)
        appstat_ids: set[int] = self.__get_search_ids(crawler, site_id, "appstat")
        mcp_ids: set[int] = self.__get_search_ids(crawler, site_id, "mcp")
        self.assertEqual(
            self.__get_search_ids(crawler, site_id,
                f"({self.__PRAGMAR_PRIMARY_KEYWORD} OR {self.__PRAGMAR_SECONDARY_KEYWORD}) AND (appstat OR mcp)"),
            (primary_ids | secondary_ids) & (appstat_ids | mcp_ids),
            "(A OR B) AND (C OR D) fulltext should keep both groups"
        )
        self.assertEqual(
            self.__get_search_ids(crawler, site_id,
                f"({self.__PRAGMAR_PRIMARY_KEYWORD} AND ({self.__PRAGMAR_SECONDARY_KEYWORD} OR appstat))"),
            primary_ids & (secondary_ids | appstat_ids),
            "(A AND (B OR C)) fulltext should keep the inner group"
        )
        self.assertEqual(
            self.__get_search_ids(crawler, site_id,
                f"(({self.__PRAGMAR_SECONDARY_KEYWORD} OR appstat) AND {self.__PRAGMAR_PRIMARY_KEYWORD}) OR mcp"),
            ((secondary_ids | appstat_ids) & primary_ids) | mcp_ids,
            "((A OR B) AND C) OR D fulltext should keep both levels"
        )

    def __run_pragmar_search_tests_negation(self, crawler: BaseCrawler, site_id: int) -> None:
        """
        NOT and mixed OR, as set logic against the site's own universe (the empty
        query, which carries the same default status floor). De Morgan, prefix NOT
        taking one operand, and fulltext ORed with other fields, all as written with
        standard precedence (NOT > AND > OR).
        """
        primary: str = self.__PRAGMAR_PRIMARY_KEYWORD
        secondary: str = self.__PRAGMAR_SECONDARY_KEYWORD
        appstat_url: str = "url: pragmar.com/appstat*"
        mcp_url: str = "url: pragmar.com/mcp-server-webcrawl*"

        all_ids: set[int] = self.__get_search_ids(crawler, site_id, "")
        html_ids: set[int] = self.__get_search_ids(crawler, site_id, "type: html")
        img_ids: set[int] = self.__get_search_ids(crawler, site_id, "type: img")
        primary_ids: set[int] = self.__get_search_ids(crawler, site_id, primary)
        secondary_ids: set[int] = self.__get_search_ids(crawler, site_id, secondary)
        appstat_ids: set[int] = self.__get_search_ids(crawler, site_id, "appstat")
        appstat_url_ids: set[int] = self.__get_search_ids(crawler, site_id, appstat_url)
        mcp_url_ids: set[int] = self.__get_search_ids(crawler, site_id, mcp_url)

        # the sets have to be partial, or the equalities below prove nothing
        for label, ids in [("html", html_ids), (primary, primary_ids), (secondary, secondary_ids), ("appstat url", appstat_url_ids)]:
            self.assertGreater(len(ids), 0, f"Fixture should have {label} resources")
            self.assertLess(len(ids), len(all_ids), f"Fixture {label} resources should not be the whole site")

        cases: list[tuple[str, set[int], str]] = [
            # De Morgan
            (f"NOT ({appstat_url} OR {mcp_url})", all_ids - (appstat_url_ids | mcp_url_ids), "NOT (A OR B) is everything but A and B"),
            (f"NOT {appstat_url} AND NOT {mcp_url}", all_ids - (appstat_url_ids | mcp_url_ids), "NOT A AND NOT B equals NOT (A OR B)"),
            (f"NOT ({primary} OR {secondary})", all_ids - (primary_ids | secondary_ids), "NOT (kw OR kw) is everything but either"),
            (f"NOT ({primary} AND {secondary})", all_ids - (primary_ids & secondary_ids), "NOT (kw AND kw) is everything but both"),
            # prefix NOT takes one operand
            (f"NOT {appstat_url} AND type: html", html_ids - appstat_url_ids, "NOT A AND B negates only A"),
            (f"type: html AND NOT {appstat_url}", html_ids - appstat_url_ids, "B AND NOT A negates only A"),
            (f"NOT {primary} AND {secondary}", secondary_ids - primary_ids, "NOT kw AND kw negates only the first"),
            # fulltext ORed with other fields, no longer quietly AND
            (f"{primary} OR {mcp_url}", primary_ids | mcp_url_ids, "kw OR url is a union"),
            (f"{mcp_url} OR {primary}", primary_ids | mcp_url_ids, "url OR kw is a union"),
            (f"{primary} OR type: img", primary_ids | img_ids, "kw OR type is a union across fts columns"),
            # fulltext OR NOT, fts5 has no unary NOT
            (f"{primary} OR NOT {secondary}", primary_ids | (all_ids - secondary_ids), "kw OR NOT kw keeps the NOT"),
            (f"NOT {primary} OR {secondary}", (all_ids - primary_ids) | secondary_ids, "NOT kw OR kw keeps the NOT"),
            # standard precedence across fields
            (f"type: html AND {primary} OR {secondary}", (html_ids & primary_ids) | secondary_ids, "A AND B OR C is (A AND B) OR C"),
            (f"{secondary} OR {primary} AND type: html", secondary_ids | (primary_ids & html_ids), "C OR B AND A is C OR (B AND A)"),
            # binary NOT on groups, double negation, nesting
            (f"{primary} NOT ({secondary} OR appstat)", primary_ids - (secondary_ids | appstat_ids), "A NOT (B OR C) excludes the group"),
            (f"NOT (NOT {primary})", primary_ids, "NOT NOT A is A"),
            (f"type: html AND NOT ({primary} OR {mcp_url})", html_ids - (primary_ids | mcp_url_ids), "A AND NOT (kw OR url) excludes the mixed group"),
        ]
        for query, expected, message in cases:
            self.assertEqual(self.__get_search_ids(crawler, site_id, query), expected, f"{message}: {query}")

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

        # this test inadvertently also covers t_URL_FIELD parser testing
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


class IndexedConcurrencyTests(unittest.TestCase):
    """
    Tool calls run off the event loop, and index builds are claimed once. A build
    is held open by a gate on _load_site_data, so each state is observed on purpose,
    not by timing luck. The gate releases itself after a few seconds, a regression
    to blocking calls fails the assertions rather than hanging the suite.
    """

    GATE_TIMEOUT_SECONDS: Final[float] = 5.0

    class BuildGate:
        """
        Stands in for a slow index build. Counts builds, announces the start of each,
        and holds until released.
        """
        def __init__(self, load_site_data):
            self.started: threading.Event = threading.Event()
            self.release: threading.Event = threading.Event()
            self.builds: int = 0
            self.__load_site_data = load_site_data

        def load_site_data(self, *args, **kwargs):
            self.builds += 1
            self.started.set()
            self.release.wait(timeout=IndexedConcurrencyTests.GATE_TIMEOUT_SECONDS)
            return self.__load_site_data(*args, **kwargs)

    def setUp(self):
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        self.__temp_directory = tempfile.TemporaryDirectory()
        # cleanups run LIFO after tearDown, anything a test registers (joining its
        # threads) runs before the directory goes, even when an assertion fails
        self.addCleanup(self.__temp_directory.cleanup)
        datasrc: Path = Path(self.__temp_directory.name)
        # unique site per test, the wget manager and its index cache are module globals
        site_name: str = f"{uuid.uuid4().hex}.example"
        site_directory: Path = datasrc / site_name
        site_directory.mkdir()
        (site_directory / "index.html").write_text("<html><body>concurrency home</body></html>", encoding="utf-8")
        (site_directory / "about.html").write_text("<html><body>concurrency about</body></html>", encoding="utf-8")
        self.site_id: int = WgetManager.string_to_id(site_name)
        self.site_directory: Path = site_directory
        self.crawler: WgetCrawler = WgetCrawler(datasrc)
        self.gate = IndexedConcurrencyTests.BuildGate(wget_manager._load_site_data)
        self.__load_patch = patch.object(wget_manager, "_load_site_data", self.gate.load_site_data)
        self.__load_patch.start()

    def tearDown(self):
        self.gate.release.set()
        self.__load_patch.stop()

    def __call(self) -> dict:
        """
        One search tool call through the MCP handler, response JSON parsed.
        """
        return asyncio.run(self.__call_async())

    async def __call_async(self) -> dict:
        response = await self.crawler.mcp_call_tool(RESOURCES_TOOL_NAME, {"sites": [self.site_id]})
        return json.loads(response[0].text)

    def __await_complete(self) -> dict:
        """
        Poll until the (released) build has cached, a cancelled call's thread runs on
        without anyone waiting on it.
        """
        timeout: float = time.monotonic() + self.GATE_TIMEOUT_SECONDS * 2
        while time.monotonic() < timeout:
            response: dict = self.__call()
            if response["__meta__"]["index"]["status"] == "complete":
                return response
            time.sleep(0.05)
        self.fail("index build never completed")

    def test_tool_call_off_event_loop(self):
        """
        While one call is held mid-build, the event loop stays free: a second call for
        the same index answers at once, reporting the build in progress (not an empty
        result passed off as no matches), and the first completes on release.
        """
        async def scenario() -> tuple[dict, dict, bool]:
            building_call = asyncio.create_task(self.__call_async())
            started: bool = await asyncio.to_thread(self.gate.started.wait, self.GATE_TIMEOUT_SECONDS)
            self.assertTrue(started, "build never started")

            concurrent: dict = await asyncio.wait_for(self.__call_async(), timeout=self.GATE_TIMEOUT_SECONDS)
            building_done_early: bool = building_call.done()
            self.gate.release.set()
            building: dict = await asyncio.wait_for(building_call, timeout=self.GATE_TIMEOUT_SECONDS * 2)
            return concurrent, building, building_done_early

        concurrent, building, building_done_early = asyncio.run(scenario())

        self.assertFalse(building_done_early, "first call finished before release, the loop was blocked")
        self.assertEqual(concurrent["__meta__"]["index"]["status"], "indexing")
        self.assertEqual(concurrent["results"], [])
        self.assertTrue(any("index is building" in error for error in concurrent["__meta__"].get("errors", [])),
                "a concurrent call must say the index is building")

        self.assertEqual(building["__meta__"]["index"]["status"], "complete")
        self.assertEqual(len(building["results"]), 2)
        self.assertNotIn("errors", building["__meta__"])
        self.assertEqual(self.gate.builds, 1, "index built more than once")

    def test_cancelled_call_returns_and_build_caches(self):
        """
        A cancelled call returns immediately, mid-build. The abandoned build runs on
        and caches, the next call gets results without building again.
        """
        async def scenario() -> float:
            building_call = asyncio.create_task(self.__call_async())
            started: bool = await asyncio.to_thread(self.gate.started.wait, self.GATE_TIMEOUT_SECONDS)
            self.assertTrue(started, "build never started")
            cancelled_at: float = time.monotonic()
            building_call.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(building_call, timeout=self.GATE_TIMEOUT_SECONDS * 2)
            return time.monotonic() - cancelled_at

        cancel_seconds: float = asyncio.run(scenario())
        self.assertLess(cancel_seconds, 1.0, "cancellation waited on the build")
        self.assertFalse(self.gate.release.is_set())

        self.gate.release.set()
        completed: dict = self.__await_complete()
        self.assertEqual(len(completed["results"]), 2)
        self.assertEqual(self.gate.builds, 1, "cancelled build did not cache, index built again")

    def test_concurrent_builds_claim_once(self):
        """
        Many threads asking for one index at the same moment: one builds, the rest
        are told it is building. The claim is atomic, not check-then-set.
        """
        thread_count: int = 8
        barrier: threading.Barrier = threading.Barrier(thread_count)
        statuses: list[str] = []
        statuses_lock: threading.Lock = threading.Lock()

        def search() -> None:
            barrier.wait()
            api: BaseJsonApi = self.crawler.get_resources_api(sites=[self.site_id])
            with statuses_lock:
                statuses.append(api.meta_index["status"])

        threads: list[threading.Thread] = [threading.Thread(target=search) for _ in range(thread_count)]
        for thread in threads:
            thread.start()
        self.addCleanup(lambda: [thread.join(self.GATE_TIMEOUT_SECONDS * 2) for thread in threads])
        self.assertTrue(self.gate.started.wait(self.GATE_TIMEOUT_SECONDS), "build never started")
        # all but the builder return while the build is held
        timeout: float = time.monotonic() + self.GATE_TIMEOUT_SECONDS
        while len(statuses) < thread_count - 1 and time.monotonic() < timeout:
            time.sleep(0.01)
        self.assertEqual(sorted(statuses), ["indexing"] * (thread_count - 1))

        self.gate.release.set()
        for thread in threads:
            thread.join(self.GATE_TIMEOUT_SECONDS * 2)
        self.assertEqual(statuses.count("complete"), 1)
        self.assertEqual(self.gate.builds, 1, "index built more than once")

    def test_stats_fifo_cap(self):
        """
        Stats keep the most recent INDEXED_MANAGER_STATS_MAX entries, oldest out first.
        """
        self.gate.release.set()
        manager: WgetManager = WgetManager()
        group: SitesGroup = SitesGroup(self.crawler.datasrc, [self.site_id], [self.site_directory])
        for _ in range(INDEXED_MANAGER_STATS_MAX + 50):
            manager.get_connection(group)

        stats: list[SitesStat] = manager.get_stats()
        self.assertEqual(len(stats), INDEXED_MANAGER_STATS_MAX)
        # the first entry, the uncached build, is the one evicted
        self.assertTrue(all(stat.cached for stat in stats), "oldest entry should be evicted first")
        self.assertTrue(all(earlier.timestamp <= later.timestamp for earlier, later in zip(stats, stats[1:])))
