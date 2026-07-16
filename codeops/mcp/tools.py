"""
Anthropic tool definitions for the read-only GitHubConnector methods.

Each of the seven read methods on GitHubConnector is exposed to Claude as a
tool. The `input_schema` for each is derived directly from the method
signature: positional parameters with no default are `required`; parameters
with a default are optional (and the default is documented). Tool name ==
connector method name, so dispatch is a straight attribute lookup.

The agent's tool-execution loop (BaseAgent._run_tool_loop) sends these
definitions to the model, then validates and dispatches whatever tool_use
blocks the model returns back to the connector.
"""

from __future__ import annotations

from typing import Any, Callable

from codeops.mcp.connectors import GitHubConnector

# Reused property fragments — every GitHub tool identifies a repo the same way.
_OWNER = {"type": "string", "description": "Repository owner (user or org login)."}
_REPO = {"type": "string", "description": "Repository name."}


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


# name -> (description, input_schema).  Names match GitHubConnector methods 1:1.
GITHUB_TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_pull_request",
        "description": "Fetch a pull request's metadata together with its unified diff.",
        "input_schema": _schema(
            {
                "owner": _OWNER,
                "repo": _REPO,
                "pr_number": {"type": "integer", "description": "Pull request number."},
            },
            ["owner", "repo", "pr_number"],
        ),
    },
    {
        "name": "get_pr_files",
        "description": "List the files changed in a pull request, with per-file patch stats.",
        "input_schema": _schema(
            {
                "owner": _OWNER,
                "repo": _REPO,
                "pr_number": {"type": "integer", "description": "Pull request number."},
            },
            ["owner", "repo", "pr_number"],
        ),
    },
    {
        "name": "get_pr_comments",
        "description": "Fetch the existing review comments on a pull request.",
        "input_schema": _schema(
            {
                "owner": _OWNER,
                "repo": _REPO,
                "pr_number": {"type": "integer", "description": "Pull request number."},
            },
            ["owner", "repo", "pr_number"],
        ),
    },
    {
        "name": "get_issue",
        "description": "Fetch a single issue's metadata and body.",
        "input_schema": _schema(
            {
                "owner": _OWNER,
                "repo": _REPO,
                "issue_number": {"type": "integer", "description": "Issue number."},
            },
            ["owner", "repo", "issue_number"],
        ),
    },
    {
        "name": "list_issues",
        "description": "List issues in a repository, optionally filtered by state and labels.",
        "input_schema": _schema(
            {
                "owner": _OWNER,
                "repo": _REPO,
                "state": {
                    "type": "string",
                    "enum": ["open", "closed", "all"],
                    "description": "Issue state filter. Defaults to 'open'.",
                },
                "labels": {
                    "type": "string",
                    "description": "Comma-separated label filter. Defaults to no filter.",
                },
            },
            ["owner", "repo"],
        ),
    },
    {
        "name": "get_file_content",
        "description": "Fetch a file's decoded text content at a given ref.",
        "input_schema": _schema(
            {
                "owner": _OWNER,
                "repo": _REPO,
                "path": {"type": "string", "description": "Path to the file within the repo."},
                "ref": {
                    "type": "string",
                    "description": "Git ref (branch, tag, or SHA). Defaults to 'main'.",
                },
            },
            ["owner", "repo", "path"],
        ),
    },
    {
        "name": "list_repo_files",
        "description": "List the contents of a directory in a repository at a given ref.",
        "input_schema": _schema(
            {
                "owner": _OWNER,
                "repo": _REPO,
                "path": {
                    "type": "string",
                    "description": "Directory path within the repo. Defaults to the root.",
                },
                "ref": {
                    "type": "string",
                    "description": "Git ref (branch, tag, or SHA). Defaults to 'main'.",
                },
            },
            ["owner", "repo"],
        ),
    },
]

# The tool names Claude is allowed to call, for quick membership checks.
GITHUB_TOOL_NAMES: set[str] = {t["name"] for t in GITHUB_TOOLS}


def build_github_dispatch(
    connector: GitHubConnector | None = None,
) -> dict[str, Callable[..., Any]]:
    """Map each tool name to the bound connector method that executes it."""
    conn = connector or GitHubConnector()
    return {name: getattr(conn, name) for name in GITHUB_TOOL_NAMES}
