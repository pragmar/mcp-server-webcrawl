import os
import sys
import asyncio
import tracemalloc
import unittest

from collections import OrderedDict
from pathlib import Path
from argparse import ArgumentParser


from mcp_server_webcrawl.utils.cli import get_help_short_message, get_help_long_message
from mcp_server_webcrawl.settings import DEBUG

__version__: str = "0.7.8"
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
    parser.add_argument("-c", "--crawler", type=str, choices=["wget",  "warc", "interrobot", "katana", "siteone"],
            help="Specify which crawler to use (default: interrobot)")
    parser.add_argument("--run-tests", action="store_true", help="Run tests instead of server")
    parser.add_argument("-d", "--datasrc", type=str, help="Path to datasrc (required unless testing)")
    args = parser.parse_args()

    if args.run_tests:
        is_development: bool = Path(__file__).parent.parent.parent.name == "mcp_server_webcrawl"
        if not is_development:
            sys.stderr.write("Unable to run tests, fixtures development directory not found.\n")
            sys.exit(1)
        else:
            file_directory = os.path.dirname(os.path.abspath(__file__))
            sys.exit(unittest.main(module=None, argv=["", "discover", "-s", file_directory, "-p", "*test*.py"]))

    if not args.datasrc:
        parser.error("the -d/--datasrc argument is required when not in test mode")

    # speed up help and mcp-server-webcrawl w/ no args, delay imports
    from mcp_server_webcrawl.main import main as mcp_main
    from mcp_server_webcrawl.crawlers.interrobot.crawler import InterroBotCrawler
    from mcp_server_webcrawl.crawlers.warc.crawler import WarcCrawler
    from mcp_server_webcrawl.crawlers.wget.crawler import WgetCrawler
    from mcp_server_webcrawl.crawlers.katana.crawler import KatanaCrawler
    from mcp_server_webcrawl.crawlers.siteone.crawler import SiteOneCrawler
    from mcp_server_webcrawl.crawlers.base.crawler import BaseCrawler

    crawler_map: OrderedDict[str, BaseCrawler] = OrderedDict([
        ("interrobot", InterroBotCrawler),
        ("warc", WarcCrawler),
        ("wget", WgetCrawler),
        ("katana", KatanaCrawler),
        ("siteone", SiteOneCrawler),
    ])

    if not args.crawler or args.crawler.lower() not in crawler_map.keys():
        valid_choices = ", ".join(crawler_map.keys())
        parser.error(f"the -c/--crawler argument must be one of: {valid_choices}")

    crawler: BaseCrawler = crawler_map[args.crawler.lower()]
    asyncio.run(mcp_main(crawler, Path(args.datasrc)))

__all__ = ["main"]
