import re
import curses

from dataclasses import dataclass
from typing import List

from mcp_server_webcrawl.interactive.ui import safe_addstr

REGEX_QUOTED_PHRASE = re.compile(r'"([^"]+)"')
REGEX_WORD = re.compile(r"\b\w+\b")
REGEX_SNIPPET_MARKER = re.compile(r"\*\*([a-zA-Z\-_' ]+)\*\*")
IGNORE_WORDS = {"AND", "OR", "NOT", "and", "or", "not", "type", "status", "size", "url", "id"}

@dataclass
class HighlightSpan:
    """
    Represents a highlight span in text
    """
    start: int
    end: int
    text: str

    def __str__(self) -> str:
        return f"[{self.start}:{self.end} '{self.text}']"


class HighlightProcessor:
    """
    Shared highlight processing utilities
    """

    @staticmethod
    def extract_search_terms(query: str) -> List[str]:
        """
        Extract search terms from query, handling quoted phrases and individual keywords.
        """
        if not query or not query.strip():
            return []

        search_terms = []
        for match in REGEX_QUOTED_PHRASE.finditer(query):
            phrase = match.group(1).strip()
            if phrase:
                search_terms.append(phrase)

        remaining_query = REGEX_QUOTED_PHRASE.sub('', query)

        # extract individual words
        for match in REGEX_WORD.finditer(remaining_query):
            word = match.group().strip()
            if word and word not in IGNORE_WORDS and len(word) > 2:
                search_terms.append(word)

        return search_terms

    @staticmethod
    def find_highlights_in_text(text: str, search_terms: List[str]) -> List[HighlightSpan]:
        """
        Find all highlight spans in text for the given search terms.
        """
        if not text or not search_terms:
            return []

        highlights = []
        escaped_terms = [re.escape(term.strip("\"'")) for term in search_terms]
        pattern = re.compile(rf"\b({'|'.join(escaped_terms)})\b", re.IGNORECASE)

        for match in pattern.finditer(text):
            span = HighlightSpan(
                start=match.start(),
                end=match.end(),
                text=match.group()
            )
            highlights.append(span)

        return HighlightProcessor.merge_overlapping_highlights(highlights, text)

    @staticmethod
    def extract_snippet_highlights(snippet_text: str) -> tuple[str, List[HighlightSpan]]:
        """
        Extract highlights from snippet text with **markers**, returning clean text and highlights.
        """

        if not snippet_text:
            return "", []

        normalized_text = re.sub(r"\s+", " ", snippet_text.strip())

        parts: List[str] = []
        highlights: List[HighlightSpan] = []
        clean_len = 0
        last_end = 0

        for match in REGEX_SNIPPET_MARKER.finditer(normalized_text):
            before = normalized_text[last_end:match.start()]
            parts.append(before)
            clean_len += len(before)

            highlight_text = match.group(1)
            highlights.append(HighlightSpan(
                start=clean_len,
                end=clean_len + len(highlight_text),
                text=highlight_text,
            ))
            parts.append(highlight_text)
            clean_len += len(highlight_text)
            last_end = match.end()

        parts.append(normalized_text[last_end:])
        return "".join(parts).strip(), highlights

    @staticmethod
    def merge_overlapping_highlights(highlights: List[HighlightSpan], text: str) -> List[HighlightSpan]:

        """
        Merge overlapping or adjacent highlight spans.
        """

        merged: List[HighlightSpan] = []

        for h in sorted(highlights, key=lambda h: h.start):
            if merged and h.start <= merged[-1].end:
                last = merged[-1]
                end = max(last.end, h.end)
                merged[-1] = HighlightSpan(start=last.start, end=end, text=text[last.start:end])
            else:
                merged.append(h)

        return merged

    @staticmethod
    def render_text_with_highlights(
        stdscr: curses.window,
        text: str,
        highlights: List[HighlightSpan],
        x: int,
        y: int,
        max_width: int,
        normal_style: int,
        hit_style: int,
    ) -> None:
        """Render text with highlights applied."""
        if not text.strip():
            return

        display_text = text[:max_width]
        current_x = x
        pos = 0

        def emit(segment: str, style: int) -> None:
            nonlocal current_x
            segment = segment[: x + max_width - current_x]
            if segment:
                safe_addstr(stdscr, y, current_x, segment, style)
                current_x += len(segment)

        try:
            for h in highlights:
                if h.start >= len(display_text):
                    continue
                emit(display_text[pos:h.start], normal_style)
                end = min(h.end, len(display_text))
                emit(display_text[h.start:end], hit_style)
                pos = max(pos, end)

            emit(display_text[pos:], normal_style)
        except curses.error:
            pass
