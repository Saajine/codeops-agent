"""
ReviewerAgent — evaluates code output from the CoderAgent, returns structured
feedback, and signals whether a self-correction loop is needed.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from codeops.agents.base_agent import AgentResult, BaseAgent
from codeops.memory.context import ContextManager

logger = logging.getLogger(__name__)


class ReviewerAgent(BaseAgent):
    """
    Reviews code for:
      - Correctness (logic errors, edge cases)
      - Code quality (readability, naming, structure)
      - Security (injection, auth issues, secrets in code)
      - Performance (obvious O(n²), unnecessary DB calls, etc.)
      - Style (PEP 8, type annotations, docstrings)

    Returns a verdict: "approved" | "needs_revision" and structured feedback.
    """

    name = "reviewer"
    skills = ["code_review"]
    system_prompt = """\
You are a senior code reviewer at a top-tier software company.
Your job is to review code thoroughly and provide actionable, constructive feedback.

For every review, output a single JSON object (no markdown fences):
{
  "verdict": "approved" | "needs_revision",
  "score": <integer 1-10>,
  "summary": "<one-sentence overall assessment>",
  "issues": [
    {
      "severity": "critical" | "major" | "minor" | "suggestion",
      "category": "correctness" | "security" | "performance" | "style" | "maintainability",
      "description": "<clear description of the issue>",
      "location": "<file:line or function name if known>",
      "fix": "<specific fix or recommendation>"
    }
  ],
  "strengths": ["<what the code does well>"],
  "required_changes": ["<must-fix items before approval>"],
  "suggested_changes": ["<nice-to-have improvements>"]
}

Rules:
- verdict is "approved" only when score >= 7 AND there are no critical/major issues.
- Be specific — vague feedback like "improve this" is not helpful.
- Always acknowledge strengths to make feedback balanced.
- Output ONLY the JSON, nothing else.
"""

    # ── Execute ───────────────────────────────────────────────────────────────

    def execute(self, task: str, context: ContextManager) -> AgentResult:
        self.logger.info("Reviewing code (iter %d)", context.iteration)
        self._iteration = context.iteration

        code_output = context.get_agent_output("code_generation")
        if not code_output:
            return AgentResult(
                agent_name=self.name,
                skill="code_review",
                output="No code found to review.",
                status="error",
                next_action="abort",
            )

        messages = self._build_messages(task, code_output, context)

        try:
            raw = self._call_llm(messages)
            review = self._parse_review(raw)

            verdict = review.get("verdict", "needs_revision")
            score = review.get("score", 0)
            issues = review.get("issues", [])
            critical_count = sum(1 for i in issues if i.get("severity") == "critical")
            major_count = sum(1 for i in issues if i.get("severity") == "major")

            # Determine action for orchestrator
            if verdict == "approved":
                status = "success"
                next_action = "done"
            else:
                status = "needs_revision"
                next_action = "revise_code"

            feedback = self._format_feedback(review)

            result = AgentResult(
                agent_name=self.name,
                skill="code_review",
                output=feedback,
                status=status,
                feedback=feedback,
                next_action=next_action,
                metadata={
                    "verdict": verdict,
                    "score": score,
                    "critical_issues": critical_count,
                    "major_issues": major_count,
                    "total_issues": len(issues),
                    "iteration": context.iteration,
                    "raw_review": review,
                },
            )
            self._persist_result(result, context, iteration=context.iteration)
            return result

        except Exception as exc:
            self.logger.error("Reviewer failed: %s", exc, exc_info=True)
            return AgentResult(
                agent_name=self.name,
                skill="code_review",
                output=f"Review failed: {exc}",
                status="error",
                next_action="abort",
            )

    # ── Message builder ───────────────────────────────────────────────────────

    def _build_messages(
        self, task: str, code_output: str, context: ContextManager
    ) -> list[dict[str, Any]]:
        plan = context.plan
        plan_summary = ""
        if plan:
            plan_summary = (
                f"## Original Task Plan\n"
                f"Title: {plan.get('title', 'N/A')}\n"
                f"Description: {plan.get('description', '')[:300]}\n"
            )

        history = ""
        if context.iteration > 0:
            history = (
                f"\nNote: This is review iteration #{context.iteration + 1}. "
                f"Previous issues should have been addressed."
            )

        content = (
            f"## Task\n{task}\n\n"
            f"{plan_summary}\n"
            f"## Code to Review\n{code_output}\n"
            f"{history}"
        )
        return [{"role": "user", "content": content}]

    # ── Output helpers ────────────────────────────────────────────────────────

    def _parse_review(self, raw: str) -> dict[str, Any]:
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON object in reviewer response.")
        return json.loads(cleaned[start:end])

    @staticmethod
    def _format_feedback(review: dict[str, Any]) -> str:
        """Convert structured review JSON to readable feedback for the coder."""
        lines = [
            f"## Code Review — {review.get('verdict', 'N/A').upper()}",
            f"Score: {review.get('score', '?')}/10",
            f"Summary: {review.get('summary', '')}",
            "",
        ]

        issues = review.get("issues", [])
        if issues:
            lines.append("### Issues Found")
            for issue in issues:
                sev = issue.get("severity", "?").upper()
                cat = issue.get("category", "?")
                desc = issue.get("description", "")
                loc = issue.get("location", "")
                fix = issue.get("fix", "")
                loc_str = f" @ `{loc}`" if loc else ""
                lines.append(f"- **[{sev}/{cat}]**{loc_str}: {desc}")
                if fix:
                    lines.append(f"  → Fix: {fix}")
            lines.append("")

        required = review.get("required_changes", [])
        if required:
            lines.append("### Required Changes (must fix before approval)")
            for r in required:
                lines.append(f"- {r}")
            lines.append("")

        strengths = review.get("strengths", [])
        if strengths:
            lines.append("### Strengths")
            for s in strengths:
                lines.append(f"- {s}")

        return "\n".join(lines)
