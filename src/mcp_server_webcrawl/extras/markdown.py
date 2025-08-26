import re
from importlib import resources
from typing import Final, Any
from lxml import etree, html
from lxml.etree import ParserError
from logging import Logger

from mcp_server_webcrawl.utils.logger import get_logger

__XSLT_RESULT_CLEANER: Final[re.Pattern] = re.compile(r"(?:\n\s*-\s*\n|\n\s*\n)+")
__RE_HTML: Final[re.Pattern] = re.compile(r"<[a-zA-Z]+[^>]*>")

logger: Logger = get_logger()

class MarkdownTransformer:
    """
    Memoizes the XSLT transformer
    """
    _xslt_transform = None

    @classmethod
    def get_xslt_transform(cls):
        """
        Get the HTML to text markdown XSLT transformer
        """
        if cls._xslt_transform is None:
            xslt_string: str = resources.read_text("mcp_server_webcrawl.templates", "markdown.xslt").encode("utf-8")
            xslt_doc = etree.fromstring(xslt_string)
            cls._xslt_transform = etree.XSLT(xslt_doc)
        return cls._xslt_transform

def get_markdown(content: str) -> str | None:
    """
    Transform HTML content to Markdown using XSLT.

    Args:
        content (str): The HTML content to transform.

    Returns:
        str | None: The transformed Markdown string, or None if the input is empty
            or if transformation fails (e.g., due to invalid HTML or XSLT errors).
    """

    transformer = MarkdownTransformer.get_xslt_transform()
    content:str = content or ""
    assert isinstance(content, str), "String (HTML) required for transformer"
    assert transformer is not None

    if content == "" or not __RE_HTML.search(content):
        return None

    try:
        doc = html.fromstring(content)
        result = str(transformer(doc))
        result = __XSLT_RESULT_CLEANER.sub("\n\n", result).strip()
        return result

    except Exception as ex:
        logger.warning(f"XSLT transform error: {type(ex).__name__}\n{ex}")
        return None
