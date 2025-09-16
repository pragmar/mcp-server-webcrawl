import re
import curses

from dataclasses import dataclass
from typing import List

from mcp_server_webcrawl.interactive.ui import safe_addstr

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

    QUOTED_PHRASE_PATTERN = re.compile(r'"([^"]+)"')
    WORD_PATTERN = re.compile(r'\b\w+\b')
    SNIPPET_MARKER_PATTERN = re.compile(r'\*\*([a-zA-Z\-_]+)\*\*')
    IGNORE_WORDS = {'AND', 'OR', 'NOT', 'and', 'or', 'not', 'type', 'status', 'size', 'url', 'id'}

    @staticmethod
    def extract_search_terms(query: str) -> List[str]:
        """
        Extract search terms from query, handling quoted phrases and individual keywords.
        """
        if not query or not query.strip():
            return []

        search_terms = []
        for match in HighlightProcessor.QUOTED_PHRASE_PATTERN.finditer(query):
            phrase = match.group(1).strip()
            if phrase:
                search_terms.append(phrase)

        remaining_query = HighlightProcessor.QUOTED_PHRASE_PATTERN.sub('', query)

        # extract individual words
        for match in HighlightProcessor.WORD_PATTERN.finditer(remaining_query):
            word = match.group().strip()
            if word and word not in HighlightProcessor.IGNORE_WORDS and len(word) > 2:
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
        escaped_terms = [re.escape(term) for term in search_terms]
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

        clean_text = ""
        highlights = []
        last_end = 0

        for match in HighlightProcessor.SNIPPET_MARKER_PATTERN.finditer(normalized_text):
            # text before this match
            clean_text += normalized_text[last_end:match.start()]

            # highlighted text (without markers)
            highlight_text = match.group(1)
            highlight_start = len(clean_text)
            clean_text += highlight_text
            highlight_end = len(clean_text)

            span: HighlightSpan = HighlightSpan(
                start=highlight_start,
                end=highlight_end,
                text=highlight_text
            )
            highlights.append(span)
            last_end = match.end()

        # remaining text
        clean_text += normalized_text[last_end:]

        return clean_text.strip(), highlights

    @staticmethod
    def merge_overlapping_highlights(highlights: List[HighlightSpan], text: str) -> List[HighlightSpan]:
        """Merge overlapping or adjacent highlight spans."""
        if not highlights:
            return []

        # sort by start position
        sorted_highlights = sorted(highlights, key=lambda h: h.start)
        merged = []

        for highlight in sorted_highlights:
            if not merged:
                merged.append(highlight)
            else:
                last = merged[-1]
                if highlight.start <= last.end:
                    # overlapping/adjacent - merge them
                    end = max(last.end, highlight.end)
                    merged_text = text[last.start:end]
                    merged[-1] = HighlightSpan(
                        start=last.start,
                        end=end,
                        text=merged_text
                    )
                else:
                    merged.append(highlight)

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
        hit_style: int
    ) -> None:
        """
        Render text with highlights applied.
        """
        if not text.strip():
            return

        display_text: str = text[:max_width] if len(text) > max_width else text
        visible_highlights: list[str] = [h for h in highlights if h.start < len(display_text)]
        current_x: int = x
        pos: int = 0

        try:
            for highlight in visible_highlights:
                # text before highlight
                if highlight.start > pos:
                    text_before: str = display_text[pos:highlight.start]
                    safe_addstr(stdscr, y, current_x, text_before, normal_style)
                    current_x += len(text_before)
                    pos = highlight.start

                # highlighted text
                highlight_end: int = min(highlight.end, len(display_text))
                highlighted_text: str = display_text[highlight.start:highlight_end]
                if current_x + len(highlighted_text) <= x + max_width:
                    safe_addstr(stdscr, y, current_x, highlighted_text, hit_style)
                    current_x += len(highlighted_text)
                pos = highlight_end

            # remaining text
            if pos < len(display_text):
                remaining_text: str = display_text[pos:]
                remaining_width: int = max_width - (current_x - x)
                if remaining_width > 0:
                    safe_addstr(stdscr, y, current_x, remaining_text[:remaining_width], normal_style)

        except curses.error:
            pass
