"""
tests/test_skills.py
─────────────────────
Tests for the SkillRegistry and SkillDefinition.
"""

from __future__ import annotations

import pytest

from codeops.skills.definitions import (
    ALL_SKILLS,
    SKILL_CODE_GENERATION,
    SKILL_CODE_REVIEW,
    SKILL_TASK_PLANNING,
    SkillDefinition,
)
from codeops.skills.registry import SkillRegistry


# ── SkillDefinition tests ─────────────────────────────────────────────────────

class TestSkillDefinition:
    def test_mvp_skills_have_required_fields(self):
        for skill in [SKILL_TASK_PLANNING, SKILL_CODE_GENERATION, SKILL_CODE_REVIEW]:
            assert skill.name
            assert skill.agent
            assert skill.description
            assert isinstance(skill.tags, list)

    def test_roadmap_skills_flagged(self):
        roadmap = [s for s in ALL_SKILLS if s.config.get("roadmap")]
        names = {s.name for s in roadmap}
        assert "test_generation" in names
        assert "doc_generation" in names

    def test_mvp_skills_not_roadmap(self):
        for skill in [SKILL_TASK_PLANNING, SKILL_CODE_GENERATION, SKILL_CODE_REVIEW]:
            assert not skill.config.get("roadmap")

    def test_priorities_ordered(self):
        mvp = [SKILL_TASK_PLANNING, SKILL_CODE_GENERATION, SKILL_CODE_REVIEW]
        priorities = [s.priority for s in mvp]
        assert priorities == sorted(priorities)


# ── SkillRegistry tests ───────────────────────────────────────────────────────

class TestSkillRegistry:
    @pytest.fixture
    def reg(self):
        return SkillRegistry()

    def test_all_skills_registered(self, reg):
        for skill in ALL_SKILLS:
            assert reg.get_skill(skill.name) is not None

    def test_get_skill_returns_correct_definition(self, reg):
        skill = reg.get_skill("task_planning")
        assert skill is not None
        assert skill.agent == "planner"

    def test_get_unknown_skill_returns_none(self, reg):
        assert reg.get_skill("nonexistent_skill") is None

    def test_register_custom_skill(self, reg):
        custom = SkillDefinition(
            name="custom_skill",
            agent="custom_agent",
            description="A custom skill",
            tags=["custom"],
        )
        reg.register_skill(custom)
        assert reg.get_skill("custom_skill") is custom

    def test_register_agent_class(self, reg):
        class MockAgent:
            name = "mock"
            skills = ["task_planning"]

        reg.register_agent_class("mock", MockAgent)
        assert reg.get_agent_class("mock") is MockAgent

    def test_find_skills_by_keyword(self, reg):
        results = reg.find_skills_by_keyword("code")
        names = {s.name for s in results}
        assert "code_generation" in names
        assert "code_review" in names

    def test_find_skills_by_tag(self, reg):
        results = reg.find_skills_by_keyword("plan")
        names = {s.name for s in results}
        assert "task_planning" in names

    def test_find_skills_for_agent(self, reg):
        coder_skills = reg.find_skills_for_agent("coder")
        assert any(s.name == "code_generation" for s in coder_skills)

    def test_available_skills_excludes_roadmap_by_default(self, reg):
        class FakePlanner:
            name = "planner"

        class FakeCoder:
            name = "coder"

        class FakeReviewer:
            name = "reviewer"

        reg.register_agent_class("planner", FakePlanner)
        reg.register_agent_class("coder", FakeCoder)
        reg.register_agent_class("reviewer", FakeReviewer)

        available = reg.available_skills(exclude_roadmap=True)
        names = {s.name for s in available}
        assert "task_planning" in names
        assert "code_generation" in names
        assert "code_review" in names
        assert "test_generation" not in names  # roadmap

    def test_available_skills_includes_roadmap_when_requested(self, reg):
        class FakeTester:
            name = "tester"

        reg.register_agent_class("tester", FakeTester)
        available = reg.available_skills(exclude_roadmap=False)
        names = {s.name for s in available}
        assert "test_generation" in names

    def test_describe_returns_string(self, reg):
        desc = reg.describe()
        assert isinstance(desc, str)
        assert "task_planning" in desc

    def test_all_skill_names(self, reg):
        names = reg.all_skill_names()
        assert "task_planning" in names
        assert "code_generation" in names
        assert len(names) == len(ALL_SKILLS)
