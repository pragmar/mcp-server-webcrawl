
from pathlib import Path
# DEBUG overrides LOG_LEVEL

DEBUG: bool = False
DATA_DIRECTORY: Path = Path.home() / ".mcp_server_webcrawl"

# LOG_PATH will automatically fallback to DATA_DIRECTORY / log.txt
# LOG_PATH: Path = Path.home() / "Desktop" / "mcp" / "mcplog.txt"

# logging get by name key
# LOG_NAME: str = "mcp_server_webcrawler"

# logging.NOTSET will NOT write to a log file, all other levels will
# LOG_LEVEL: int = logging.NOTSET

try:
    from .settings_local import *
except ImportError:
    pass
