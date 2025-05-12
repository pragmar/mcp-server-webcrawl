from enum import Enum
from typing import Final
from datetime import datetime

from mcp_server_webcrawl.models import METADATA_VALUE_TYPE
from mcp_server_webcrawl.utils import isoformat_zulu

RESOURCES_TOOL_NAME: str = "webcrawl_search"
RESOURCES_LIMIT_DEFAULT: int = 20
RESOURCES_LIMIT_MAX: int = 100

RESOURCES_FIELDS_REQUIRED: Final[list[str]] = ["id", "url", "site", "type", "status"]
RESOURCES_FIELDS_DEFAULT: Final[list[str]] = RESOURCES_FIELDS_REQUIRED + ["created", "modified"]
RESOURCES_SORT_OPTIONS_DEFAULT: Final[list[str]] = ["+id", "-id", "+url", "-url", "+status", "-status", "?"]

RESOURCES_DEFAULT_FIELD_MAPPING: Final[dict[str, str]] = {
    "id": "Id",
    "site": "Project",
    "url": "Url",
    "name": "Name",
    "status": "Status",
    "size": "Size",
    "type": "Type",
    "headers": "Headers",
    "content": "Content",
    "time": "Time"
}

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
        site: int | None = None,
        crawl: int | None = None,
        type: ResourceResultType = ResourceResultType.UNDEFINED,
        name: str | None = None,
        headers: str | None = None,
        content: str | None = None,
        created: datetime | None = None,
        modified: datetime | None = None,
        status: int | None = None,
        size: int | None = None,
        time: int | None = None,
        metadata: dict[str, METADATA_VALUE_TYPE] | None = None,
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
            "created": isoformat_zulu(self.created) if self.created else None,
            "modified": isoformat_zulu(self.modified) if self.modified else None,
            "status": self.status,
            "size": self.size,
            "time": self.time,
            "metadata": self.metadata  # reserved
        }

        return {k: v for k, v in result.items() if v is not None and not (k == "metadata" and v == {})}

    def to_forcefield_dict(self, forcefields=None) -> dict[str, METADATA_VALUE_TYPE]:
        """
        Create a dictionary with forced fields set to None if not present in the object.

        Args:
            forcefields: List of field names that should be included in the result
                        even if they're not present in the object data

        Returns:
            Dictionary containing object data with forced fields included
        """
        result = {}
        if forcefields:
            result = {k: None for k in forcefields}
        result.update(self.to_dict())
        return result
