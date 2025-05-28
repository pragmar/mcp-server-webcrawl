from enum import Enum
from typing import Final
from datetime import datetime

from mcp_server_webcrawl.models import METADATA_VALUE_TYPE
from mcp_server_webcrawl.utils import to_isoformat_zulu

RESOURCES_TOOL_NAME: Final[str] = "webcrawl_search"
RESOURCES_LIMIT_DEFAULT: Final[int] = 20
RESOURCES_LIMIT_MAX: Final[int] = 100
RESOURCE_EXTRAS_ALLOWED: Final[set[str]] = {"markdown", "snippets", "thumbnails"}
RESOURCES_FIELDS_REQUIRED: Final[list[str]] = ["id", "url", "site", "type", "status"]
RESOURCES_FIELDS_DEFAULT: Final[list[str]] = RESOURCES_FIELDS_REQUIRED + ["created", "modified"]
RESOURCES_SORT_OPTIONS_DEFAULT: Final[list[str]] = ["+id", "-id", "+url", "-url", "+status", "-status", "?"]
RESOURCES_DEFAULT_FIELD_MAPPING: Final[dict[str, str]] = {
    "id": "ResourcesFullText.Id",
    "site": "ResourcesFullText.Project",
    "created": "Resources.Created",
    "modified": "Resources.Modified",
    "url": "ResourcesFullText.Url",
    "status": "Resources.Status",
    "size": "Resources.Size",
    "type": "ResourcesFullText.Type",
    "headers": "ResourcesFullText.Headers",
    "content": "ResourcesFullText.Content",
    "time": "Resources.Time",
    "fulltext": "ResourcesFullText",
}
RESOURCES_DEFAULT_SORT_MAPPING: Final[dict[str, tuple[str, str]]] = {
    "+id": ("Resources.Id", "ASC"),
    "-id": ("Resources.Id", "DESC"),
    "+url": ("ResourcesFullText.Url", "ASC"),
    "-url": ("ResourcesFullText.Url", "DESC"),
    "+status": ("Resources.Status", "ASC"),
    "-status": ("Resources.Status", "DESC"),
    "?": ("Resources.Id", "RANDOM")
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
    def values(cls) -> list[str]:
        """
        Return all values of the enum as a list.
        """
        return [member.value for member in cls]

    @classmethod
    def to_int_map(cls):
        """
        Return a dictionary mapping each enum value to its integer position.

        Returns:
            dict: a dictionary with enum values as keys and their ordinal positions as values.
        """
        return {member.value: i for i, member in enumerate(cls)}

# if types stored as ints within db
RESOURCES_ENUMERATED_TYPE_MAPPING: Final[dict[int, ResourceResultType]] = {
    0: ResourceResultType.UNDEFINED,
    1: ResourceResultType.PAGE,
    2: ResourceResultType.OTHER,
    3: ResourceResultType.FEED,
    4: ResourceResultType.FRAME,
    5: ResourceResultType.OTHER,
    6: ResourceResultType.IMAGE,
    7: ResourceResultType.AUDIO,
    8: ResourceResultType.VIDEO,
    9: ResourceResultType.FONT,
    10: ResourceResultType.CSS,
    11: ResourceResultType.SCRIPT,
    12: ResourceResultType.OTHER,
    13: ResourceResultType.TEXT,
    14: ResourceResultType.PDF,
    15: ResourceResultType.DOC
}

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
            id: resource identifier
            url: resource URL
            site: site identifier the resource belongs to
            crawl: crawl identifier the resource was found in
            type: type of resource
            name: resource name
            headers: HTTP headers
            content: resource content
            created: creation timestamp
            modified: last modification timestamp
            status: HTTP status code
            size: size in bytes
            time: response time in milliseconds
            thumbnail: base64 encoded thumbnail (experimental)
            metadata: additional metadata for the resource
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

        # set externally
        self.__extras: dict[str, str] = {}

    def to_dict(self) -> dict[str, METADATA_VALUE_TYPE]:
        """
        Convert the object to a dictionary suitable for JSON serialization.
        """
        result: dict[str, METADATA_VALUE_TYPE] = {
            "id": self.id,
            "url": self.url,
            "site": self.site,
            "crawl": self.crawl,
            "type": self.type.value if self.type else None,
            "name": self.name,
            "headers": self.headers,
            "content": self.content,
            "created": to_isoformat_zulu(self.created) if self.created else None,
            "modified": to_isoformat_zulu(self.modified) if self.modified else None,
            "status": self.status,
            "size": self.size,
            "time": self.time,
            "metadata": self.metadata  # reserved
        }
        if self.__extras:
            result["extras"] = {k: v for k, v in self.__extras.items()}

        return {k: v for k, v in result.items() if v is not None and not (k == "metadata" and v == {})}

    def set_extra(self, extra_name: str, extra_value: str) -> None:
        assert extra_name in RESOURCE_EXTRAS_ALLOWED, f"Unexpected extra requested. {extra_name}"
        self.__extras[extra_name] = extra_value

    def to_forcefield_dict(self, forcefields=None) -> dict[str, METADATA_VALUE_TYPE]:
        """
        Create a dictionary with forced fields set to None if not present in the object.

        Args:
            forcefields: list of field names that should be included in the result
                even if they're not present in the object data

        Returns:
            Dictionary containing object data with forced fields included
        """
        result = {}
        if forcefields:
            result = {k: None for k in forcefields}
        result.update(self.to_dict())
        return result
