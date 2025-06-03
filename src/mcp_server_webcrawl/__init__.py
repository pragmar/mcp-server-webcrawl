import os
import sys
import asyncio
import tracemalloc
import unittest
import logging

from pathlib import Path
from argparse import ArgumentParser

from mcp_server_webcrawl.utils.cli import get_help_short_message, get_help_long_message
from mcp_server_webcrawl.settings import DEBUG, DATA_DIRECTORY

VALID_CRAWLER_CHOICES: list[str] = ["wget",  "warc", "interrobot", "katana", "siteone"]

__version__: str = "0.10.4"
__name__: str = "mcp-server-webcrawl"

if DEBUG:
    tracemalloc.start()

class CustomHelpArgumentParser(ArgumentParser):
    def print_help(self, file=None):
        print(get_help_long_message(__version__))

def main() -> None:
    """
    Main entry point for the package. mcp-server-webcrawl should be on path if pip installed
    """

    if len(sys.argv) == 1:
        # \n parser error follows short message
        sys.stderr.write(get_help_short_message(__version__) + "\n")

    parser: CustomHelpArgumentParser = CustomHelpArgumentParser(description="InterrBot MCP Server")
    parser.add_argument("-c", "--crawler", type=str, choices=VALID_CRAWLER_CHOICES,
            help="Specify which crawler to use (default: interrobot)")
    parser.add_argument("--run-tests", action="store_true", help="Run tests instead of server")
    parser.add_argument("-d", "--datasrc", type=str, help="Path to datasrc (required unless testing)")
    args = parser.parse_args()

    if args.run_tests:
        is_development: bool = Path(__file__).parent.parent.parent.name == "mcp-server-webcrawl"
        if not is_development:
            sys.stderr.write("you must have the full github repo, locally installed, to run tests. \n")
            sys.exit(1)
        else:
            # testing captures some cross-fixture file information, useful for debug
            # force=True gets this to write during tests (usually quieted during run)
            unittest_log: Path = DATA_DIRECTORY / "fixtures-report.log"
            logging.basicConfig(level=logging.INFO, filename=unittest_log, filemode='w', force=True)
            file_directory = os.path.dirname(os.path.abspath(__file__))
            sys.exit(unittest.main(module=None, argv=["", "discover", "-s", file_directory, "-p", "*test*.py"]))

    if not args.datasrc:
        parser.error("the -d/--datasrc argument is required when not in test mode")

    if not args.crawler or args.crawler.lower() not in VALID_CRAWLER_CHOICES:
        valid_crawlers = ", ".join(VALID_CRAWLER_CHOICES)
        parser.error(f"the -c/--crawler argument must be one of: {valid_crawlers}")

    # cli interaction prior to loading the server
    from mcp_server_webcrawl.main import main as mcp_main
    def get_crawler(crawler_name: str):
        """
        lazy load crawler, some classes have additional package dependencies
        """
        crawler_name = crawler_name.lower()
        if crawler_name == "interrobot":
            from mcp_server_webcrawl.crawlers.interrobot.crawler import InterroBotCrawler
            return InterroBotCrawler
        elif crawler_name == "warc":
            from mcp_server_webcrawl.crawlers.warc.crawler import WarcCrawler
            return WarcCrawler
        elif crawler_name == "wget":
            from mcp_server_webcrawl.crawlers.wget.crawler import WgetCrawler
            return WgetCrawler
        elif crawler_name == "katana":
            from mcp_server_webcrawl.crawlers.katana.crawler import KatanaCrawler
            return KatanaCrawler
        elif crawler_name == "siteone":
            from mcp_server_webcrawl.crawlers.siteone.crawler import SiteOneCrawler
            return SiteOneCrawler
        else:
            valid_choices = ", ".join(VALID_CRAWLER_CHOICES)
            raise ValueError(f"unsupported crawler '{crawler_name}' ({valid_choices})")

    crawler = get_crawler(args.crawler)
    asyncio.run(mcp_main(crawler, Path(args.datasrc)))

__all__ = ["main"]
