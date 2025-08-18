import re

from functools import lru_cache
from typing import Final
from logging import Logger

from mcp_server_webcrawl.utils.logger import get_logger

__REGEX_PATTERNS_REGEX_HAZARDS: Final[list[str]] = [
    r"\([^)]*\*[^)]*\+",                   # (.*)*+, (.+)*+, etc.
    r"\([^)]*\+[^)]*\*",                   # (.+)*., (.*)++, etc.
    r"\([^)]*\+[^)]*\+",                   # (.+)+, (.++)+ etc.
    r"\([^)]*\*[^)]*\*",                   # (.*)*, (.**) etc.
    r"\.\*.*\.\*",                         # .*.* patterns
    r"\.\+.*\.\+",                         # .+.+ patterns
    r"\([^)]*\?\)\*",                      # (a?)* patterns
    r"\([^)]*\?\)\+",                      # (a?)+ patterns
    r"\([^)]*[*+?][^)]*[*+?][^)]*\)[*+]",  # 2+ quantifiers inside, then quantifier outside
]

logger: Logger = get_logger()

@lru_cache(maxsize=None)
def __get_compiled_hazard_patterns():
    """
    Lazy load compiled patterns
    """
    compiled_patterns = []
    for hazard in __REGEX_PATTERNS_REGEX_HAZARDS:
        try:
            compiled_patterns.append(re.compile(hazard))
        except re.error as e:
            logger.warning(f"Invalid hazard pattern {hazard}: {e}")
            continue
    return compiled_patterns

def __regex_is_hazardous(pattern: str) -> bool:
    """
    Check if a regex pattern might cause catastrophic backtracking
    or otherwise unacceptable performance over up to 100 HTML files
    """

    compiled_hazards = __get_compiled_hazard_patterns()

    for hazard_pattern in compiled_hazards:
        try:
            if hazard_pattern.search(pattern):
                logger.error(f"hazardous regex discarded {pattern} matched {hazard_pattern.pattern}")
                return True
        except re.error as e:
            logger.warning(f"Error checking hazard pattern {hazard_pattern.pattern}: {e}")
            continue

    return False

def get_regex(headers: str, content: str, patterns: list[str]) -> list[dict[str, str | int]]:
    """
    Takes headers and content and gets regex matches

    Arguments:
        headers: The headers to search
        content: The content to search
        patterns: The regex patterns

    Returns:
        A list of dicts, with selector, value, groups, position info, and source
    """

    if not isinstance(content, str):
        content = ""
    if not isinstance(headers, str):
        headers = ""

    if not isinstance(patterns, list) or not all(isinstance(item, str) for item in patterns):
        raise ValueError("patterns must be a list of strings")

    results = []

    if content == "" and headers == "":
        return results

    re_patterns = []
    for pattern in patterns:
        if __regex_is_hazardous(pattern):
            logger.warning(f"Hazardous regex pattern '{pattern}'")
            continue

        try:
            re_pattern = re.compile(pattern)
            re_patterns.append(re_pattern)
        except re.error as ex:
            logger.warning(f"Invalid regex pattern '{pattern}': {ex}")
            continue

    # search headers and content
    search_targets = [("headers", headers), ("content", content)]

    for re_pattern in re_patterns:
        for source_name, search_text in search_targets:
            if not search_text:
                continue

            for match in re_pattern.finditer(search_text):
                regex_hit: dict[str, str | int] = {
                    "selector": re_pattern.pattern,
                    "value": match.group(0),
                    "source": source_name  # headers or content
                }

                if match.groups():
                    for i, group in enumerate(match.groups(), 1):
                        if group is not None:
                            regex_hit[f"group_{i}"] = group

                regex_hit["start"] = match.start()
                regex_hit["end"] = match.end()
                results.append(regex_hit)

    return results