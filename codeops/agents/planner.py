"""
PlannerAgent — breaks a high-level task into a structured, dependency-aware
execution plan that the orchestrator can route step-by-step to specialised agents.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from codeops.agents.base_agent import AgentResult, BaseAgent
from codeops.memory.context import ContextManager

logger = logging.getLogger(__name__)


class PlannerAgent(BaseAgent):
    """
    Analyses a task description and returns a JSON execution plan with:
      - title        : short summary of the work
      - description  : detailed explanation
      - steps        : ordered list of sub-tasks, each with
                         id, title, description, skill, depends_on[]
      - estimated_complexity : "low" | "medium" | "high"
    """

    name = "planner"
    skills = ["task_planning"]
    system_prompt = """\
You are an expert software engineering planner and technical architect.
Your role is to analyse tasks, GitHub issues, or feature requests and produce
a clear, actionable execution plan.

When given a task you will output a single JSON object (no markdown fences) with:
{
  "title": "<short task title>",
  "description": "<detailed analysis>",
  "estimated_complexity": "low|medium|high",
  "steps": [
    {
      "id": 1,
      "title": "<step title>",
      "description": "<what needs to be done in detail>",
      "skill": "<skill name: task_planning|code_generation|code_review|test_generation|doc_generation>",
      "depends_on": [],
      "acceptance_criteria": "<how to know this step is complete>"
    }
  ],
  "risks": ["<risk 1>", "<risk 2>"],
  "tech_stack": ["<language or framework>"]
}

Rules:
- Always include at least one code_generation step and one code_review step.
- List dependencies accurately so the orchestrator can parallelise work.
- Be specific in descriptions — the downstream agent reads these directly.
- Output ONLY the JSON object, nothing else.
"""

    # ── Execute ───────────────────────────────────────────────────────────────

    def execute(self, task: str, context: ContextManager) -> AgentResult:
        self.logger.info("Planning task: %s", task[:80])

        # Build message including any prior context (e.g. from a previous iteration)
        messages = self._build_messages(task, context)

        try:
            raw = self._call_llm(messages)
            plan = self._parse_plan(raw)
            context.set_plan(plan)
            self.store.save_plan(context.task_id, plan)

            result = AgentResult(
                agent_name=self.name,
                skill="task_planning",
                output=json.dumps(plan, indent=2),
                status="success",
                next_action="execute_plan",
                metadata={"steps": len(plan.get("steps", []))},
            )
            self._persist_result(result, context)
            return result

        except Exception as exc:
            self.logger.error("Planner failed: %s", exc, exc_info=True)
            return AgentResult(
                agent_name=self.name,
                skill="task_planning",
                output=f"Planning failed: {exc}",
                status="error",
                next_action="abort",
            )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _build_messages(self, task: str, context: ContextManager) -> list[dict[str, Any]]:
        content = f"Please create an execution plan for the following task:\n\n{task}"

        # If we have previous outputs in context (e.g. re-planning after review)
        prior = context.get_agent_output("task_planning")
        if prior and context.iteration > 0:
            content += (
                f"\n\nNote: A previous plan was attempted. "
                f"Review feedback is: {context.get_agent_output('code_review') or 'N/A'}. "
                f"Please update the plan accordingly."
            )

        return [{"role": "user", "content": content}]

    def _parse_plan(self, raw: str) -> dict[str, Any]:
        """Extract JSON from the LLM response robustly."""
        # Strip any accidental markdown fences
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()

        # Find the outermost JSON object
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON object found in planner response.")

        plan = json.loads(cleaned[start:end])

        # Normalise
        if "steps" not in plan:
            plan["steps"] = []
        for i, step in enumerate(plan["steps"], 1):
            step.setdefault("id", i)
            step.setdefault("depends_on", [])
            step.setdefault("skill", "code_generation")
            step.setdefault("acceptance_criteria", "")

        return plan
