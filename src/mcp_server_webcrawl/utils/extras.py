import re
import html2text
from html.parser import HTMLParser
from logging import Logger
from typing import Final

from mcp_server_webcrawl.models.resources import RESOURCES_DEFAULT_FIELD_MAPPING
from mcp_server_webcrawl.settings import DEBUG, DATA_DIRECTORY
from mcp_server_webcrawl.utils.logger import get_logger
from mcp_server_webcrawl.utils.search import SearchQueryParser

logger: Logger = get_logger()

MAX_SNIPPETS_MATCHED_COUNT: Final[int] = 15
MAX_SNIPPETS_RETURNED_COUNT: Final[int] = 3
MAX_SNIPPETS_CONTEXT_SIZE: Final[int] = 48

__markdown_transformer = html2text.HTML2Text()
__markdown_transformer.ignore_links = False
__markdown_transformer.ignore_images = True
__markdown_transformer.ignore_tables = False
__markdown_transformer.body_width = 0
__html_re: re.Pattern = re.compile(r"<[a-zA-Z]+[^>]*>")

class HTMLContentExtractor(HTMLParser):
    """
    Custom HTML parser to extract different types of content from HTML.
    """

    __RE_SPLIT = re.compile(r"[\s\-_]+")
    __RE_WHITESPACE = re.compile(r"\s+")

    def __init__(self):
        super().__init__()
        self.__text_content = []
        self.__html_markup = []
        self.__html_attributes = []
        self.__html_comments = []
        self.__text_accumulator = []

    def __flush_text(self) -> str:
        """
        Accumulate and flush the current text buffer.
        """
        if self.__text_accumulator:
            text = " ".join(self.__text_accumulator)
            self.__text_content.append(text)
            self.__text_accumulator.clear()
            return text
        return ""

    def __normalize_whitespace(self, text: str) -> str:
        """
        Normalize whitespace using pre-compiled pattern.
        """
        return self.__RE_WHITESPACE.sub(" ", text).strip()

    def handle_starttag(self, tag, attrs):
        self.__html_markup.append(tag)
        self.__flush_text()

        for attribute_name, attribute_value in attrs:
            self.__html_markup.append(attribute_name)
            if attribute_value:
                # Use pre-compiled pattern and filter empties in one pass
                values = [v for v in self.__RE_SPLIT.split(attribute_value) if v]
                self.__html_attributes.extend(values)

    def handle_endtag(self, tag):
        self.__flush_text()

    def handle_data(self, data):
        cleaned: str = data.strip()
        if cleaned:
            self.__text_accumulator.append(cleaned)

    def handle_comment(self, data):
        cleaned = data.strip()
        if cleaned:
            self.__html_comments.append(cleaned)

    def close(self):
        self.__flush_text()
        super().close()

    def get_text_content(self) -> str:
        """
        Get all text content joined and normalized.
        """
        joined: str = " ".join(self.__text_content)
        return self.__normalize_whitespace(joined)

    def get_markup_content(self) -> str:
        """
        Get all HTML markup (tags and attribute names) joined and normalized.
        """
        joined: str = " ".join(self.__html_markup)
        return self.__normalize_whitespace(joined)

    def get_attributes_content(self) -> str:
        """
        Get all attribute values joined and normalized.
        """
        joined: str = " ".join(self.__html_attributes)
        return self.__normalize_whitespace(joined)

    def get_comments_content(self) -> str:
        """
        Get all HTML comments joined and normalized.
        """
        joined: str = " ".join(self.__html_comments)
        return self.__normalize_whitespace(joined)

def get_markdown(content: str) -> str | None:
    if content is None or content == "":
        return None
    elif __html_re.search(content):
        return __markdown_transformer.handle(content)
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
    pattern = rf"\b({'|'.join(escaped_terms)})\b"
    matches = list(re.finditer(pattern, text_lower))

    for match in matches:

        if len(snippets) >= max_snippets:
            break

        context_start = max(0, match.start() - MAX_SNIPPETS_CONTEXT_SIZE)
        context_end = min(len(text), match.end() + MAX_SNIPPETS_CONTEXT_SIZE)
        if context_start > 0:
            while context_start > 0 and text[context_start].isalnum():
                context_start -= 1
        if context_end < len(text):
            while context_end < len(text) and text[context_end].isalnum():
                context_end += 1

        snippet = text[context_start:context_end].strip()
        snippet = re.sub(r"^[^\w\[]+", "", snippet)
        snippet = re.sub(r"[^\w\]]+$", "", snippet)
        highlighted_snippet = snippet

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

    search_terms_parser = HTMLContentExtractor()
    try:
        search_terms_parser.feed(content)
        search_terms_parser.close()
        search_groups["text"] = search_terms_parser.get_text_content()
        search_groups["html_attributes"] = search_terms_parser.get_attributes_content()
        search_groups["html_comments"] = search_terms_parser.get_comments_content()
        search_groups["html_markup"] = search_terms_parser.get_markup_content()
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
