"""
MCP Protocol Connectors — adapters that let agents interact with external tools.

Currently implemented:
  - GitHubConnector  : fetch PRs, issues, file contents via GitHub REST API
  - FileSystemConnector : read / write / list local files safely

Each connector exposes a standard interface so agents can call them without
knowing the underlying transport.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx

from codeops.config import config

logger = logging.getLogger(__name__)


# ── Base connector ────────────────────────────────────────────────────────────


class MCPConnector:
    """Abstract base for all MCP connectors."""

    name: str = "base"

    def health_check(self) -> dict[str, Any]:
        return {"connector": self.name, "status": "ok"}


# ── GitHub connector ──────────────────────────────────────────────────────────


class GitHubConnector(MCPConnector):
    """
    Connects to the GitHub REST API.

    Required env var: GITHUB_TOKEN
    """

    name = "github"
    BASE_URL = "https://api.github.com"

    def __init__(self, token: str | None = None) -> None:
        self.token = token or config.GITHUB_TOKEN
        self._headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            self._headers["Authorization"] = f"Bearer {self.token}"

    # ── Pull Requests ─────────────────────────────────────────────────────────

    def get_pull_request(self, owner: str, repo: str, pr_number: int) -> dict[str, Any]:
        """Fetch PR metadata + diff."""
        pr = self._get(f"/repos/{owner}/{repo}/pulls/{pr_number}")
        diff = self._get_raw(
            f"/repos/{owner}/{repo}/pulls/{pr_number}",
            headers={**self._headers, "Accept": "application/vnd.github.diff"},
        )
        pr["diff"] = diff
        return pr

    def get_pr_files(self, owner: str, repo: str, pr_number: int) -> list[dict[str, Any]]:
        """Return list of changed files in a PR."""
        return self._get(f"/repos/{owner}/{repo}/pulls/{pr_number}/files")

    def get_pr_comments(self, owner: str, repo: str, pr_number: int) -> list[dict[str, Any]]:
        return self._get(f"/repos/{owner}/{repo}/pulls/{pr_number}/comments")

    # ── Issues ────────────────────────────────────────────────────────────────

    def get_issue(self, owner: str, repo: str, issue_number: int) -> dict[str, Any]:
        return self._get(f"/repos/{owner}/{repo}/issues/{issue_number}")

    def list_issues(
        self, owner: str, repo: str, state: str = "open", labels: str = ""
    ) -> list[dict[str, Any]]:
        params = f"state={state}"
        if labels:
            params += f"&labels={labels}"
        return self._get(f"/repos/{owner}/{repo}/issues?{params}")

    # ── Repository ────────────────────────────────────────────────────────────

    def get_file_content(self, owner: str, repo: str, path: str, ref: str = "main") -> str:
        """Fetch a file's decoded text content."""
        import base64
        data = self._get(f"/repos/{owner}/{repo}/contents/{path}?ref={ref}")
        if isinstance(data, dict) and data.get("encoding") == "base64":
            return base64.b64decode(data["content"]).decode("utf-8")
        return str(data)

    def list_repo_files(
        self, owner: str, repo: str, path: str = "", ref: str = "main"
    ) -> list[dict[str, Any]]:
        return self._get(f"/repos/{owner}/{repo}/contents/{path}?ref={ref}")

    # ── HTTP helpers ──────────────────────────────────────────────────────────

    def _get(self, endpoint: str) -> Any:
        url = self.BASE_URL + endpoint
        with httpx.Client(timeout=30) as client:
            resp = client.get(url, headers=self._headers)
            resp.raise_for_status()
            return resp.json()

    def _get_raw(self, endpoint: str, headers: dict[str, str] | None = None) -> str:
        url = self.BASE_URL + endpoint
        with httpx.Client(timeout=30) as client:
            resp = client.get(url, headers=headers or self._headers)
            resp.raise_for_status()
            return resp.text

    def health_check(self) -> dict[str, Any]:
        try:
            data = self._get("/user") if self.token else self._get("/zen")
            return {"connector": self.name, "status": "ok", "authenticated": bool(self.token)}
        except Exception as exc:
            return {"connector": self.name, "status": "error", "error": str(exc)}


# ── File system connector ─────────────────────────────────────────────────────


class FileSystemConnector(MCPConnector):
    """
    Safe local file-system access for agents.

    All paths are resolved relative to *root_dir* and must stay within it
    (path traversal protection).
    """

    name = "filesystem"

    def __init__(self, root_dir: str | None = None) -> None:
        self.root = Path(root_dir or os.getcwd()).resolve()

    def _safe_path(self, relative: str) -> Path:
        target = (self.root / relative).resolve()
        if not str(target).startswith(str(self.root)):
            raise PermissionError(f"Path traversal attempt blocked: {relative}")
        return target

    def read_file(self, path: str) -> str:
        """Read a text file, returning its contents."""
        p = self._safe_path(path)
        return p.read_text(encoding="utf-8")

    def write_file(self, path: str, content: str) -> None:
        """Write content to a file, creating directories as needed."""
        p = self._safe_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        logger.info("Wrote %d bytes to %s", len(content), p)

    def list_files(self, directory: str = "", pattern: str = "**/*") -> list[str]:
        """Return relative paths of files matching *pattern* under *directory*."""
        base = self._safe_path(directory) if directory else self.root
        return [
            str(p.relative_to(self.root))
            for p in base.glob(pattern)
            if p.is_file()
        ]

    def file_exists(self, path: str) -> bool:
        try:
            return self._safe_path(path).exists()
        except PermissionError:
            return False

    def delete_file(self, path: str) -> None:
        p = self._safe_path(path)
        if p.exists():
            p.unlink()

    def health_check(self) -> dict[str, Any]:
        return {
            "connector": self.name,
            "status": "ok",
            "root": str(self.root),
            "writable": os.access(self.root, os.W_OK),
        }


# ── CI/CD stub (future) ───────────────────────────────────────────────────────


class CICDConnector(MCPConnector):
    """
    Stub connector for CI/CD systems (GitHub Actions, Jenkins, etc.).
    Marked as roadmap — not yet implemented.
    """

    name = "cicd"

    def trigger_pipeline(self, pipeline_id: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        raise NotImplementedError("CICDConnector is on the roadmap — not yet available.")

    def get_pipeline_status(self, run_id: str) -> dict[str, Any]:
        raise NotImplementedError("CICDConnector is on the roadmap — not yet available.")

    def health_check(self) -> dict[str, Any]:
        return {"connector": self.name, "status": "roadmap", "message": "Not yet implemented."}


# ── Registry ──────────────────────────────────────────────────────────────────


class ConnectorRegistry:
    """Lightweight registry so agents can resolve connectors by name."""

    def __init__(self) -> None:
        self._connectors: dict[str, MCPConnector] = {}

    def register(self, connector: MCPConnector) -> None:
        self._connectors[connector.name] = connector

    def get(self, name: str) -> MCPConnector | None:
        return self._connectors.get(name)

    def health_report(self) -> list[dict[str, Any]]:
        return [c.health_check() for c in self._connectors.values()]


# ── Default registry ──────────────────────────────────────────────────────────

connector_registry = ConnectorRegistry()
connector_registry.register(GitHubConnector())
connector_registry.register(FileSystemConnector())
connector_registry.register(CICDConnector())
