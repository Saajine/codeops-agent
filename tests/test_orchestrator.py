"""
tests/test_orchestrator.py
──────────────────────────
Integration-style tests for the Orchestrator.
All LLM calls are mocked so these run without a real API key.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest

from codeops.agents.base_agent import AgentResult
from codeops.memory.store import MemoryStore
from codeops.orchestrator import Orchestrator, OrchestratorResult


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_store(tmp_path):
    return MemoryStore(db_path=str(tmp_path / "test.db"))


SIMPLE_PLAN = {
    "title": "Simple Feature",
    "description": "Build a basic function",
    "estimated_complexity": "low",
    "steps": [
        {
            "id": 1,
            "title": "Write function",
            "description": "Implement add(a, b)",
            "skill": "code_generation",
            "depends_on": [],
            "acceptance_criteria": "Returns correct sum",
        }
    ],
    "risks": [],
    "tech_stack": ["Python"],
}

MOCK_CODE = """\
---FILE: add.py---
def add(a: int, b: int) -> int:
    \"\"\"Return the sum of a and b.\"\"\"
    return a + b
---END---

## Implementation Notes
Simple addition function.
"""

MOCK_REVIEW_APPROVED = json.dumps({
    "verdict": "approved",
    "score": 9,
    "summary": "Clean and correct.",
    "issues": [],
    "strengths": ["Simple", "Typed"],
    "required_changes": [],
    "suggested_changes": [],
})

MOCK_REVIEW_FAIL = json.dumps({
    "verdict": "needs_revision",
    "score": 4,
    "summary": "Missing edge case handling.",
    "issues": [
        {
            "severity": "major",
            "category": "correctness",
            "description": "No overflow protection",
            "location": "add",
            "fix": "Add overflow check",
        }
    ],
    "strengths": [],
    "required_changes": ["Add overflow check"],
    "suggested_changes": [],
})


def make_orchestrator(store):
    return Orchestrator(max_iterations=2, store=store)


# ── Orchestrator tests ────────────────────────────────────────────────────────

class TestOrchestrator:
    def _mock_all_agents(self, orchestrator):
        """Patch _call_llm on all agent instances inside the orchestrator."""
        for agent in orchestrator._agents.values():
            if agent.name == "planner":
                agent._call_llm = MagicMock(return_value=json.dumps(SIMPLE_PLAN))
            elif agent.name == "coder":
                agent._call_llm = MagicMock(return_value=MOCK_CODE)
            elif agent.name == "reviewer":
                agent._call_llm = MagicMock(return_value=MOCK_REVIEW_APPROVED)

    def test_full_pipeline_success(self, tmp_store):
        orc = make_orchestrator(tmp_store)
        self._mock_all_agents(orc)

        with patch("codeops.config.Config.validate"):
            result = orc.run("Build an add function")

        assert isinstance(result, OrchestratorResult)
        assert result.success
        assert result.plan.get("title") == "Simple Feature"

    def test_plan_failure_aborts_pipeline(self, tmp_store):
        orc = make_orchestrator(tmp_store)
        orc._agents["planner"]._call_llm = MagicMock(return_value="invalid json")
        orc._agents["coder"]._call_llm = MagicMock(return_value=MOCK_CODE)
        orc._agents["reviewer"]._call_llm = MagicMock(return_value=MOCK_REVIEW_APPROVED)

        with patch("codeops.config.Config.validate"):
            result = orc.run("Build an add function")

        assert result.status == "failed"
        # Coder should not have been called
        orc._agents["coder"]._call_llm.assert_not_called()

    def test_self_correction_loop(self, tmp_store):
        """Reviewer rejects first attempt, approves second."""
        orc = make_orchestrator(tmp_store)
        orc._agents["planner"]._call_llm = MagicMock(return_value=json.dumps(SIMPLE_PLAN))
        orc._agents["coder"]._call_llm = MagicMock(return_value=MOCK_CODE)
        # First review fails, second approves
        orc._agents["reviewer"]._call_llm = MagicMock(
            side_effect=[MOCK_REVIEW_FAIL, MOCK_REVIEW_APPROVED]
        )

        with patch("codeops.config.Config.validate"):
            result = orc.run("Build an add function")

        # Coder should be called twice (original + revision)
        assert orc._agents["coder"]._call_llm.call_count == 2
        # Final result should be success (second review approved)
        assert result.status == "success"

    def test_max_iterations_respected(self, tmp_store):
        """Even if reviewer always rejects, we stop at max_iterations."""
        orc = Orchestrator(max_iterations=2, store=tmp_store)
        orc._agents["planner"]._call_llm = MagicMock(return_value=json.dumps(SIMPLE_PLAN))
        orc._agents["coder"]._call_llm = MagicMock(return_value=MOCK_CODE)
        orc._agents["reviewer"]._call_llm = MagicMock(return_value=MOCK_REVIEW_FAIL)

        with patch("codeops.config.Config.validate"):
            result = orc.run("Build an add function")

        # Coder should be called exactly max_iterations times
        assert orc._agents["coder"]._call_llm.call_count == 2

    def test_run_single_skill(self, tmp_store):
        """run_single_skill bypasses the planner."""
        orc = make_orchestrator(tmp_store)
        orc._agents["reviewer"]._call_llm = MagicMock(return_value=MOCK_REVIEW_APPROVED)

        # Inject code into context via a patched orchestrator.run_single_skill
        from codeops.memory.context import ContextManager
        orig_run = orc.run_single_skill

        def patched_run(skill_name, task, task_id=None):
            result = orig_run(skill_name, task, task_id)
            return result

        # Pre-seed the context that run_single_skill creates
        from codeops.memory.context import ContextManager as CM
        original_init = CM.__init__

        def patched_init(self, task_id=None, persist=True):
            original_init(self, task_id=task_id, persist=False)

        with patch.object(CM, "__init__", patched_init):
            with patch("codeops.config.Config.validate"):
                # The reviewer will get no code_generation output → error
                result = orc.run_single_skill("code_review", "Review some code")

        # Expected: error because no code in context
        assert isinstance(result, AgentResult)

    def test_task_saved_to_store(self, tmp_store):
        orc = make_orchestrator(tmp_store)
        self._mock_all_agents(orc)
        task_id = str(uuid.uuid4())

        with patch("codeops.config.Config.validate"):
            orc.run("Build an add function", task_id=task_id)

        saved = tmp_store.get_task(task_id)
        assert saved is not None
        assert saved["description"] == "Build an add function"

    def test_agent_results_populated(self, tmp_store):
        orc = make_orchestrator(tmp_store)
        self._mock_all_agents(orc)

        with patch("codeops.config.Config.validate"):
            result = orc.run("Build an add function")

        skills = {r.skill for r in result.agent_results}
        assert "task_planning" in skills
        assert "code_generation" in skills
        assert "code_review" in skills

    def test_determine_final_status_all_errors(self):
        results = [
            AgentResult("a", "s", "fail", "error"),
            AgentResult("b", "s", "fail", "error"),
        ]
        assert Orchestrator._determine_final_status(results) == "failed"

    def test_determine_final_status_review_approved(self):
        results = [
            AgentResult("coder", "code_generation", "code", "success", next_action="review"),
            AgentResult("reviewer", "code_review", "ok", "success", next_action="done"),
        ]
        assert Orchestrator._determine_final_status(results) == "success"
