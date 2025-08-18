
import re
import lxml.html

from lxml import etree
from lxml.etree import ParserError
from logging import Logger
from typing import Final

from mcp_server_webcrawl.utils.logger import get_logger
from mcp_server_webcrawl.utils.search import SearchQueryParser

MAX_SNIPPETS_MATCHED_COUNT: Final[int] = 15
MAX_SNIPPETS_RETURNED_COUNT: Final[int] = 3
MAX_SNIPPETS_CONTEXT_SIZE: Final[int] = 48

__RE_SNIPPET_START_TRIM: Final[re.Pattern] = re.compile(r"^[^\w\[]+")
__RE_SNIPPET_END_TRIM: Final[re.Pattern] = re.compile(r"[^\w\]]+$")

logger: Logger = get_logger()

class SnippetContentExtractor:
    """
    lxml-based HTML parser for extracting different types of content from HTML.
    Content separates into components: text, markup, attributes (values), and comments.
    These can be prioritized in search so that text is the displayed hit over noisier
    types.
    """
    PRIORITY_ORDER: list[str] = ["url", "document_text", "document_attributes",
        "document_comments", "headers", "document_markup"]

    __RE_SPLIT: re.Pattern = re.compile(r"[\s_]+|(?<!\w)-(?!\w)")
    __RE_WHITESPACE: re.Pattern = re.compile(r"\s+")
    __MAX_CONTENT_BYTES: int = 2 * 1024 * 1024 # 2MB

    def __init__(self, url: str, headers: str, content: str):

        self.__document: lxml.html.HtmlElement | None = None

        self.url: str = url
        self.content: str = ""
        # headers one liner to facilitate snippet
        self.headers: str = re.sub(r"\s+", " ", headers).strip()
        self.document_text: str = ""
        self.document_markup: str = ""
        self.document_attributes: str = ""
        self.document_comments: str = ""

        if len(content) > self.__MAX_CONTENT_BYTES:
            # ignore large files, slow
            return
        else:
            self.content = content

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
        comment_values = []

        element: lxml.html.HtmlElement | None = None
        for element in self.__document.iter():

            # HTML outliers
            if element.tag is etree.Comment or element.tag is etree.ProcessingInstruction:
                if element.text is not None:
                    comment_values.append(str(element.text.strip()))
                # avoid regular element text processing
                continue

            if element.tag is etree.Entity or element.tag is etree.CDATA:
                if element.text is not None:
                    text_values.append(str(element.text.strip()))
                continue

            # HTML tags and attributes
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
                    values = [v for v in self.__RE_SPLIT.split(attr_value) if v]
                    attribute_values.extend(values)

        self.document_text = self.__normalize_values(text_values)
        self.document_markup = self.__normalize_values(markup_values)
        self.document_attributes = self.__normalize_values(attribute_values)
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
        return self.__RE_WHITESPACE.sub(" ", text).strip()

def get_snippets(url: str, headers: str, content: str, query: str) -> str | None:
    """
    Takes a query and content, reduces the HTML to text content and extracts hits
    as excerpts of text.

    Arguments:
        headers: Header content to search
        content: The HTML or text content to search in
        query: The search query string

    Returns:
        A string of snippets with context around matched terms, separated by " ... " or None
    """
    if query in (None, ""):
        return None

    url = url or ""
    content = content or ""
    headers = headers or ""

    search_terms_parser = SearchQueryParser()
    search_terms: list[str] = search_terms_parser.get_fulltext_terms(query)

    if not search_terms:
        return None

    snippets = []
    search_terms_parser = SnippetContentExtractor(url, headers, content)

    # priority order url, text, attributes, comments, headers, markup
    # most interesting to least, as search hits
    for group_name in search_terms_parser.PRIORITY_ORDER:
        search_group_text = getattr(search_terms_parser, group_name)
        if not search_group_text:
            continue
        group_snippets = find_snippets_in_text(search_group_text, search_terms,
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

def find_snippets_in_text(
        text: str,
        terms: list[str],
        max_snippets: int = MAX_SNIPPETS_MATCHED_COUNT,
        group_name: str = "") -> list[str]:
    """
    Searches for whole-word matches of the given terms in the text and extracts
    surrounding context to create highlighted snippets. Each snippet shows the matched term
    in context with markdown-style bold highlighting (**term**).

    Args:
        text: The text to search within
        terms: List of search terms to find (case-insensitive, whole words only)
        max_snippets: Maximum number of snippets to return (default: MAX_SNIPPETS_MATCHED_COUNT)
        group_name: Regex group identifier (reserved for future use)

    Returns:
        List of unique snippet strings with matched terms highlighted using **bold** markdown.
        Each snippet includes surrounding context up to MAX_SNIPPETS_CONTEXT_SIZE characters
        on each side of the match. Returns empty list if no matches found or invalid input.
    """

    if not text or not terms:
        return []

    snippets: list[str] = []
    seen_snippets: set[str] = set()
    text_lower: str = text.lower()

    escaped_terms = [re.escape(term) for term in terms]
    pattern: str = rf"\b({'|'.join(escaped_terms)})\b"
    highlight_patterns: list[tuple[re.Pattern, str]] = [
        (re.compile(rf"\b({re.escape(term)})\b",
        re.IGNORECASE), term) for term in terms
    ]

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
