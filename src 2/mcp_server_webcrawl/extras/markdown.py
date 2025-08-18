import re

from typing import Final

from mcp_server_webcrawl.utils.xslt import transform_to_markdown

__RE_HTML: Final[re.Pattern] = re.compile(r"<[a-zA-Z]+[^>]*>")

def get_markdown(content: str) -> str | None:
    if content is None or content == "":
        return None
    elif __RE_HTML.search(content):
        return transform_to_markdown(content)
    else:
        return None