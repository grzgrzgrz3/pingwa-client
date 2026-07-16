# Runs the pingwa MCP server (stdio) — used by MCP directory sandboxes (Glama)
# to start the server and introspect its tools. The server starts without
# PINGWA_KEY; tools return an actionable error explaining how to get one.
FROM python:3.12-slim
RUN pip install --no-cache-dir pingwa
ENTRYPOINT ["pingwa", "mcp"]
