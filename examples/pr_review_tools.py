"""
Real-PR review via Anthropic tool calls.

The GitHubPRAgent hands Claude the seven read-only GitHub tools and lets it
call get_pull_request / get_pr_files (and friends) itself — actual tool_use
round-trips — before writing the review. Nothing here regex-parses free text.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    # optional, lifts GitHub rate limits / enables private repos:
    export GITHUB_TOKEN=ghp_...
    python examples/pr_review_tools.py https://github.com/psf/requests/pull/6432

Prints the review, plus which tools the model actually called.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from codeops.agents.github_pr import GitHubPRAgent
from codeops.memory.context import ContextManager


def main() -> int:
    pr = sys.argv[1] if len(sys.argv) > 1 else "https://github.com/psf/requests/pull/6432"

    agent = GitHubPRAgent()
    if agent._demo_mode:
        print("Demo mode is on (CODEOPS_DEMO). Unset it to make real tool calls.")
        return 1

    context = ContextManager(persist=False)
    result = agent.execute(f"Review this pull request: {pr}", context)

    print("=" * 70)
    print(result.output)
    print("=" * 70)
    print(f"status      : {result.status}")
    print(f"pr          : {result.metadata.get('pr')}")
    print(f"tools_used  : {result.metadata.get('tools_used')}")

    tools_used = set(result.metadata.get("tools_used", []))
    required = {"get_pull_request", "get_pr_files"}
    if required <= tools_used:
        print("\n✓ Reviewed the PR via real get_pull_request + get_pr_files tool calls.")
        return 0
    print(f"\n✗ Expected {required} to be called; got {tools_used}.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
