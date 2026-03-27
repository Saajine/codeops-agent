"""
CoderAgent — generates or modifies code based on a plan step or direct instruction.

Supports both:
  - Step-based mode: given a plan step dict, implements it.
  - Free-form mode : given a plain-text instruction, generates code.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from codeops.agents.base_agent import AgentResult, BaseAgent
from codeops.memory.context import ContextManager

logger = logging.getLogger(__name__)

# Languages we can auto-detect from content
_LANG_PATTERNS: list[tuple[str, str]] = [
    (r"\bdef \w+\(", "python"),
    (r"\bimport\s+\w+", "python"),
    (r"\bfunction\s+\w+\s*\(", "javascript"),
    (r"const\s+\w+\s*=", "typescript"),
    (r"^package\s+\w+", "go"),
    (r"public\s+class\s+\w+", "java"),
]


class CoderAgent(BaseAgent):
    """
    Generates production-quality code from a specification.
    Respects reviewer feedback when context.iteration > 0.
    """

    name = "coder"
    skills = ["code_generation"]
    system_prompt = """\
You are a senior software engineer with expertise across Python, TypeScript,
Go, Java, and SQL. You write clean, typed, well-documented, production-ready code.

When asked to implement something you will:
1. Think through the design carefully.
2. Write complete, working code (not pseudocode or stubs).
3. Include type annotations and docstrings.
4. Add inline comments for non-obvious logic.
5. Handle errors gracefully.
6. Follow the principle of least surprise.

Format your output as:
---FILE: <relative/path/to/file.ext>---
<full file content>
---END---

If multiple files are needed, repeat the block for each file.
After all files, include a brief "## Implementation Notes" section.
"""

    # ── Execute ───────────────────────────────────────────────────────────────

    def execute(self, task: str, context: ContextManager) -> AgentResult:
        self.logger.info("Coding task (iter %d): %s", context.iteration, task[:80])
        self._iteration = context.iteration

        messages = self._build_messages(task, context)

        try:
            raw = self._call_llm(messages)
            files = self._parse_files(raw)

            # Persist code artifacts
            for fpath, content in files.items():
                lang = self._detect_language(fpath, content)
                self.store.save_code_artifact(context.task_id, fpath, content, lang)

            result = AgentResult(
                agent_name=self.name,
                skill="code_generation",
                output=raw,
                status="success",
                next_action="review",
                metadata={
                    "files_generated": list(files.keys()),
                    "iteration": context.iteration,
                },
            )
            self._persist_result(result, context, iteration=context.iteration)
            return result

        except Exception as exc:
            self.logger.error("Coder failed: %s", exc, exc_info=True)
            return AgentResult(
                agent_name=self.name,
                skill="code_generation",
                output=f"Code generation failed: {exc}",
                status="error",
                next_action="abort",
            )

    # ── Message builder ───────────────────────────────────────────────────────

    def _build_messages(self, task: str, context: ContextManager) -> list[dict[str, Any]]:
        parts: list[str] = []

        # Include the execution plan if available
        plan = context.plan
        if plan:
            parts.append(f"## Execution Plan\n```json\n{json.dumps(plan, indent=2)}\n```")

        parts.append(f"## Current Task\n{task}")

        # Self-correction: include reviewer feedback if this is a retry
        if context.iteration > 0:
            review_output = context.get_agent_output("code_review")
            if review_output:
                parts.append(
                    f"## Reviewer Feedback (Iteration {context.iteration})\n"
                    f"The previous code submission had the following issues:\n\n"
                    f"{review_output}\n\n"
                    f"Please address all feedback points in your revised implementation."
                )
            prev_code = context.get_agent_output("code_generation")
            if prev_code:
                # Summarise previous attempt to keep context lean
                preview = prev_code[:2000] + ("…" if len(prev_code) > 2000 else "")
                parts.append(f"## Previous Code (to improve)\n{preview}")

        return [{"role": "user", "content": "\n\n".join(parts)}]

    # ── Output parsers ────────────────────────────────────────────────────────

    def _parse_files(self, raw: str) -> dict[str, str]:
        """Extract FILE blocks from the LLM response."""
        files: dict[str, str] = {}
        pattern = re.compile(
            r"---FILE:\s*(.+?)---\s*(.*?)---END---",
            re.DOTALL | re.IGNORECASE,
        )
        for match in pattern.finditer(raw):
            path = match.group(1).strip()
            content = match.group(2).strip()
            files[path] = content

        # Fallback: treat the entire output as a single file if no blocks found
        if not files and raw.strip():
            files["generated_code.py"] = raw.strip()

        return files

    @staticmethod
    def _detect_language(file_path: str, content: str) -> str:
        ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
        ext_map = {
            "py": "python", "ts": "typescript", "tsx": "typescript",
            "js": "javascript", "jsx": "javascript", "go": "go",
            "java": "java", "rs": "rust", "rb": "ruby", "sql": "sql",
            "sh": "bash", "yaml": "yaml", "yml": "yaml", "json": "json",
            "md": "markdown",
        }
        if ext in ext_map:
            return ext_map[ext]
        for pattern, lang in _LANG_PATTERNS:
            if re.search(pattern, content, re.MULTILINE):
                return lang
        return "unknown"
