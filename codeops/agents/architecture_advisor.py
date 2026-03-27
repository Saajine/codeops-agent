"""
ArchitectureAdvisorAgent — reviews system design specs and existing code
to recommend architectural patterns, identify anti-patterns, and generate
implementation guidance.

Maps to enterprise use case: "Architecture & infrastructure maintenance — guided,
repeatable workflows so mid-level engineers can maintain systems confidently."
"""

from __future__ import annotations

import json
import re
from typing import Any

from codeops.agents.base_agent import AgentResult, BaseAgent
from codeops.memory.context import ContextManager


class ArchitectureAdvisorAgent(BaseAgent):
    """
    Reviews system design and recommends:
      - Architecture patterns suited to the use case
      - Anti-patterns to avoid
      - Scalability and reliability considerations
      - Implementation roadmap with skill requirements
      - Trade-offs between options
    """

    name = "architecture_advisor"
    skills = ["architecture_review", "system_design", "tech_selection"]
    system_prompt = """\
You are a principal software architect with 15+ years of experience designing
distributed systems, APIs, microservices, and cloud-native applications.

When given a system design request, problem description, or existing codebase,
output a single JSON object:
{
  "assessment": {
    "summary": "<2-3 sentence overview>",
    "current_state": "<what exists now, or 'greenfield' if starting fresh>",
    "core_challenge": "<the main technical challenge to solve>"
  },
  "recommended_architecture": {
    "pattern": "<e.g. Event-driven microservices, CQRS, Hexagonal, Monolith-first>",
    "rationale": "<why this pattern fits the requirements>",
    "components": [
      {
        "name": "<component name>",
        "responsibility": "<single responsibility>",
        "technology": "<specific tech recommendation>",
        "rationale": "<why this tech>"
      }
    ],
    "data_flow": "<describe how data moves through the system>",
    "diagram_description": "<text description of the architecture diagram>"
  },
  "alternative_architectures": [
    {
      "pattern": "<alternative>",
      "when_to_use": "<conditions where this is better>",
      "trade_offs": "<pros and cons>"
    }
  ],
  "anti_patterns_detected": [
    {
      "pattern": "<anti-pattern name>",
      "location": "<where it exists>",
      "impact": "<performance|security|maintainability|scalability>",
      "fix": "<specific remediation>"
    }
  ],
  "scalability_plan": {
    "bottlenecks": ["<identified bottleneck>"],
    "horizontal_scaling": "<how to scale horizontally>",
    "caching_strategy": "<what to cache and where>",
    "estimated_capacity": "<rough capacity at recommended architecture>"
  },
  "implementation_roadmap": [
    {
      "phase": 1,
      "title": "<phase name>",
      "duration": "<estimate>",
      "deliverables": ["<concrete deliverable>"],
      "skills_required": ["<skill>"],
      "risks": ["<risk>"]
    }
  ],
  "security_considerations": ["<security recommendation>"],
  "observability_recommendations": ["<logging/metrics/tracing recommendation>"],
  "confidence": "<high|medium|low>",
  "open_questions": ["<question that needs answering before full design>"]
}

Output ONLY the JSON object, nothing else.
"""

    def execute(self, task: str, context: ContextManager) -> AgentResult:
        self.logger.info("Architecture review: %s", task[:80])

        # Include any existing code or plan context
        extra_context = ""
        plan = context.plan
        if plan:
            extra_context += f"\n\nExisting execution plan context:\n{json.dumps(plan, indent=2)[:2000]}"

        code = context.get_agent_output("code_generation")
        if code:
            extra_context += f"\n\nExisting codebase:\n{code[:3000]}"

        messages = [
            {
                "role": "user",
                "content": (
                    f"Provide a comprehensive architecture review and recommendation for:\n\n"
                    f"{task}{extra_context}"
                ),
            }
        ]

        try:
            raw = self._call_llm(messages)
            arch_data = self._parse_json(raw)
            output = self._format_architecture_report(arch_data)

            result = AgentResult(
                agent_name=self.name,
                skill="architecture_review",
                output=output,
                status="success",
                next_action="done",
                metadata={
                    "pattern": arch_data.get("recommended_architecture", {}).get("pattern", ""),
                    "anti_patterns": len(arch_data.get("anti_patterns_detected", [])),
                    "phases": len(arch_data.get("implementation_roadmap", [])),
                    "confidence": arch_data.get("confidence", "unknown"),
                    "raw": arch_data,
                },
            )
            self._persist_result(result, context)
            return result

        except Exception as exc:
            self.logger.error("ArchitectureAdvisorAgent failed: %s", exc, exc_info=True)
            return AgentResult(
                agent_name=self.name,
                skill="architecture_review",
                output=f"Architecture review failed: {exc}",
                status="error",
                next_action="abort",
            )

    def _parse_json(self, raw: str) -> dict[str, Any]:
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON in architecture advisor response")
        return json.loads(cleaned[start:end])

    @staticmethod
    def _format_architecture_report(data: dict[str, Any]) -> str:
        lines: list[str] = ["# Architecture Review Report\n"]

        # Assessment
        assessment = data.get("assessment", {})
        lines.append(f"## Summary\n{assessment.get('summary', '')}")
        lines.append(f"\n**Core Challenge:** {assessment.get('core_challenge', '')}\n")

        # Recommended architecture
        arch = data.get("recommended_architecture", {})
        lines.append(f"## Recommended Architecture: {arch.get('pattern', '')}")
        lines.append(f"\n{arch.get('rationale', '')}\n")

        components = arch.get("components", [])
        if components:
            lines.append("### Components")
            for comp in components:
                lines.append(
                    f"- **{comp.get('name', '')}** (`{comp.get('technology', '')}`): "
                    f"{comp.get('responsibility', '')} — *{comp.get('rationale', '')}*"
                )
            lines.append("")

        data_flow = arch.get("data_flow", "")
        if data_flow:
            lines.append(f"### Data Flow\n{data_flow}\n")

        # Anti-patterns
        anti = data.get("anti_patterns_detected", [])
        if anti:
            lines.append("## ⚠️ Anti-Patterns Detected")
            for a in anti:
                lines.append(
                    f"- **{a.get('pattern', '')}** [{a.get('impact', '').upper()}] "
                    f"@ `{a.get('location', '')}`: {a.get('fix', '')}"
                )
            lines.append("")

        # Scalability
        scale = data.get("scalability_plan", {})
        if scale:
            lines.append("## Scalability Plan")
            bottlenecks = scale.get("bottlenecks", [])
            if bottlenecks:
                lines.append("**Bottlenecks:** " + ", ".join(bottlenecks))
            lines.append(f"**Caching:** {scale.get('caching_strategy', 'N/A')}")
            lines.append(f"**Capacity:** {scale.get('estimated_capacity', 'N/A')}\n")

        # Roadmap
        roadmap = data.get("implementation_roadmap", [])
        if roadmap:
            lines.append("## Implementation Roadmap")
            for phase in roadmap:
                lines.append(
                    f"\n### Phase {phase.get('phase', '?')}: {phase.get('title', '')} "
                    f"({phase.get('duration', '?')})"
                )
                for d in phase.get("deliverables", []):
                    lines.append(f"- {d}")

        # Security
        security = data.get("security_considerations", [])
        if security:
            lines.append("\n## Security")
            for s in security:
                lines.append(f"- {s}")

        # Open questions
        questions = data.get("open_questions", [])
        if questions:
            lines.append("\n## Open Questions")
            for q in questions:
                lines.append(f"- {q}")

        confidence = data.get("confidence", "")
        if confidence:
            lines.append(f"\n**Confidence:** {confidence.upper()}")

        return "\n".join(lines)
