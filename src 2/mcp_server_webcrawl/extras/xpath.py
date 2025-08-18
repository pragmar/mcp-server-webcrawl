import lxml.html

from lxml import etree
from lxml.etree import ParserError, XPathEvalError, XPathSyntaxError
from logging import Logger

from mcp_server_webcrawl.utils.logger import get_logger

logger: Logger = get_logger()

def get_xpath(content: str, xpaths: list[str]) -> list[dict[str, str | int | float]]:
    """
    Takes content and gets xpath hits

    Arguments:
        content: The HTML source
        xpaths: The xpath selectors

    Returns:
        A list of dicts, with selector and value
    """

    if not isinstance(content, str):
        return []

    if not isinstance(xpaths, list) or not all(isinstance(item, str) for item in xpaths):
        raise ValueError("xpaths must be a list of strings")

    results = []

    if content == "":
        return results

    try:
        doc: lxml.html.HtmlElement = lxml.html.fromstring(content.encode("utf-8"))
    except ParserError:
        return results

    for xpath in xpaths:
        try:
            selector_result = doc.xpath(xpath)
        except (XPathEvalError, XPathSyntaxError) as ex:
            logger.warning(f"Invalid xpath '{xpath}': {ex}")
            continue

        if isinstance(selector_result, (list, tuple)):
            # normal xpath query returns a list
            for result in selector_result:
                # a new dict for each result
                xpath_hit: dict[str, str | int | float] = {"selector": xpath}
                if hasattr(result, "tag"):
                    html_string: str = etree.tostring(result, encoding="unicode", method="html")
                    xpath_hit["value"] = html_string.strip()
                else:
                    xpath_hit["value"] = str(result).strip()
                results.append(xpath_hit)
        else:
            # single value case (count(//h1), sum(), etc.) is also valid xpath
            xpath_hit: dict[str, str | int | float] = {"selector": xpath}
            if isinstance(selector_result, (int, float)):
                xpath_hit["value"] = selector_result
            else:
                xpath_hit["value"] = str(selector_result).strip()
            results.append(xpath_hit)

    return results