
# to build docs
mcp_server_webcrawl> 
sphinx-apidoc -o sphinx src/mcp_server_webcrawl
sphinx-build -b html ./sphinx ./docs
