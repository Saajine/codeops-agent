"""
TestGeneratorAgent — auto-generates test suites from code.

Given code (from context) or a task description, produces a pytest-based
test suite covering happy paths, edge cases, and concurrency.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from codeops.agents.base_agent import AgentResult, BaseAgent
from codeops.memory.context import ContextManager

logger = logging.getLogger(__name__)


class TestGeneratorAgent(BaseAgent):
    """
    Generates comprehensive test suites from code artifacts in context.
    Reads code_generation output and produces pytest test files.
    """

    name = "tester"
    skills = ["test_generation"]
    system_prompt = """\
You are a senior QA engineer specialising in automated testing. You write
thorough, well-structured pytest test suites.

When asked to generate tests you will:
1. Analyse the code under test for all public APIs.
2. Write tests covering: happy paths, edge cases, error handling, and concurrency.
3. Use pytest fixtures, parametrize where appropriate.
4. Mock external dependencies (network, filesystem, databases).
5. Aim for >= 85% branch coverage.
6. Include clear docstrings and descriptive test names.

Format your output as:
---FILE: <relative/path/to/test_file.py>---
<full test file content>
---END---

After the test file(s), include a JSON summary block:
```json
{
    "test_file": "<path>",
    "test_count": <int>,
    "coverage_estimate": "<percent>",
    "categories": ["<category>", ...],
    "framework": "pytest"
}
```
"""

    # ── Execute ───────────────────────────────────────────────────────────────

    def execute(self, task: str, context: ContextManager) -> AgentResult:
        self.logger.info("Generating tests: %s", task[:80])
        self._iteration = context.iteration

        # Read code from context if available
        code = context.get_agent_output("code_generation")
        if not code:
            code = task  # Fall back to treating the task as code

        messages = self._build_messages(task, code, context)

        try:
            raw = self._call_llm(messages)
            test_files = self._parse_files(raw)
            summary = self._parse_summary(raw)

            # Persist test artifacts
            for fpath, content in test_files.items():
                self.store.save_code_artifact(
                    context.task_id, fpath, content, "python"
                )

            result = AgentResult(
                agent_name=self.name,
                skill="test_generation",
                output=raw,
                status="success",
                next_action="done",
                metadata={
                    "test_files": list(test_files.keys()),
                    "test_count": summary.get("test_count", len(test_files)),
                    "coverage_estimate": summary.get("coverage_estimate", "unknown"),
                },
            )
            self._persist_result(result, context)
            return result

        except Exception as exc:
            self.logger.error("Test generation failed: %s", exc, exc_info=True)
            return AgentResult(
                agent_name=self.name,
                skill="test_generation",
                output=f"Test generation failed: {exc}",
                status="error",
                next_action="abort",
            )

    # ── Message builder ───────────────────────────────────────────────────────

    def _build_messages(
        self, task: str, code: str, context: ContextManager
    ) -> list[dict[str, Any]]:
        parts: list[str] = []

        parts.append(f"## Task\n{task}")

        if code and code != task:
            preview = code[:4000] + ("…" if len(code) > 4000 else "")
            parts.append(f"## Code Under Test\n```\n{preview}\n```")

        plan = context.plan
        if plan:
            parts.append(
                f"## Context\nProject: {plan.get('title', 'unknown')}\n"
                f"Tech stack: {', '.join(plan.get('tech_stack', []))}"
            )

        return [{"role": "user", "content": "\n\n".join(parts)}]

    # ── Output parsers ────────────────────────────────────────────────────────

    def _parse_files(self, raw: str) -> dict[str, str]:
        files: dict[str, str] = {}
        pattern = re.compile(
            r"---FILE:\s*(.+?)---\s*(.*?)---END---",
            re.DOTALL | re.IGNORECASE,
        )
        for match in pattern.finditer(raw):
            path = match.group(1).strip()
            content = match.group(2).strip()
            files[path] = content

        if not files and raw.strip():
            files["tests/test_generated.py"] = raw.strip()

        return files

    @staticmethod
    def _parse_summary(raw: str) -> dict[str, Any]:
        pattern = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)
        match = pattern.search(raw)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        return {}
