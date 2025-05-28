import logging
from pathlib import Path
from typing import Final

import mcp_server_webcrawl.settings as settings
from mcp_server_webcrawl.settings import DEBUG, DATA_DIRECTORY

DEFAULT_LOG_KEY: Final[str] = "mcp-server-webcrawl"
DEFAULT_LOG_PATH: Final[Path] = DATA_DIRECTORY / "mcp-server-webcrawl.log"
DEFAULT_LOG_LEVEL: Final[int] = logging.WARNING

def get_logger_configuration() -> tuple[str, Path, int]:
    """
    Get log name, path, and level (in that order)

    Returns:
        tuple[str, Path, int]: A tuple containing name, path, and level
    """

    log_path: Path = DEFAULT_LOG_PATH
    log_level: int = DEFAULT_LOG_LEVEL

    log_level = logging.DEBUG if DEBUG else getattr(settings, "LOG_LEVEL", DEFAULT_LOG_LEVEL)
    log_path = getattr(settings, "LOG_PATH", DEFAULT_LOG_PATH)
    return (DEFAULT_LOG_KEY, log_path, log_level)

def get_logger() -> logging.Logger:
    """
    Get logger, usually in order to write to it

    Returns:
        Logger: a writable logging object (error/warn/info/debug)
    """

    (log_name, _, _) = get_logger_configuration()
    return logging.getLogger(log_name)

def initialize_logger() -> None:
    """
    Validate and set up logger for writing

    Returns:
        None
    """

    (log_name, log_path, log_level) = get_logger_configuration()
    if log_level == logging.NOTSET:
        # don't set up anything, named logging will effectively evaporate
        return

    assert isinstance(log_level, int) and log_level != 0, "LOG_LEVEL must be set"
    assert isinstance(log_path, Path), "LOG_PATH must be a Path object"
    assert isinstance(log_name, str) and log_name.strip() != "", "LOG_NAME must be a non-empty string"
    assert all(c.isalpha() or c in "-_" for c in log_name), "LOG_NAME must contain only A-Z, a-z, hyphens, and underscores"

    # handle custom log paths differently, don't generate directories
    if ".mcp_server_webcrawl" in str(log_path):
        log_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        assert log_path.parent.exists() and log_path.parent.is_dir(), \
            f"Custom parent directory `{log_path.parent}` does not exist or is not a directory"

    logging.basicConfig(filename=str(log_path), filemode="w", level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S", encoding="utf-8")

    logger: logging.Logger = logging.getLogger(log_name)

    # just set a few ops back, concurrent logger might not be ready
    if log_level <= logging.INFO:
        logger.info("🖥️ starting webcrawl MCP server")
        log_extra: str = "(Debug is True)" if DEBUG else ""
        logger.info(f"log level set to {log_level} {log_extra}")
