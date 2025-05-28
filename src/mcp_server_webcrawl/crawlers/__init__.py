
from pathlib import Path

def get_fixture_directory():
    modroot: Path = Path(__file__).parent.parent.parent.parent
    # assumes git project structure to locate fixtures
    assert modroot.name == "mcp-server-webcrawl", f"expected modroot mcp_server_webcrawl, got {modroot.name}"
    return modroot / "fixtures"
