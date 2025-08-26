import re
import unittest
import difflib

from urllib.request import urlopen
from mcp_server_webcrawl.utils.logger import get_logger
from mcp_server_webcrawl.extras.markdown import get_markdown

logger = get_logger()

try:
    # optional dependency only used in testing
    from html2text import html2text
except ImportError:
    logger.error(f"html2text is required to run tests")
    pass

class TemplateTests(unittest.TestCase):
    """
    Test suite for the custom HTML to markdown converter.
    Why custom? It's a bit faster, that is the only reason.
    Maximum load is 100 transforms (1 per result for a max result 
    of 100), so speed matters. A default set is 20.
    This converter does a few things differently to tailor to LLM
    interaction.
    * aggressively removes images (html2text selectively renders)
    * links with block decendents will render like a <p> 
        (html2text treats as <a><br>)
    * this may be a rabbit hole trying to compare anything with 
        practical pass/fail when it's never going equivalent. 
        TODO: look for fuzzy solution, or hyper customize comparisons
        for a handful of webpages.
    """

    def setUp(self):
        """
        Set up the test environment with fixture data.
        """
        super().setUp()

    def normalize_text(self, text):
        """
        Normalize text for loose comparison - ignore whitespace differences.
        """
        if text is None:
            return ""

        lines = [line.strip() for line in text.splitlines()]
        normalized = '\n'.join(lines)
        normalized = re.sub(r'[ \t]+', ' ', normalized)
        normalized = re.sub(r'\n{4,}', '\n\n\n', normalized)
        normalized = re.sub(r'(?<![.!?:])\n(?=[a-zA-Z])', ' ', normalized)
        return normalized.strip()

    def compare_transforms(self, url) -> bool:
        """
        Compare markdown converters
        """

        response = urlopen(url, timeout=10)
        if response.status != 200:
            return False

        html = response.read().decode("utf-8")
        result1 = get_markdown(html) or None
        result2 = html2text(html) or None
        if result1 is None or result2 is None:
            return False

        normalized1 = self.normalize_text(result1)
        normalized2 = self.normalize_text(result2)

        if normalized1 != normalized2:
            diff = difflib.unified_diff(
                normalized2.splitlines(keepends=True),  # html2text as baselineif content is None or content
                normalized1.splitlines(keepends=True),  # custom transform
                fromfile='html2text (normalized)',
                tofile='transform_to_markdown (normalized)',
                lineterm=''
            )

            diff_output = ''.join(diff)
            logger.warning(f"Semantic differences found for {url}\n\n{diff_output}")
            return False

        return True

    def test_example_com(self):
        result: bool = self.compare_transforms("https://example.com")
        self.assertTrue(result, "example.com should contain functionally equivalent HTML to text (simple).")
