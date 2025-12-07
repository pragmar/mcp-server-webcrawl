from typing import Union
from datetime import datetime
from pathlib import Path

METADATA_VALUE_TYPE = Union[str, int, float, bool, datetime, Path, dict, list, None]

class BaseModel:

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
