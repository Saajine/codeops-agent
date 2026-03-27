"""
BaseAgent — abstract base class for all CodeOps agents.

Every agent:
  1. Has a name and a list of skills it handles.
  2. Has a system prompt that shapes its persona/behaviour.
  3. Implements execute(task, context) → AgentResult.
  4. Uses the Anthropic API (claude-opus-4-6) with streaming for long outputs.
  5. Reads from / writes to the shared ContextManager.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import anthropic

from codeops.config import config
from codeops.demo import demo_llm_response
from codeops.memory.context import ContextManager
from codeops.memory.store import MemoryStore

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    """Structured return value from every agent execution."""

    agent_name: str
    skill: str
    output: str                       # Primary text/code output
    status: str                       # "success" | "needs_revision" | "error"
    feedback: str = ""                # Reviewer feedback (for self-correction loops)
    next_action: str = ""             # Hint to the orchestrator ("review", "code", "done")
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.status == "success"

    def __str__(self) -> str:
        return (
            f"[{self.agent_name}] skill={self.skill} status={self.status}\n"
            f"{self.output[:300]}{'...' if len(self.output) > 300 else ''}"
        )


class BaseAgent(ABC):
    """
    Abstract base agent.  Subclasses must implement:
      - name   (class attribute)
      - skills (class attribute)
      - system_prompt (class attribute)
      - execute(task, context) → AgentResult
    """

    name: str = "base"
    skills: list[str] = []
    system_prompt: str = "You are a helpful software engineering agent."

    def __init__(
        self,
        store: MemoryStore | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> None:
        self.store = store or MemoryStore()
        self.model = model or config.MODEL
        self.max_tokens = max_tokens or config.MAX_TOKENS
        self._demo_mode = config.DEMO_MODE
        self._client: anthropic.Anthropic | None = None
        if not self._demo_mode:
            self._client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self.logger = logging.getLogger(f"codeops.agent.{self.name}")
        self._iteration = 0  # tracked for demo mode

    # ── Abstract interface ────────────────────────────────────────────────────

    @abstractmethod
    def execute(self, task: str, context: ContextManager) -> AgentResult:
        """
        Execute the agent's primary skill against *task*.

        Args:
            task   : the specific sub-task or instruction for this agent.
            context: shared state; read previous outputs, write new results.

        Returns:
            AgentResult with output, status, and optional routing hint.
        """

    # ── LLM helpers ──────────────────────────────────────────────────────────

    def _call_llm(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        use_streaming: bool = True,
    ) -> str:
        """
        Call the Anthropic API.  Uses streaming for long responses to avoid
        HTTP timeouts, then reassembles into a single string.

        In demo mode, returns realistic mock responses instead.
        """
        # Demo mode — return realistic mocks without hitting the API
        if self._demo_mode:
            task_text = ""
            for msg in messages:
                if msg.get("role") == "user":
                    task_text = msg.get("content", "")[:500]
                    break
            return demo_llm_response(self.name, task_text, self._iteration)

        sys_prompt = system or self.system_prompt
        kwargs: dict[str, Any] = dict(
            model=self.model,
            max_tokens=self.max_tokens,
            system=sys_prompt,
            messages=messages,
            thinking={"type": "adaptive"},
        )

        if use_streaming:
            return self._call_llm_streaming(**kwargs)
        else:
            response = self._client.messages.create(**kwargs)
            return self._extract_text(response.content)

    def _call_llm_streaming(self, **kwargs: Any) -> str:
        """Stream the response and reassemble, ignoring thinking blocks."""
        if self._client is None:
            raise RuntimeError("Anthropic client not initialized — set API key or use demo mode.")
        full_text = ""
        with self._client.messages.stream(**kwargs) as stream:
            for event in stream:
                if event.type == "content_block_delta":
                    if hasattr(event.delta, "text"):
                        full_text += event.delta.text
        return full_text

    @staticmethod
    def _extract_text(content: list[Any]) -> str:
        """Extract text blocks from a message response."""
        return "\n".join(
            block.text for block in content if block.type == "text"
        )

    # ── Persistence helpers ───────────────────────────────────────────────────

    def _persist_result(self, result: AgentResult, context: ContextManager, iteration: int = 0) -> None:
        """Write result to the memory store and update shared context."""
        context.set_agent_output(result.skill, result.output, agent_name=self.name)
        self.store.save_agent_output(
            task_id=context.task_id,
            agent_name=self.name,
            skill=result.skill,
            output=result.output,
            status=result.status,
            iteration=iteration,
        )

    # ── Utility ───────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} skills={self.skills}>"
