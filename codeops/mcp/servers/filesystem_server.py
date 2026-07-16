"""
Filesystem MCP server (stdio).

Exposes the FileSystemConnector methods as MCP tools. The connector's
path-traversal guard (_safe_path) still applies — every operation stays
within the root directory.

Run standalone:
    python -m codeops.mcp.servers.filesystem_server
Root: CODEOPS_FS_ROOT env var, or the process working directory.
"""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from codeops.mcp.connectors import FileSystemConnector

mcp = FastMCP("codeops-filesystem", log_level="WARNING")
_conn = FileSystemConnector(root_dir=os.getenv("CODEOPS_FS_ROOT") or os.getcwd())


@mcp.tool()
def read_file(path: str) -> str:
    """Read a text file (relative to the server root) and return its contents."""
    return _conn.read_file(path)


@mcp.tool()
def write_file(path: str, content: str) -> str:
    """Write content to a file (relative to the server root), creating dirs as needed."""
    _conn.write_file(path, content)
    return f"wrote {len(content)} bytes to {path}"


@mcp.tool()
def list_files(directory: str = "", pattern: str = "**/*") -> list[str]:
    """List files under a directory matching a glob pattern (relative to the root)."""
    return _conn.list_files(directory, pattern)


@mcp.tool()
def file_exists(path: str) -> bool:
    """Return whether a file exists within the server root."""
    return _conn.file_exists(path)


@mcp.tool()
def delete_file(path: str) -> str:
    """Delete a file within the server root."""
    _conn.delete_file(path)
    return f"deleted {path}"


if __name__ == "__main__":
    mcp.run()  # stdio transport
