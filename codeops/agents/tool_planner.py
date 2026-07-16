"""
Tool planner — decides, for a given request, which GitHub tools should be
called (in order) and whether the request should be refused or escalated
before any tool runs.

This is the deterministic tool-selection + safety-gating policy. In the live
system the model chooses tools inside the loop; this policy is (a) the
pre-flight guardrail the agent enforces regardless of the model, and (b) the
offline, gradeable target of the eval harness (evals/). The same golden cases
grade the live model by capturing its actual tool_use order instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ToolPlan:
    action: str  # "proceed" | "refuse" | "escalate"
    tools: list[str] = field(default_factory=list)
    reason: str = ""


# A PR reference: a full /pull/ URL, or owner/repo#N shorthand.
_PR_REF = re.compile(r"github\.com/[\w.-]+/[\w.-]+/pull/\d+|\b[\w.-]+/[\w.-]+#\d+\b")

# Destructive / exfiltration intent → refuse outright.
_DESTRUCTIVE = (
    "delete", "force-push", "force push", "rm -rf", "drop table",
    "wipe", "exfiltrat", "leak", "secret", "credential", "steal",
)
# Privilege bypass → escalate to a human / privileged path, never auto-run.
_ESCALATE = (
    "bypass", "skip the required", "skip required", "admin token",
    "disable branch protection", "merge without review", "override",
    "elevate", "sudo",
)


def plan_tools(task: str) -> ToolPlan:
    """Return the tool plan for a request.

    Safety gate runs first: destructive/exfiltration requests are refused and
    privilege-bypass requests are escalated, before any tool is planned.
    """
    t = task.lower()

    if any(k in t for k in _DESTRUCTIVE):
        return ToolPlan("refuse", [], "destructive or exfiltration request")
    if any(k in t for k in _ESCALATE):
        return ToolPlan("escalate", [], "requires privileged action or human approval")

    is_pr = bool(_PR_REF.search(task)) or (
        ("pull request" in t or re.search(r"\bpr\b", t))
        and any(w in t for w in ("review", "summar", "changed"))
    )
    if is_pr:
        return ToolPlan("proceed", ["get_pull_request", "get_pr_files"])
    if "comment" in t and ("pr" in t or "pull request" in t):
        return ToolPlan("proceed", ["get_pr_comments"])
    if "issue" in t and ("list" in t or "open" in t):
        return ToolPlan("proceed", ["list_issues"])
    if "issue" in t:
        return ToolPlan("proceed", ["get_issue"])
    if "content" in t or re.search(r"\bfile\b", t):
        return ToolPlan("proceed", ["get_file_content"])
    if "files" in t or "directory" in t:
        return ToolPlan("proceed", ["list_repo_files"])
    return ToolPlan("proceed", [])
