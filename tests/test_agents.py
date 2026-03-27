"""
tests/test_agents.py
────────────────────
Unit tests for PlannerAgent, CoderAgent, and ReviewerAgent.
All Anthropic API calls are mocked.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest

from codeops.agents.base_agent import AgentResult
from codeops.agents.coder import CoderAgent
from codeops.agents.planner import PlannerAgent
from codeops.agents.reviewer import ReviewerAgent
from codeops.memory.context import ContextManager
from codeops.memory.store import MemoryStore


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_store(tmp_path):
    return MemoryStore(db_path=str(tmp_path / "test.db"))


@pytest.fixture
def context(tmp_path):
    ctx = ContextManager(task_id=str(uuid.uuid4()), persist=False)
    ctx.set_task("Build a rate limiter in Python")
    return ctx


MOCK_PLAN = {
    "title": "Rate Limiter Implementation",
    "description": "Implement a thread-safe rate limiter",
    "estimated_complexity": "medium",
    "steps": [
        {
            "id": 1,
            "title": "Implement RateLimiter class",
            "description": "Create a thread-safe rate limiter using token bucket algorithm",
            "skill": "code_generation",
            "depends_on": [],
            "acceptance_criteria": "Passes unit tests",
        },
        {
            "id": 2,
            "title": "Review implementation",
            "description": "Code review for quality and correctness",
            "skill": "code_review",
            "depends_on": [1],
            "acceptance_criteria": "Score >= 7",
        },
    ],
    "risks": ["Thread safety edge cases"],
    "tech_stack": ["Python", "threading"],
}

MOCK_CODE = """\
---FILE: rate_limiter.py---
\"\"\"Thread-safe rate limiter.\"\"\"
import threading
import time
from collections import deque


class RateLimiter:
    def __init__(self, max_calls: int, period: float) -> None:
        self.max_calls = max_calls
        self.period = period
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def allow(self) -> bool:
        with self._lock:
            now = time.monotonic()
            while self._calls and self._calls[0] <= now - self.period:
                self._calls.popleft()
            if len(self._calls) < self.max_calls:
                self._calls.append(now)
                return True
            return False
---END---

## Implementation Notes
Thread-safe sliding window rate limiter using a deque.
"""

MOCK_REVIEW_APPROVED = {
    "verdict": "approved",
    "score": 9,
    "summary": "Well-structured, thread-safe implementation.",
    "issues": [],
    "strengths": ["Thread-safe", "Clean API"],
    "required_changes": [],
    "suggested_changes": ["Add type stub"],
}

MOCK_REVIEW_NEEDS_REVISION = {
    "verdict": "needs_revision",
    "score": 5,
    "summary": "Missing error handling and tests.",
    "issues": [
        {
            "severity": "major",
            "category": "correctness",
            "description": "No error handling for negative max_calls",
            "location": "__init__",
            "fix": "Add validation in __init__",
        }
    ],
    "strengths": ["Thread-safe"],
    "required_changes": ["Add input validation"],
    "suggested_changes": [],
}


# ── PlannerAgent tests ────────────────────────────────────────────────────────

class TestPlannerAgent:
    def test_execute_returns_success(self, tmp_store, context):
        planner = PlannerAgent(store=tmp_store)
        with patch.object(planner, "_call_llm", return_value=json.dumps(MOCK_PLAN)):
            result = planner.execute("Build a rate limiter", context)

        assert isinstance(result, AgentResult)
        assert result.status == "success"
        assert result.skill == "task_planning"
        assert result.agent_name == "planner"
        assert result.next_action == "execute_plan"

    def test_plan_is_stored_in_context(self, tmp_store, context):
        planner = PlannerAgent(store=tmp_store)
        with patch.object(planner, "_call_llm", return_value=json.dumps(MOCK_PLAN)):
            planner.execute("Build a rate limiter", context)

        assert context.plan.get("title") == "Rate Limiter Implementation"
        assert len(context.plan.get("steps", [])) == 2

    def test_handles_invalid_json(self, tmp_store, context):
        planner = PlannerAgent(store=tmp_store)
        with patch.object(planner, "_call_llm", return_value="not json at all"):
            result = planner.execute("Build a rate limiter", context)

        assert result.status == "error"

    def test_parses_json_with_markdown_fences(self, tmp_store, context):
        planner = PlannerAgent(store=tmp_store)
        wrapped = f"```json\n{json.dumps(MOCK_PLAN)}\n```"
        with patch.object(planner, "_call_llm", return_value=wrapped):
            result = planner.execute("Build a rate limiter", context)

        assert result.status == "success"

    def test_output_is_persisted(self, tmp_store, context):
        planner = PlannerAgent(store=tmp_store)
        with patch.object(planner, "_call_llm", return_value=json.dumps(MOCK_PLAN)):
            planner.execute("Build a rate limiter", context)

        outputs = tmp_store.get_agent_outputs(context.task_id)
        assert any(o["agent_name"] == "planner" for o in outputs)


# ── CoderAgent tests ──────────────────────────────────────────────────────────

class TestCoderAgent:
    def test_execute_returns_success(self, tmp_store, context):
        coder = CoderAgent(store=tmp_store)
        with patch.object(coder, "_call_llm", return_value=MOCK_CODE):
            result = coder.execute("Implement RateLimiter class", context)

        assert result.status == "success"
        assert result.skill == "code_generation"
        assert result.next_action == "review"

    def test_code_is_stored_in_context(self, tmp_store, context):
        coder = CoderAgent(store=tmp_store)
        with patch.object(coder, "_call_llm", return_value=MOCK_CODE):
            coder.execute("Implement RateLimiter class", context)

        code = context.get_agent_output("code_generation")
        assert code is not None
        assert "RateLimiter" in code

    def test_parse_files_extracts_file_blocks(self, tmp_store, context):
        coder = CoderAgent(store=tmp_store)
        files = coder._parse_files(MOCK_CODE)
        assert "rate_limiter.py" in files
        assert "RateLimiter" in files["rate_limiter.py"]

    def test_fallback_when_no_file_blocks(self, tmp_store, context):
        coder = CoderAgent(store=tmp_store)
        plain = "def hello(): pass"
        files = coder._parse_files(plain)
        assert len(files) == 1
        assert "hello" in list(files.values())[0]

    def test_includes_reviewer_feedback_on_retry(self, tmp_store, context):
        context.iteration = 1
        context.set_agent_output("code_review", "Fix missing error handling", agent_name="reviewer")

        coder = CoderAgent(store=tmp_store)
        captured_messages = []

        def capture_llm(messages, **kwargs):
            captured_messages.extend(messages)
            return MOCK_CODE

        with patch.object(coder, "_call_llm", side_effect=capture_llm):
            coder.execute("Implement RateLimiter class", context)

        combined = " ".join(m["content"] for m in captured_messages)
        assert "Reviewer Feedback" in combined or "Fix missing error handling" in combined

    def test_language_detection(self, tmp_store, context):
        assert CoderAgent._detect_language("foo.py", "") == "python"
        assert CoderAgent._detect_language("foo.ts", "") == "typescript"
        assert CoderAgent._detect_language("foo.go", "") == "go"
        assert CoderAgent._detect_language("foo.java", "") == "java"


# ── ReviewerAgent tests ───────────────────────────────────────────────────────

class TestReviewerAgent:
    def test_approve_when_score_high(self, tmp_store, context):
        context.set_agent_output("code_generation", MOCK_CODE, agent_name="coder")
        reviewer = ReviewerAgent(store=tmp_store)
        with patch.object(reviewer, "_call_llm", return_value=json.dumps(MOCK_REVIEW_APPROVED)):
            result = reviewer.execute("Review rate limiter", context)

        assert result.status == "success"
        assert result.next_action == "done"
        assert result.metadata["verdict"] == "approved"
        assert result.metadata["score"] == 9

    def test_needs_revision_when_issues(self, tmp_store, context):
        context.set_agent_output("code_generation", MOCK_CODE, agent_name="coder")
        reviewer = ReviewerAgent(store=tmp_store)
        with patch.object(reviewer, "_call_llm", return_value=json.dumps(MOCK_REVIEW_NEEDS_REVISION)):
            result = reviewer.execute("Review rate limiter", context)

        assert result.status == "needs_revision"
        assert result.next_action == "revise_code"
        assert result.metadata["major_issues"] == 1

    def test_error_when_no_code_in_context(self, tmp_store, context):
        reviewer = ReviewerAgent(store=tmp_store)
        result = reviewer.execute("Review nothing", context)
        assert result.status == "error"

    def test_feedback_contains_required_changes(self, tmp_store, context):
        context.set_agent_output("code_generation", MOCK_CODE, agent_name="coder")
        reviewer = ReviewerAgent(store=tmp_store)
        with patch.object(reviewer, "_call_llm", return_value=json.dumps(MOCK_REVIEW_NEEDS_REVISION)):
            result = reviewer.execute("Review rate limiter", context)

        assert "Required Changes" in result.output or "required_changes" in result.output.lower()

    def test_handles_invalid_json_response(self, tmp_store, context):
        context.set_agent_output("code_generation", MOCK_CODE, agent_name="coder")
        reviewer = ReviewerAgent(store=tmp_store)
        with patch.object(reviewer, "_call_llm", return_value="not json"):
            result = reviewer.execute("Review rate limiter", context)

        assert result.status == "error"
