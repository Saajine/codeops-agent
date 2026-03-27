#!/usr/bin/env python3
"""
examples/pr_review.py
─────────────────────
Demo: Auto-review a pull request (or a local code snippet).

Modes:
  1. GitHub PR  : fetches diff + metadata and runs ReviewerAgent directly.
  2. Local file : reads a local .py / .ts / etc. file and reviews it.
  3. Inline code: review a hard-coded snippet (default demo mode).

Usage:
    # Review a GitHub PR (needs GITHUB_TOKEN in .env):
    python examples/pr_review.py --github anthropics/anthropic-sdk-python 42

    # Review a local file:
    python examples/pr_review.py --file path/to/my_module.py

    # Run the built-in demo snippet:
    python examples/pr_review.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax

from codeops.agents.reviewer import ReviewerAgent
from codeops.memory.context import ContextManager
from codeops.memory.store import MemoryStore
from codeops.mcp.connectors import GitHubConnector

console = Console()

# ── Demo snippet ──────────────────────────────────────────────────────────────

DEMO_CODE = '''\
---FILE: user_service.py---
"""User service — manages user CRUD operations."""
import hashlib, sqlite3
from typing import Optional

DB_PATH = "users.db"

def get_db():
    return sqlite3.connect(DB_PATH)

def create_user(username: str, password: str, email: str):
    """Create a new user account."""
    db = get_db()
    pw_hash = hashlib.md5(password.encode()).hexdigest()  # hash the password
    query = f"INSERT INTO users VALUES ('{username}', '{pw_hash}', '{email}')"
    db.execute(query)
    db.commit()
    print(f"User {username} created!")
    return True

def get_user(username: str) -> Optional[dict]:
    """Fetch user by username."""
    db = get_db()
    result = db.execute(
        f"SELECT * FROM users WHERE username = '{username}'"
    ).fetchone()
    if result:
        return {"username": result[0], "password_hash": result[1], "email": result[2]}
    return None

def authenticate(username: str, password: str) -> bool:
    """Check username / password."""
    user = get_user(username)
    if not user:
        return False
    pw_hash = hashlib.md5(password.encode()).hexdigest()
    return user["password_hash"] == pw_hash
---END---
'''

DEMO_TASK = "Review this user service implementation for a production Python web application."


def review_snippet(code: str, task: str) -> None:
    """Run the reviewer on an arbitrary code string."""
    store = MemoryStore()
    context = ContextManager()
    context.set_task(task)

    # Inject the code as if the coder had produced it
    context.set_agent_output("code_generation", code, agent_name="coder")

    console.print(
        Panel(
            "[bold cyan]CodeOps Agent[/bold cyan] — PR / Code Review Demo\n\n"
            "Agent: [yellow]Reviewer[/yellow]",
            border_style="cyan",
        )
    )

    console.print("\n[bold]Code Under Review:[/bold]")
    # Extract first FILE block for display
    import re
    m = re.search(r"---FILE:\s*(.+?)---\s*(.*?)---END---", code, re.DOTALL | re.IGNORECASE)
    display_code = m.group(2).strip() if m else code
    console.print(Syntax(display_code, "python", theme="monokai", line_numbers=True))

    console.print("\n[cyan]⟳ Running ReviewerAgent…[/cyan]")
    reviewer = ReviewerAgent(store=store)
    result = reviewer.execute(task, context)

    console.print("\n")
    console.print(Panel("[bold]Review Report[/bold]", border_style="yellow"))
    console.print(Markdown(result.output))

    # Stats
    meta = result.metadata
    score = meta.get("score", "?")
    verdict = meta.get("verdict", "?").upper()
    critical = meta.get("critical_issues", 0)
    major = meta.get("major_issues", 0)

    score_color = "green" if isinstance(score, int) and score >= 7 else "yellow" if isinstance(score, int) and score >= 5 else "red"
    verdict_color = "green" if verdict == "APPROVED" else "red"

    console.print(
        f"\n[bold]Verdict:[/bold] [{verdict_color}]{verdict}[/{verdict_color}]  |  "
        f"[bold]Score:[/bold] [{score_color}]{score}/10[/{score_color}]  |  "
        f"Critical: [red]{critical}[/red]  Major: [yellow]{major}[/yellow]"
    )


def review_github_pr(owner: str, repo: str, pr_number: int) -> None:
    """Fetch a GitHub PR and review it."""
    console.print(f"[cyan]Fetching PR #{pr_number} from {owner}/{repo}…[/cyan]")
    connector = GitHubConnector()
    pr = connector.get_pull_request(owner, repo, pr_number)

    title = pr.get("title", "")
    body = pr.get("body", "") or ""
    diff = pr.get("diff", "")

    # Build a code blob from the diff
    code_blob = f"## PR: {title}\n\n{body}\n\n## Diff\n```diff\n{diff[:8000]}\n```"
    task = f"Review this GitHub pull request: '{title}' in {owner}/{repo}"

    review_snippet(code_blob, task)


def review_local_file(file_path: str) -> None:
    """Read a local file and review it."""
    p = Path(file_path)
    if not p.exists():
        console.print(f"[red]File not found: {file_path}[/red]")
        sys.exit(1)
    content = p.read_text(encoding="utf-8")
    ext = p.suffix.lstrip(".")
    code_blob = f"---FILE: {p.name}---\n{content}\n---END---"
    task = f"Review this {ext} file for production readiness: {p.name}"
    review_snippet(code_blob, task)


def main() -> None:
    parser = argparse.ArgumentParser(description="CodeOps Agent — PR Review Demo")
    sub = parser.add_subparsers(dest="mode")

    gh = sub.add_parser("--github", help="Review a GitHub PR")
    gh.add_argument("repo", help="owner/repo")
    gh.add_argument("pr_number", type=int, help="PR number")

    lf = sub.add_parser("--file", help="Review a local file")
    lf.add_argument("path", help="Path to file")

    args, remaining = parser.parse_known_args()

    if args.mode == "--github":
        owner, repo = args.repo.split("/", 1)
        review_github_pr(owner, repo, args.pr_number)
    elif args.mode == "--file":
        review_local_file(args.path)
    else:
        # Default: run the built-in demo
        # Check for simple CLI flags
        if len(sys.argv) >= 3 and sys.argv[1] == "--github":
            owner, repo = sys.argv[2].split("/", 1)
            pr_number = int(sys.argv[3])
            review_github_pr(owner, repo, pr_number)
        elif len(sys.argv) >= 3 and sys.argv[1] == "--file":
            review_local_file(sys.argv[2])
        else:
            review_snippet(DEMO_CODE, DEMO_TASK)


if __name__ == "__main__":
    main()
