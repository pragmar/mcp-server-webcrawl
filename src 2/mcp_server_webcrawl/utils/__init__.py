import re

from datetime import datetime

def to_isoformat_zulu(dt: datetime):
    """
    Convert datetime to iso Z.

    python<=3.10 struggles with Z and fractions of seconds, will
    throw. smooth out the iso string, second precision isn't key here
    """
    return dt.isoformat().replace("+00:00", "Z")

def from_isoformat_zulu(dt_string: str | None) -> datetime:
    """
    Convert ISO string to datetime.

    python<=3.10 struggles with Z and fractions of seconds, will
    throw. smooth out the iso string, second precision isn't key here
    """

    if not dt_string:
        return None
    dt_string = dt_string.replace("Z", "+00:00")
    match = re.match(r"(.*\.\d{6})\d*([-+]\d{2}:\d{2}|$)", dt_string)
    if match:
        dt_string = match.group(1) + (match.group(2) or "")
    return datetime.fromisoformat(dt_string)
