import re
import lxml.html

from lxml import etree
from lxml.etree import ParserError, XPathEvalError, XPathSyntaxError
from logging import Logger
from typing import Final

from mcp_server_webcrawl.utils.logger import get_logger
from mcp_server_webcrawl.utils.search import SearchQueryParser
from mcp_server_webcrawl.utils.xslt import transform_to_markdown

MAX_SNIPPETS_MATCHED_COUNT: Final[int] = 15
MAX_SNIPPETS_RETURNED_COUNT: Final[int] = 3
MAX_SNIPPETS_CONTEXT_SIZE: Final[int] = 48

__RE_HTML: Final[re.Pattern] = re.compile(r"<[a-zA-Z]+[^>]*>")
__RE_SNIPPET_START_TRIM: Final[re.Pattern] = re.compile(r"^[^\w\[]+")
__RE_SNIPPET_END_TRIM: Final[re.Pattern] = re.compile(r"[^\w\]]+$")

logger: Logger = get_logger()

class HTMLContentExtractor:
    """
    lxml-based HTML parser for extracting different types of content from HTML.
    Content separates into components: text, markup, attributes (values), and comments.
    These can be prioritized in search so that text is the displayed hit over noisier
    types.
    """

    _RE_SPLIT: re.Pattern = re.compile(r"[\s\-_]+")
    _RE_WHITESPACE: re.Pattern = re.compile(r"\s+")

    def __init__(self, content: str):
        self.__document: lxml.html.HtmlElement | None = None
        self.content: str = content
        self.document_text: str = ""
        self.document_markup: str = ""
        self.document_attributes: str = ""
        self.document_comments: str = ""

        load_success: bool = self.__load_content()
        if load_success == True:
            _ = self.__extract()
        else:
            self.document_text = self.__normalize_whitespace(self.content)

    def __load_content(self) -> bool:
        """
        Load content string into lxml doc.
        """

        if not self.content or not self.content.strip():
            return False

        try:
            self.__document = lxml.html.fromstring(self.content.encode("utf-8"))
            return True
        except (ParserError, ValueError, UnicodeDecodeError):
            try:
                wrapped_content = f"<html><body>{self.content}</body></html>"
                self.__document = lxml.html.fromstring(wrapped_content.encode("utf-8"))
                return True
            except (ParserError, ValueError, UnicodeDecodeError):
                return False

    def __extract(self) -> bool:
        """
        Extract content from lxml doc.
        """

        if self.__document is None:
            return False

        text_values = []
        markup_values = []
        attribute_values = []
        element: lxml.html.HtmlElement | None = None
        for element in self.__document.iter():

            if element.tag:
                markup_values.append(element.tag)
                if element.tag in ("script", "style"):
                    continue

            if element.text:
                text_values.append(element.text.strip())

            if element.tail:
                text_values.append(element.tail.strip())

            for attr_name, attr_value in element.attrib.items():
                markup_values.append(attr_name)
                if attr_value:
                    values = [v for v in self._RE_SPLIT.split(attr_value) if v]
                    attribute_values.extend(values)

        self.document_text = self.__normalize_values(text_values)
        self.document_markup = self.__normalize_values(markup_values)
        self.document_attributes = self.__normalize_values(attribute_values)

        comment_values = []
        comment_nodes = self.__document.xpath("//comment()")
        for comment in comment_nodes:
            if comment.strip():
                comment_values.append(comment.strip())
        self.document_comments = self.__normalize_values(comment_values)

        return True

    def __normalize_values(self, values: list[str]) -> str:
        """
        Concatenate values and normalize whitespace for list of values.
        """
        text = " ".join([value for value in values if value])
        return self.__normalize_whitespace(text)

    def __normalize_whitespace(self, text: str) -> str:
        """
        Normalize whitespace using pre-compiled pattern.
        """
        return self._RE_WHITESPACE.sub(" ", text).strip()


def get_markdown(content: str) -> str | None:
    if content is None or content == "":
        return None
    elif __RE_HTML.search(content):
        return transform_to_markdown(content)
    else:
        return None

def find_matches_in_text(
        text: str,
        terms: list[str],
        max_snippets: int = MAX_SNIPPETS_MATCHED_COUNT,
        group_name: str = "") -> list[str]:

    if not text or not terms:
        return []

    snippets: list[str] = []
    seen_snippets: set[str] = set()
    text_lower: str = text.lower()

    highlight_patterns: list[re.Pattern] = [(re.compile(rf"\b({re.escape(term)})\b",
            re.IGNORECASE), term) for term in terms]
    escaped_terms = [re.escape(term) for term in terms]
    pattern: str = rf"\b({'|'.join(escaped_terms)})\b"
    matches = list(re.finditer(pattern, text_lower))

    for match in matches:

        if len(snippets) >= max_snippets:
            break

        context_start: int = max(0, match.start() - MAX_SNIPPETS_CONTEXT_SIZE)
        context_end: int = min(len(text), match.end() + MAX_SNIPPETS_CONTEXT_SIZE)
        if context_start > 0:
            while context_start > 0 and text[context_start].isalnum():
                context_start -= 1
        if context_end < len(text):
            while context_end < len(text) and text[context_end].isalnum():
                context_end += 1

        snippet: str = text[context_start:context_end].strip()
        snippet = __RE_SNIPPET_START_TRIM.sub("", snippet)
        snippet = __RE_SNIPPET_END_TRIM.sub("", snippet)
        highlighted_snippet: str = snippet

        for pattern, _ in highlight_patterns:
            highlighted_snippet = pattern.sub(r"**\1**", highlighted_snippet)

        if highlighted_snippet and highlighted_snippet not in seen_snippets:
            seen_snippets.add(highlighted_snippet)
            snippets.append(highlighted_snippet)

    return snippets


def get_snippets(headers: str, content: str, query: str) -> str | None:
    """
    Takes a query and content, reduces the HTML to text content and extracts hits
    as excerpts of text.

    Arguments:
        headers: Header content to search
        content: The HTML or text content to search in
        query: The search query string

    Returns:
        A string of snippets with context around matched terms, separated by " ... "
    """
    if content in (None, "") or query in (None, ""):
        return None

    headers = headers or ""
    headers_one_liner = re.sub(r"\s+", " ", headers).strip()
    search_terms_parser = SearchQueryParser()
    search_terms: list[str] = search_terms_parser.get_fulltext_terms(query)

    if not search_terms:
        return None

    snippets = []

    search_groups: dict[str, str] = {
        "headers": headers_one_liner,
        "text": "",
        "html_attributes": "",
        "html_comments": "",
        "html_markup": "",
    }

    search_terms_parser = HTMLContentExtractor(content)
    try:
        search_groups["text"] = search_terms_parser.document_text
        search_groups["html_attributes"] = search_terms_parser.document_attributes
        search_groups["html_comments"] = search_terms_parser.document_comments
        search_groups["html_markup"] = search_terms_parser.document_markup
    except Exception as e:
        # fallback to plain text, if <=1MB
        if len(content) < 1024 * 1024:
            search_groups["text"] = content

    # priority order text, attributes, comments, headers, markup
    for group_name in ["text", "html_attributes", "html_comments", "headers", "html_markup"]:
        search_group_text = search_groups[group_name]
        if not search_group_text:
            continue
        group_snippets = find_matches_in_text(search_group_text, search_terms,
                max_snippets=MAX_SNIPPETS_MATCHED_COUNT+1, group_name=group_name)
        snippets.extend(group_snippets)
        if len(snippets) > MAX_SNIPPETS_MATCHED_COUNT:
            break

    if snippets:
        total_snippets = len(snippets)
        displayed_snippets = snippets[:MAX_SNIPPETS_RETURNED_COUNT]
        result = " ... ".join(displayed_snippets)

        if total_snippets > MAX_SNIPPETS_MATCHED_COUNT:
            result += f" ... + >{MAX_SNIPPETS_MATCHED_COUNT} more"
        elif total_snippets > MAX_SNIPPETS_RETURNED_COUNT:
            remaining = total_snippets - MAX_SNIPPETS_RETURNED_COUNT
            result += f" ... +{remaining} more"

        return result

    return None

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
            continue  # skip this xpath

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
