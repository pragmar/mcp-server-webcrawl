from datetime import datetime
from typing import Final
from pathlib import Path
from enum import Enum

from mcp_server_webcrawl.models.base import BaseModel, METADATA_VALUE_TYPE
from mcp_server_webcrawl.utils import to_isoformat_zulu

class SiteType(Enum):
    UNDEFINED = "undefined"
    CRAWLED_URL = "url"
    CRAWLED_LIST = "list"

SITES_TOOL_NAME: Final[str] = "webcrawl_sites"
SITES_FIELDS_BASE: Final[list[str]] = ["id", "name", "type", "urls"]
SITES_FIELDS_DEFAULT: Final[list[str]] = SITES_FIELDS_BASE + ["created", "modified"]

class SiteResult(BaseModel):
    """
    Represents a website or crawl directory result.
    """

    def __init__(
        self,
        id: int,
        name: str | None = None,
        type: SiteType = SiteType.CRAWLED_URL,
        urls: list[str] | None = None,
        path: Path = None,
        created: datetime | None = None,
        modified: datetime | None = None,
        robots: str | None = None,
        metadata: dict[str, METADATA_VALUE_TYPE] | None = None
    ):
        """
        Initialize a SiteResult instance.

        Args:
            id: site identifier
            name: site name, either a URL or a custom job
            urls: site URL(s), multiple for list type crawls
            path: path to site data, different from datasrc
            created: creation timestamp
            modified: last modification timestamp
            robots: robots.txt content
            metadata: additional metadata for the site
        """
        self.id = id
        self.name = name
        self.type = type
        self.urls = urls
        self.path = path
        self.created = created
        self.modified = modified
        self.robots = robots
        self.metadata = metadata or {}

    def to_dict(self) -> dict[str, METADATA_VALUE_TYPE]:
        """
        Convert the object to a dictionary suitable for JSON serialization.
        """
        result: dict[str, METADATA_VALUE_TYPE] = {
            "id": self.id,
            "name": self.name,
            "type": self.type.value,
            "urls": self.urls,
            "created": to_isoformat_zulu(self.created) if self.created else None,
            "modified": to_isoformat_zulu(self.modified) if self.modified else None,
            "metadata": self.metadata if self.metadata else None,
        }

        return {k: v for k, v in result.items() if v is not None and not (k == "metadata" and v == {})}
