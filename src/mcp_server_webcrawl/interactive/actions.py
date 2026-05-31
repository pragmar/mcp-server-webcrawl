from dataclasses import dataclass
from typing import Optional

from mcp_server_webcrawl.interactive.ui import UiState, UiFocusable
from mcp_server_webcrawl.models.resources import ResourceResult
from mcp_server_webcrawl.interactive.config import AppConfig

class Action:
    """
    Base type for intents returned from handle_input.
    """
    pass

@dataclass
class Transition(Action):
    """
    Switch to another UI state, optionally changing focus.
    """
    state: UiState
    focus: Optional[UiFocusable] = None

@dataclass
class RunSearch(Action):
    """
    Re-run the search from the current form state.
    """
    immediate: bool = False

@dataclass
class OpenDocument(Action):
    """
    Open the document viewer for a chosen result. The session performs the fetch.
    """
    result: ResourceResult

@dataclass
class ApplyConfig(Action):
    """
    Reconfigure the app with a freshly loaded crawler/datasrc pairing.
    """
    config: AppConfig

@dataclass
class Quit(Action):
    """
    Exit the application.
    """
    pass
