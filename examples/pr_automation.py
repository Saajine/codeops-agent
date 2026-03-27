#!/usr/bin/env python3
"""
examples/pr_automation.py
──────────────────────────
Demo: GitHub PR Automation — auto-generate PR descriptions, risk assessment,
and inline review comments from a code diff.

This demo shows the enterprise use case:
  "Faster, cleaner PRs — reduce senior reviewer bottleneck by 60%"

Usage:
    python examples/pr_automation.py              # built-in demo diff
    python examples/pr_automation.py --file path/to/diff.patch
    python examples/pr_automation.py --github owner/repo 42
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from codeops.agents.github_pr import GitHubPRAgent
from codeops.memory.context import ContextManager
from codeops.memory.store import MemoryStore
from codeops.mcp.connectors import GitHubConnector

console = Console()

# ── Demo: a realistic PR diff with issues ─────────────────────────────────────

DEMO_DIFF = """\
---FILE: auth/jwt_handler.py---
import jwt
import datetime
import os

SECRET_KEY = "my-super-secret-key-1234"  # TODO: move to env

def create_token(user_id: int, role: str) -> str:
    payload = {
        "user_id": user_id,
        "role": role,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=24)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def verify_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except:
        return {}  # swallow all exceptions

def is_admin(token: str) -> bool:
    data = verify_token(token)
    return data.get("role") == "admin"
---END---

---FILE: api/users.py---
from flask import request, jsonify
from auth.jwt_handler import is_admin, verify_token
import sqlite3

DB = sqlite3.connect("users.db", check_same_thread=False)

def get_user(user_id):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not verify_token(token):
        return jsonify({"error": "Unauthorized"}), 401

    # Fetch user
    cursor = DB.execute(f"SELECT * FROM users WHERE id = {user_id}")
    user = cursor.fetchone()
    return jsonify({"user": user})

def delete_user(user_id):
    token = request.headers.get("Authorization", "")
    if is_admin(token):
        DB.execute(f"DELETE FROM users WHERE id = {user_id}")
        DB.commit()
    return jsonify({"status": "ok"})
---END---

## PR Description (submitted by author)
Added JWT auth and user management endpoints.
"""


def run_pr_automation(code: str, context_description: str) -> None:
    store = MemoryStore()
    context = ContextManager(persist=False)
    context.set_task(context_description)
    context.set_agent_output("code_generation", code, agent_name="coder")

    console.print(
        Panel(
            "[bold cyan]CodeOps Agent[/bold cyan] — PR Automation Demo\n\n"
            "Agent: [magenta]GitHubPRAgent[/magenta]\n"
            "Generates: PR description · Risk assessment · Review comments · Merge readiness",
            border_style="cyan",
        )
    )

    agent = GitHubPRAgent(store=store)

    with console.status("[cyan]🔀 Running PR automation…[/cyan]"):
        result = agent.execute(context_description, context)

    console.print("\n")
    console.print(Panel("[bold]PR Automation Output[/bold]", border_style="blue"))
    console.print(Markdown(result.output))

    meta = result.metadata
    risk = meta.get("risk_level", "?").upper()
    ready = "✅ Yes" if meta.get("merge_ready") else "❌ No"
    score = meta.get("merge_score", "?")
    comments = meta.get("review_comments", 0)

    risk_color = {"LOW": "green", "MEDIUM": "yellow", "HIGH": "red", "CRITICAL": "red bold"}.get(risk, "white")
    console.print(
        f"\n[bold]Stats:[/bold] "
        f"Risk [{risk_color}]{risk}[/{risk_color}] | "
        f"Merge ready: {ready} | "
        f"Score: {score}/10 | "
        f"Auto-comments: {comments}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="CodeOps — PR Automation Demo")
    parser.add_argument("--file", type=str, help="Path to diff/code file")
    parser.add_argument("--github", type=str, help="owner/repo (with --pr)")
    parser.add_argument("--pr", type=int, help="PR number")
    args = parser.parse_args()

    if args.file:
        p = Path(args.file)
        code = p.read_text()
        run_pr_automation(code, f"Review PR from file: {p.name}")

    elif args.github and args.pr:
        owner, repo = args.github.split("/", 1)
        console.print(f"[cyan]Fetching PR #{args.pr} from {owner}/{repo}…[/cyan]")
        connector = GitHubConnector()
        pr = connector.get_pull_request(owner, repo, args.pr)
        diff = pr.get("diff", "")[:6000]
        title = pr.get("title", "")
        code = f"## PR: {title}\n\n```diff\n{diff}\n```"
        run_pr_automation(code, f"PR #{args.pr}: {title}")

    else:
        run_pr_automation(DEMO_DIFF, "Review JWT auth implementation PR for production readiness")

    sys.exit(0)


if __name__ == "__main__":
    main()
