"""
GitHub MCP server (stdio).

Exposes the read-only GitHubConnector methods as MCP tools over the official
MCP SDK. The connector logic itself is unchanged — it now lives *behind* a
protocol boundary. FastMCP derives each tool's input schema from the function
signature and docstring; the client discovers them via tools/list.

Run standalone:
    python -m codeops.mcp.servers.github_server
Auth: reads GITHUB_TOKEN from the environment (optional for public repos).
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from codeops.mcp.connectors import GitHubConnector

mcp = FastMCP("codeops-github", log_level="WARNING")
_conn = GitHubConnector()


@mcp.tool()
def get_pull_request(owner: str, repo: str, pr_number: int) -> dict[str, Any]:
    """Fetch a pull request's metadata together with its unified diff."""
    return _conn.get_pull_request(owner, repo, pr_number)


@mcp.tool()
def get_pr_files(owner: str, repo: str, pr_number: int) -> list[dict[str, Any]]:
    """List the files changed in a pull request, with per-file patch stats."""
    return _conn.get_pr_files(owner, repo, pr_number)


@mcp.tool()
def get_pr_comments(owner: str, repo: str, pr_number: int) -> list[dict[str, Any]]:
    """Fetch the existing review comments on a pull request."""
    return _conn.get_pr_comments(owner, repo, pr_number)


@mcp.tool()
def get_issue(owner: str, repo: str, issue_number: int) -> dict[str, Any]:
    """Fetch a single issue's metadata and body."""
    return _conn.get_issue(owner, repo, issue_number)


@mcp.tool()
def list_issues(owner: str, repo: str, state: str = "open", labels: str = "") -> list[dict[str, Any]]:
    """List issues in a repository, optionally filtered by state and labels."""
    return _conn.list_issues(owner, repo, state=state, labels=labels)


@mcp.tool()
def get_file_content(owner: str, repo: str, path: str, ref: str = "main") -> str:
    """Fetch a file's decoded text content at a given ref."""
    return _conn.get_file_content(owner, repo, path, ref=ref)


@mcp.tool()
def list_repo_files(owner: str, repo: str, path: str = "", ref: str = "main") -> list[dict[str, Any]]:
    """List the contents of a directory in a repository at a given ref."""
    return _conn.list_repo_files(owner, repo, path=path, ref=ref)


if __name__ == "__main__":
    mcp.run()  # stdio transport
