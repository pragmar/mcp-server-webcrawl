import re
import unittest

from importlib import resources
from urllib.request import urlopen
from mcp_server_webcrawl.utils.logger import get_logger
from mcp_server_webcrawl.extras.markdown import get_markdown

logger = get_logger()

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
    """

    def setUp(self):
        """
        Set up the test environment with fixture data.
        """
        super().setUp()

    def test_core_html(self):
        core_html: str = resources.read_text("mcp_server_webcrawl.templates", "tests_core.html")
        markdown = get_markdown(core_html)

        # h1-6
        self.assertIn("# Lorem Ipsum Dolor Sit Amet", markdown)
        self.assertIn("## Consectetur Adipiscing Elit", markdown)
        self.assertIn("### Nemo Enim Ipsam Voluptatem", markdown)
        self.assertIn("#### Sed Quia Non Numquam", markdown)
        self.assertIn("##### Nisi Ut Aliquid Ex Ea", markdown)
        self.assertIn("###### At Vero Eos Et Accusamus", markdown)

        # no content loss - key phrases should be preserved
        self.assertIn("Lorem ipsum dolor sit amet", markdown)
        self.assertIn("Definition List Example", markdown)
        self.assertIn("More Text Elements", markdown)

        # inline formatting (proper spacing)
        self.assertIn("amet, **consectetur adipiscing elit**. Sed", markdown)
        self.assertIn("laborum. **Sed ut perspiciatis** unde", markdown)
        self.assertIn("consequat. *Duis aute irure dolor* in", markdown)
        self.assertIn("laudantium. *Totam rem aperiam*, eaque", markdown)

        # link formatting (proper spacing)
        self.assertIn("veniam, quis nostrud exercitation ullamco", markdown)  # Fragment links as plain text
        self.assertIn("and a link back to top. Nam", markdown)

        # list formatting
        self.assertIn("* Similique sunt in culpa", markdown)
        self.assertIn("1. Temporibus autem quibusdam", markdown)

        # dl/dt
        self.assertIn("**Lorem Ipsum**", markdown)
        self.assertIn("    Dolor sit amet, consectetur adipiscing elit", markdown)
        self.assertIn("**Ut Enim**", markdown)
        self.assertIn("    Ad minim veniam, quis nostrud exercitation", markdown)
        self.assertIn("**Duis Aute**", markdown)
        self.assertIn("    Irure dolor in reprehenderit in voluptate", markdown)

        # table structure
        self.assertIn("| Lorem | Ipsum | Dolor | Sit |", markdown)
        self.assertIn("|---|---|---|---|", markdown)
        self.assertIn("| Consectetur | Adipiscing | Elit | Sed |", markdown)

        # code formatting
        self.assertIn("Here we have some `inline code` and", markdown)
        self.assertIn("```\nfunction lorem() {\n    return \"ipsum dolor sit amet\";\n}\n```", markdown)

        # blockquotes
        self.assertIn("> \"Sed ut perspiciatis unde omnis iste natus", markdown)

        # horizontal rule
        self.assertIn("---", markdown)

        # no double spacing for inline elements
        self.assertNotIn("**  ", markdown)  # No double spaces after bold
        self.assertNotIn("  **", markdown)  # No double spaces before bold
        self.assertNotIn("*  ", markdown)   # No double spaces after emphasis
        self.assertNotIn("  *", markdown)   # No double spaces before emphasis

        # structural integrity - count major elements
        heading_count = len(re.findall(r"^#{1,6} ", markdown, re.MULTILINE))
        self.assertEqual(heading_count, 11, "Should have exactly 6 headings")
        table_count = len(re.findall(r"^\|.*\|$", markdown, re.MULTILINE))
        self.assertGreater(table_count, 5, "Should have multiple table rows")

