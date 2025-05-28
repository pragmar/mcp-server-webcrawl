def __cli_apply_color(text: str, code: int):
    return f"\033[{code}m{text}\033[0m"

def __cli_light_gray(text):
    return __cli_apply_color(text, "38;2;130;130;130")

def __cli_gold(text):
    return __cli_apply_color(text, "38;2;170;120;0")

def get_help_short_message(version: str) -> str:
    return f"""{__cli_gold('mcp-server-webcrawl')} {__cli_light_gray("v" + version + ', ©2025 MPL2,')} {__cli_gold('--help')} for more information"""

def get_help_long_message(version: str) -> str:
    return f"""A server to connect your web crawls/archives to an LLM via MCP (Model Context Protocol).

Usage: {__cli_gold('mcp-server-webcrawl')} [-c {{wget,warc,interrobot,katana,siteone}}] [-d DATASRC]

Options:
  -c, --crawler  Specify which crawler to use
  -d, --datasrc  Path to datasrc (required unless testing)
  -h, --help     Show this help message and exit

Where is my DATASRC?
  wget           Directory containing the webroot archives
  warc           Directory containing WARC files
  interrobot     Path to */interrobot.v2.db
  katana         Directory containing the webroot archives
  siteone        Directory containing the webroot archives
                   (requires archive option)

                        [DATASRC]
           ╭─────────────────────────────────╮
   ✧───────────────────────✧ ✧───────────────────────✧
  ╱ example.com (webroot) ╱ ╱ pragmar.com (webroot) ╱
 ✧───────────────────────✧ ✧───────────────────────✧

MCP Configuration Example:
{{"mcpServers": {{
  "wget": {{
    "command": "mcp-server-webcrawl",
      "args": ["--crawler", "wget", "--datasrc",
        "/path/to/archived/hosts/"]}},
  "interrobot": {{
    "command": "mcp-server-webcrawl",
      "args": ["--crawler", "interrobot", "--datasrc",
        "/path/to/interrobot.v2.db"]}}
  }}
}}

{__cli_gold('mcp-server-webcrawl')} {__cli_light_gray("v" + version + ', ©2025 MPL2')}
https://github.com/pragmar/mcp-server-webcrawl
"""
