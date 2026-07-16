"""
GitHubPRAgent — automates pull request workflows.

Given a code diff or PR content, this agent:
  1. Generates a professional PR description (summary, changes, testing steps)
  2. Identifies risk areas (breaking changes, security issues, missing tests)
  3. Suggests reviewers based on changed files
  4. Auto-generates inline review comments for issues it finds
  5. Checks if the PR is ready to merge (CI, tests, review coverage)

Maps to enterprise use case: "Faster, cleaner PRs — reduce senior reviewer bottleneck"
"""

from __future__ import annotations

import json
import re
from typing import Any

from codeops.agents.base_agent import AgentResult, BaseAgent
from codeops.agents.tool_planner import plan_tools
from codeops.memory.context import ContextManager

# A full PR URL: https://github.com/<owner>/<repo>/pull/<n>
_PR_URL_RE = re.compile(r"github\.com/([\w.-]+)/([\w.-]+)/pull/(\d+)")
# Shorthand: <owner>/<repo>#<n>
_PR_SHORT_RE = re.compile(r"\b([\w.-]+)/([\w.-]+)#(\d+)\b")


def _extract_pr_ref(task: str) -> tuple[str, str, int] | None:
    """Return (owner, repo, pr_number) if the task references a GitHub PR."""
    match = _PR_URL_RE.search(task) or _PR_SHORT_RE.search(task)
    if match:
        return match.group(1), match.group(2), int(match.group(3))
    return None


class GitHubPRAgent(BaseAgent):
    """
    Automates the PR lifecycle:
      - PR description generation
      - Risk assessment
      - Automated review comments
      - Merge readiness check
    """

    name = "github_pr"
    skills = ["pr_automation", "pr_description", "pr_review"]

    # Optional MCPClient, injected by the orchestrator when CODEOPS_MCP is on.
    # When present, PR reviews call GitHub tools over the MCP boundary; when
    # None, they use the in-process connector directly.
    mcp: Any = None
    system_prompt = """\
You are a senior software engineer specializing in code review and pull request best practices.
Your role is to automate the PR workflow to reduce bottlenecks on human reviewers.

When given a code diff or PR content, output a JSON object:
{
  "pr_title": "<concise, imperative-mood title>",
  "pr_description": {
    "summary": "<1-2 sentence overview of what changed and why>",
    "changes": ["<bullet: specific change 1>", "<bullet: specific change 2>"],
    "testing": ["<how to test this change>"],
    "screenshots": "<N/A or describe what to screenshot>",
    "breaking_changes": "<none | describe breaking changes>"
  },
  "risk_assessment": {
    "level": "low|medium|high|critical",
    "reasons": ["<risk factor 1>"],
    "areas_needing_careful_review": ["<file or area>"]
  },
  "automated_review_comments": [
    {
      "file": "<filename>",
      "line_hint": "<function or line context>",
      "severity": "blocker|warning|suggestion|nitpick",
      "comment": "<specific, actionable review comment>",
      "suggested_fix": "<code snippet or approach>"
    }
  ],
  "merge_readiness": {
    "ready": true|false,
    "blockers": ["<what must be fixed before merge>"],
    "score": <1-10>
  },
  "suggested_labels": ["<github label>"],
  "estimated_review_time": "<5 min|15 min|30 min|1 hour>"
}

Rules:
- Be specific and actionable — vague comments waste reviewers' time.
- Flag security issues (injection, exposed secrets, auth bypasses) as blockers.
- Missing tests on business logic → blocker.
- Output ONLY the JSON, nothing else.
"""

    def execute(self, task: str, context: ContextManager) -> AgentResult:
        self.logger.info("Running PR automation for task: %s", task[:80])

        # Pre-flight safety gate — refuse destructive/exfiltration requests and
        # escalate privilege-bypass requests before any tool or model runs.
        plan = plan_tools(task)
        if plan.action in ("refuse", "escalate"):
            self.logger.warning("Guardrail %s: %s", plan.action, plan.reason)
            return AgentResult(
                agent_name=self.name,
                skill="pr_automation",
                output=f"{plan.action.capitalize()}d — {plan.reason}.",
                status="error" if plan.action == "refuse" else "needs_revision",
                next_action="abort" if plan.action == "refuse" else "escalate",
                metadata={"guardrail": plan.action, "reason": plan.reason},
            )

        # Real-PR path: if the task names a GitHub PR and we can reach the API,
        # let the model read the PR itself via GitHub tool calls.
        pr_ref = _extract_pr_ref(task)
        if pr_ref and not self._demo_mode and self._client is not None:
            try:
                return self._review_pr_with_tools(task, pr_ref, context)
            except Exception as exc:  # noqa: BLE001 — fall back to the text path
                self.logger.error("Tool-based PR review failed: %s", exc, exc_info=True)

        # Pull code from context if a coder has already run, otherwise use task directly
        code = context.get_agent_output("code_generation") or task

        messages = [
            {
                "role": "user",
                "content": (
                    f"Analyze this pull request and generate the full PR automation output:\n\n"
                    f"{code[:8000]}"
                ),
            }
        ]

        try:
            raw = self._call_llm(messages)
            pr_data = self._parse_json(raw)

            # Format a human-readable output
            output = self._format_pr_output(pr_data)

            result = AgentResult(
                agent_name=self.name,
                skill="pr_automation",
                output=output,
                status="success",
                next_action="done",
                metadata={
                    "risk_level": pr_data.get("risk_assessment", {}).get("level", "unknown"),
                    "merge_ready": pr_data.get("merge_readiness", {}).get("ready", False),
                    "merge_score": pr_data.get("merge_readiness", {}).get("score", 0),
                    "review_comments": len(pr_data.get("automated_review_comments", [])),
                    "raw": pr_data,
                },
            )
            self._persist_result(result, context)
            return result

        except Exception as exc:
            self.logger.error("GitHubPRAgent failed: %s", exc, exc_info=True)
            return AgentResult(
                agent_name=self.name,
                skill="pr_automation",
                output=f"PR automation failed: {exc}",
                status="error",
                next_action="abort",
            )

    def _review_pr_with_tools(
        self, task: str, pr_ref: tuple[str, str, int], context: ContextManager
    ) -> AgentResult:
        """Review a real PR by letting the model call the GitHub read tools."""
        from codeops.mcp.connectors import GitHubConnector
        from codeops.mcp.tools import GITHUB_TOOLS, build_github_dispatch

        owner, repo, number = pr_ref

        # Source the tools + dispatch from MCP (federated, over the protocol
        # boundary) if a client is wired in; otherwise call the connector
        # directly in-process.
        if self.mcp is not None:
            tools = self.mcp.registry.anthropic_tools()
            dispatch = self.mcp.dispatch()
            transport = "mcp"
        else:
            tools = GITHUB_TOOLS
            dispatch = build_github_dispatch(GitHubConnector())
            transport = "in_process"

        prompt = (
            f"Review pull request #{number} in the repository {owner}/{repo}.\n\n"
            f"First call get_pull_request to read its metadata and diff, and "
            f"get_pr_files to see the changed files. Use get_file_content or "
            f"get_pr_comments if you need more context. Then produce the PR "
            f"automation JSON exactly as specified in your instructions.\n\n"
            f"Original request:\n{task}"
        )
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]

        final_text, tool_calls = self._run_tool_loop(
            messages, tools, dispatch, system=self.system_prompt
        )
        tools_used = sorted({c["name"] for c in tool_calls})

        # The model was asked for the PR-automation JSON; render it if parseable,
        # otherwise fall back to whatever text it produced.
        try:
            pr_data = self._parse_json(final_text)
            output = self._format_pr_output(pr_data)
            meta_extra = {
                "risk_level": pr_data.get("risk_assessment", {}).get("level", "unknown"),
                "merge_ready": pr_data.get("merge_readiness", {}).get("ready", False),
                "review_comments": len(pr_data.get("automated_review_comments", [])),
                "raw": pr_data,
            }
        except Exception:
            output = final_text
            meta_extra = {}

        result = AgentResult(
            agent_name=self.name,
            skill="pr_automation",
            output=output,
            status="success",
            next_action="done",
            metadata={
                "pr": f"{owner}/{repo}#{number}",
                "transport": transport,
                "tools_used": tools_used,
                "tool_calls": tool_calls,
                **meta_extra,
            },
        )
        self._persist_result(result, context)
        return result

    def _parse_json(self, raw: str) -> dict[str, Any]:
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON in PR agent response")
        return json.loads(cleaned[start:end])

    @staticmethod
    def _format_pr_output(pr: dict[str, Any]) -> str:
        lines: list[str] = []

        # Title
        title = pr.get("pr_title", "")
        lines.append(f"## {title}\n")

        # Description
        desc = pr.get("pr_description", {})
        lines.append(f"### Summary\n{desc.get('summary', '')}\n")

        changes = desc.get("changes", [])
        if changes:
            lines.append("### Changes")
            for c in changes:
                lines.append(f"- {c}")
            lines.append("")

        testing = desc.get("testing", [])
        if testing:
            lines.append("### Testing")
            for t in testing:
                lines.append(f"- {t}")
            lines.append("")

        breaking = desc.get("breaking_changes", "none")
        if breaking and breaking.lower() != "none":
            lines.append(f"### ⚠️ Breaking Changes\n{breaking}\n")

        # Risk
        risk = pr.get("risk_assessment", {})
        risk_level = risk.get("level", "unknown").upper()
        risk_emoji = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🔴", "CRITICAL": "🚨"}.get(risk_level, "⚪")
        lines.append(f"### Risk: {risk_emoji} {risk_level}")
        for r in risk.get("reasons", []):
            lines.append(f"- {r}")
        lines.append("")

        # Review comments
        comments = pr.get("automated_review_comments", [])
        if comments:
            lines.append("### Automated Review Comments")
            for c in comments:
                sev = c.get("severity", "?").upper()
                sev_emoji = {"BLOCKER": "🚫", "WARNING": "⚠️", "SUGGESTION": "💡", "NITPICK": "📝"}.get(sev, "•")
                lines.append(f"\n**{sev_emoji} [{sev}]** `{c.get('file', '?')}` — {c.get('line_hint', '')}")
                lines.append(f"> {c.get('comment', '')}")
                fix = c.get("suggested_fix", "")
                if fix:
                    lines.append(f"```\n{fix}\n```")
            lines.append("")

        # Merge readiness
        merge = pr.get("merge_readiness", {})
        score = merge.get("score", "?")
        ready = merge.get("ready", False)
        ready_str = "✅ Ready to merge" if ready else "❌ Not ready"
        lines.append(f"### Merge Readiness: {ready_str} (score {score}/10)")
        for b in merge.get("blockers", []):
            lines.append(f"- 🚫 {b}")

        labels = pr.get("suggested_labels", [])
        if labels:
            lines.append(f"\n**Labels:** {', '.join(f'`{l}`' for l in labels)}")

        eta = pr.get("estimated_review_time", "")
        if eta:
            lines.append(f"**Estimated review time:** {eta}")

        return "\n".join(lines)
