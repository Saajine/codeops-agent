"""
Skill Registry — maps skill names to agent classes and provides
keyword-based skill discovery so the orchestrator can route tasks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Type

from codeops.skills.definitions import ALL_SKILLS, SkillDefinition

if TYPE_CHECKING:
    from codeops.agents.base_agent import BaseAgent


class SkillRegistry:
    """Central registry for all skills and their agent mappings."""

    def __init__(self) -> None:
        self._skills: dict[str, SkillDefinition] = {}
        self._agent_classes: dict[str, "Type[BaseAgent]"] = {}

        # Auto-register all built-in skills
        for skill in ALL_SKILLS:
            self._skills[skill.name] = skill

    # ── Registration ──────────────────────────────────────────────────────────

    def register_skill(self, skill: SkillDefinition) -> None:
        """Register or overwrite a skill definition."""
        self._skills[skill.name] = skill

    def register_agent_class(self, agent_name: str, agent_class: "Type[BaseAgent]") -> None:
        """Bind an agent name to its implementation class."""
        self._agent_classes[agent_name] = agent_class

    # ── Lookup ────────────────────────────────────────────────────────────────

    def get_skill(self, name: str) -> SkillDefinition | None:
        return self._skills.get(name)

    def get_agent_class(self, agent_name: str) -> "Type[BaseAgent] | None":
        return self._agent_classes.get(agent_name)

    def get_agent_class_for_skill(self, skill_name: str) -> "Type[BaseAgent] | None":
        skill = self.get_skill(skill_name)
        if not skill:
            return None
        return self._agent_classes.get(skill.agent)

    # ── Discovery ────────────────────────────────────────────────────────────

    def find_skills_by_keyword(self, keyword: str) -> list[SkillDefinition]:
        """Return skills whose name, description, or tags contain *keyword*."""
        kw = keyword.lower()
        matches: list[SkillDefinition] = []
        for skill in self._skills.values():
            if (
                kw in skill.name
                or kw in skill.description.lower()
                or any(kw in t for t in skill.tags)
            ):
                matches.append(skill)
        return sorted(matches, key=lambda s: s.priority)

    def find_skills_for_agent(self, agent_name: str) -> list[SkillDefinition]:
        return [s for s in self._skills.values() if s.agent == agent_name]

    def available_skills(self, exclude_roadmap: bool = True) -> list[SkillDefinition]:
        """Return skills that have a registered agent class."""
        out = []
        for skill in self._skills.values():
            if exclude_roadmap and skill.config.get("roadmap"):
                continue
            if skill.agent in self._agent_classes:
                out.append(skill)
        return sorted(out, key=lambda s: s.priority)

    def all_skill_names(self) -> list[str]:
        return list(self._skills.keys())

    def describe(self) -> str:
        """Human-readable summary of the registry."""
        lines = ["Skill Registry", "=" * 40]
        for skill in sorted(self._skills.values(), key=lambda s: s.priority):
            status = "✓" if skill.agent in self._agent_classes else "○"
            roadmap = " [roadmap]" if skill.config.get("roadmap") else ""
            lines.append(f"  {status} {skill.name:<25} → {skill.agent}{roadmap}")
        return "\n".join(lines)


# ── Module-level singleton ────────────────────────────────────────────────────

registry = SkillRegistry()
