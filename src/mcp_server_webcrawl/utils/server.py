import os
import sys

def initialize_mcp_server() -> None:
    """
    MCP stdio streams require utf-8 explicitly set for Windows (default cp1252)
    or internationalized content will fail.
    """
    if sys.platform == "win32" and os.environ.get("PYTHONIOENCODING") is None:
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
