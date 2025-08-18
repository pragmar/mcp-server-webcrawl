import logging
from pathlib import Path

# DEBUG overrides LOG_LEVEL
DEBUG: bool = False
DATA_DIRECTORY: Path = Path.home() / ".mcp_server_webcrawl"

# logging.NOTSET will not write to a log file, all other levels will
# LOG_LEVEL: int = logging.ERROR

# LOG_PATH will automatically fallback to DATA_DIRECTORY / mcp-server-webcrawl.log
# LOG_PATH: Path = Path.home() / "Desktop" / "mcpdemo" / "server_log.txt"

try:
    from .settings_local import *
except ImportError:
    pass
