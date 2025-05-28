from datetime import datetime
from typing import Final
from pathlib import Path

from mcp_server_webcrawl.models import METADATA_VALUE_TYPE
from mcp_server_webcrawl.utils import to_isoformat_zulu

SITES_TOOL_NAME: Final[str] = "webcrawl_sites"
SITES_FIELDS_REQUIRED: Final[list[str]] = ["id", "url"]
SITES_FIELDS_DEFAULT: Final[list[str]] = SITES_FIELDS_REQUIRED + ["created", "modified"]

class SiteResult:
    """
    Represents a website or crawl directory result.
    """

    def __init__(
        self,
        id: int,
        url: str | None = None,
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
            url: site URL
            path: path to site data, different from datasrc
            created: creation timestamp
            modified: last modification timestamp
            robots: robots.txt content
            metadata: additional metadata for the site
        """
        self.id = id
        self.url = url
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
            "url": self.url,
            "created": to_isoformat_zulu(self.created) if self.created else None,
            "modified": to_isoformat_zulu(self.modified) if self.modified else None,
            "robots": self.robots,
            "metadata": self.metadata if self.metadata else None,
        }

        return {k: v for k, v in result.items() if v is not None and not (k == "metadata" and v == {})}

    def to_forcefield_dict(self, forcefields: list[str]) -> dict[str, METADATA_VALUE_TYPE]:
        """
        Convert the object to a dictionary with specified fields forced to exist.

        Creates a dictionary that includes all non-None values from the forcefields list,
        and ensuring all fields in the forcefields list exist, even if null.

        Args:
            forcefields: list of field names that must appear in the output dictionary
                with at least a None value

        Returns:
            Dictionary containing all non-None object attributes, plus forced fields
            set to None if not already present
        """
        # None self-annihilates in filter, forcefields can force their existence, as null
        result = {}
        if forcefields:
            result = {k: None for k in forcefields}
        result.update(self.to_dict())
        return result
