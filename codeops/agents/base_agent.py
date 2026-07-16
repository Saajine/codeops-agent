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

import json
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

    # Safety cap on the number of model round-trips in a tool-use loop.
    MAX_TOOL_ITERATIONS: int = 8

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
        tools: list[dict[str, Any]] | None = None,
    ) -> Any:
        """
        Call the Anthropic API for a single turn.

        Without *tools*, returns the assembled response text as a string
        (streaming by default, to avoid HTTP timeouts on long outputs).

        With *tools*, returns the full ``Message`` object so the caller can
        inspect ``response.stop_reason`` and any ``tool_use`` content blocks.
        Tool turns run non-streaming — the tool loop needs the complete
        message (including tool_use inputs) before it can act.

        In demo mode, returns realistic mock text instead of hitting the API.
        """
        # Demo mode — return realistic mocks without hitting the API.
        if self._demo_mode:
            task_text = ""
            for msg in messages:
                if msg.get("role") == "user":
                    content = msg.get("content", "")
                    if isinstance(content, str):
                        task_text = content[:500]
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

        if tools:
            kwargs["tools"] = tools
            # Non-streaming create; cap max_tokens so the SDK doesn't refuse
            # the request for exceeding its no-stream timeout estimate.
            kwargs["max_tokens"] = min(self.max_tokens, 8192)
            return self._client.messages.create(**kwargs)

        if use_streaming:
            return self._call_llm_streaming(**kwargs)
        else:
            response = self._client.messages.create(**kwargs)
            return self._extract_text(response.content)

    # ── Tool-use loop ─────────────────────────────────────────────────────────

    def _run_tool_loop(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        dispatch: dict[str, Any],
        system: str | None = None,
        max_iterations: int | None = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        """
        Drive the Anthropic tool-use loop.

        Each turn: send messages + tools → receive the model's response. If it
        contains tool_use blocks, validate their arguments, dispatch each to
        the matching callable in *dispatch*, feed the tool_result blocks back,
        and repeat. Stop when the model stops calling tools (``end_turn``) or
        the iteration cap is reached.

        Returns ``(final_text, tool_calls)`` where *tool_calls* records every
        tool the model invoked (name, input, and whether it succeeded).

        NOTE: *messages* is mutated in place — the assistant turn and the
        tool_result turn are appended each iteration.
        """
        cap = max_iterations or self.MAX_TOOL_ITERATIONS
        tool_calls: list[dict[str, Any]] = []

        for _ in range(cap):
            response = self._call_llm(messages, system=system, tools=tools)

            # Server paused a long turn — resend the history to resume it.
            if response.stop_reason == "pause_turn":
                messages.append({"role": "assistant", "content": response.content})
                continue

            tool_uses = [b for b in response.content if getattr(b, "type", None) == "tool_use"]

            # Model is done calling tools — return its final text.
            if response.stop_reason == "end_turn" or not tool_uses:
                return self._extract_text(response.content), tool_calls

            # Preserve the full assistant turn (incl. thinking + tool_use blocks).
            messages.append({"role": "assistant", "content": response.content})

            results: list[dict[str, Any]] = []
            for tu in tool_uses:
                ok, payload = self._invoke_tool(dispatch.get(tu.name), tu.name, tu.input)
                tool_calls.append({"name": tu.name, "input": tu.input, "ok": ok})
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": payload,
                        "is_error": not ok,
                    }
                )
            messages.append({"role": "user", "content": results})

        # Iteration cap hit — ask once more for a final answer, no tools.
        messages.append(
            {
                "role": "user",
                "content": "Tool budget reached. Provide your final answer now without calling more tools.",
            }
        )
        final = self._call_llm(messages, system=system)
        return (final if isinstance(final, str) else self._extract_text(final.content)), tool_calls

    def _invoke_tool(
        self, fn: Any, name: str, args: Any
    ) -> tuple[bool, str]:
        """
        Validate a tool call's arguments and dispatch it to *fn*.

        Returns ``(ok, content)``. On any failure, ``ok`` is False and
        *content* is an error message fed back to the model as an error
        tool_result so it can recover rather than the loop crashing.
        """
        if fn is None:
            return False, f"Unknown tool: {name}"
        if not isinstance(args, dict):
            return False, f"Tool input for '{name}' must be a JSON object, got {type(args).__name__}."

        try:
            # The connector signature is the schema: missing/unexpected/wrong
            # kwargs raise TypeError, which is exactly argument validation.
            result = fn(**args)
        except TypeError as exc:
            return False, f"Invalid arguments for '{name}': {exc}"
        except Exception as exc:  # noqa: BLE001 — surface any tool error to the model
            return False, f"'{name}' failed: {exc}"

        if isinstance(result, str):
            text = result
        else:
            try:
                text = json.dumps(result, default=str)
            except Exception:
                text = str(result)
        # Bound the payload so large diffs/listings don't blow up the context.
        return True, text[:20000]

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
