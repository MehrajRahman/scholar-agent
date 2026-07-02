"""MCP (Model Context Protocol) server.

Exposes the Scout's real-world tools — and the whole pipeline — over MCP so any
MCP client (Claude Desktop, IDEs, other agents) can call them. MCP is the
emerging open standard for tool/context interop, which makes this platform a
*provider* in a larger agent ecosystem, not a closed silo.

Run:  python -m scholar.mcp_server        (stdio transport)
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .graph_app import run_pipeline
from .observability import configure_logging
from .tools import (
    fetch_clean_text,
    openalex_professor,
    openalex_works,
    search_nih,
    search_nsf,
    web_search,
)

configure_logging()
mcp = FastMCP("scholar-agent")

# --- Expose Scout tools ---------------------------------------------------
mcp.tool()(web_search)
mcp.tool()(openalex_works)
mcp.tool()(openalex_professor)
mcp.tool()(search_nsf)
mcp.tool()(search_nih)
mcp.tool()(fetch_clean_text)


@mcp.tool()
async def find_opportunities(cv_text: str, query: str = "") -> dict:
    """Run the full matchmaking + synthesis pipeline on a CV and return bundles."""
    final = await run_pipeline([cv_text], query)
    return {
        "matches": [m.model_dump() for m in final.get("matches", [])],
        "bundles": [b.model_dump() for b in final.get("bundles", [])],
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
