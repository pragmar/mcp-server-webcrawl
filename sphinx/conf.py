# to build docs
# mcp_server_webcrawl> sphinx-apidoc -o sphinx src/mcp_server_webcrawl 
# mcp_server_webcrawl> cd .\sphinx\
# mcp_server_webcrawl\sphinx> sphinx-build -b html . ../docs

import os
import sys

# path the src directory for autodiscovery
sys.path.insert(0, os.path.abspath("../../src"))

project = "mcp-server-webcrawl"
copyright = "2025, pragmar"
author = "pragmar"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
    "sphinx.ext.napoleon",
    "sphinx.ext.coverage",
    "sphinx.ext.intersphinx",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "**/settings_local.py"]


html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
html_theme_options = {
    "navigation_depth": 2,  # This is the key setting to prevent deep nesting
    "titles_only": False,
}
# Better autodoc formatting
autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": False,
    "member-order": "bysource",
}

autodoc_member_order = "groupwise"
autodoc_typehints = "description"
autodoc_class_signature = "separated"
# autodoc_mock_imports = ["mcp_server_webcrawl.settings_local"]
add_module_names = False
autoclass_content = "both"


intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}


toctree_maxdepth = 2