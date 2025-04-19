from enum import Enum
from typing import Final, Optional
from datetime import datetime

from mcp_server_webcrawl.models import METADATA_VALUE_TYPE

RESOURCES_TOOL_NAME: str = "webcrawl_search"
RESOURCES_LIMIT_DEFAULT: int = 20
RESOURCES_LIMIT_MAX: int = 100

RESOURCES_FIELDS_REQUIRED: Final[list[str]] = ["id", "url", "site", "type", "status"]
RESOURCES_FIELDS_DEFAULT: Final[list[str]] = RESOURCES_FIELDS_REQUIRED + ["created", "modified"]
RESOURCES_SORT_OPTIONS_DEFAULT: Final[list[str]] = ["+id", "-id", "+url", "-url", "+status", "-status", "?"]

class ResourceResultType(Enum):
    """
    Enum representing different types of web resources.
    """
    UNDEFINED = ""
    PAGE = "html"
    FRAME = "iframe"
    IMAGE = "img"
    AUDIO = "audio"
    VIDEO = "video"
    FONT = "font"
    CSS = "style"
    SCRIPT = "script"
    FEED = "rss"
    TEXT = "text"
    PDF = "pdf"
    DOC = "doc"
    OTHER = "other"

    @classmethod
    def values(cls):
        """
        Return all values of the enum as a list.
        """
        return [member.value for member in cls]


class ResourceResult:
    """
    Represents a web resource result from a crawl operation.
    """
    def __init__(
        self,
        id: int,
        url: str,
        site: Optional[int] = None,
        crawl: Optional[int] = None,
        type: ResourceResultType = ResourceResultType.UNDEFINED,
        name: Optional[str] = None,
        headers: Optional[str] = None,
        content: Optional[str] = None,
        created: Optional[datetime] = None,
        modified: Optional[datetime] = None,
        status: Optional[int] = None,
        size: Optional[int] = None,
        time: Optional[int] = None,
        metadata: Optional[dict[str, METADATA_VALUE_TYPE]] = None,
    ):
        """
        Initialize a ResourceResult instance.

        Args:
            id: Resource identifier
            url: Resource URL
            site: Site identifier the resource belongs to
            crawl: Crawl identifier the resource was found in
            type: Type of resource
            name: Resource name
            headers: HTTP headers
            content: Resource content
            created: Creation timestamp
            modified: Last modification timestamp
            status: HTTP status code
            size: Size in bytes
            time: Response time in milliseconds
            thumbnail: Base64 encoded thumbnail (experimental)
            metadata: Additional metadata for the resource
        """
        self.id = id
        self.url = url
        self.site = site
        self.crawl = crawl
        self.type = type
        self.name = name
        self.headers = headers
        self.content = content
        self.created = created
        self.modified = modified
        self.status = status
        self.size = size  # in bytes
        self.time = time  # in millis
        self.metadata = metadata  # reserved

    def to_dict(self) -> dict[str, METADATA_VALUE_TYPE]:
        """
        Convert the object to a dictionary suitable for JSON serialization.
        """
        # api_type = self.type.value if self.type else None
        result: dict[str, METADATA_VALUE_TYPE] = {
            "id": self.id,
            "url": self.url,
            "site": self.site,
            "crawl": self.crawl,
            "type": self.type.value if self.type else None,
            "name": self.name,
            "headers": self.headers,
            "content": self.content,
            "created": self.created.isoformat() if self.created else None,
            "modified": self.modified.isoformat() if self.modified else None,
            "status": self.status,
            "size": self.size,
            "time": self.time,
            "metadata": self.metadata  # reserved
        }

        return {k: v for k, v in result.items() if v is not None and not (k == "metadata" and v == {})}

    def to_forcefield_dict(self, forcefields=[]) -> dict[str, METADATA_VALUE_TYPE]:
        # None self annihilates in filter, forcefields can force their existence, as null
        result = {k: None for k in forcefields}
        result.update(self.to_dict())
        return result
