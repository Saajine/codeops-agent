"""
Skill definitions — the contract between tasks and agents.

Each skill describes:
  - name       : unique identifier used for routing
  - agent      : which agent class handles this skill
  - description: human/LLM-readable description
  - tags       : keywords for fuzzy matching
  - priority   : lower = higher priority when multiple skills match
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillDefinition:
    name: str
    agent: str
    description: str
    tags: list[str] = field(default_factory=list)
    priority: int = 50
    config: dict[str, Any] = field(default_factory=dict)


# ── MVP skills (available now) ────────────────────────────────────────────────

SKILL_TASK_PLANNING = SkillDefinition(
    name="task_planning",
    agent="planner",
    description=(
        "Analyse a task or GitHub issue and produce a structured, step-by-step "
        "execution plan with dependencies and skill requirements for each step."
    ),
    tags=["plan", "analyse", "breakdown", "design", "architecture", "steps"],
    priority=10,
)

SKILL_CODE_GENERATION = SkillDefinition(
    name="code_generation",
    agent="coder",
    description=(
        "Generate, implement, or modify code based on a specification or plan step. "
        "Produces production-quality, typed, documented Python/TypeScript/etc. code."
    ),
    tags=["code", "implement", "write", "generate", "build", "develop", "function", "class"],
    priority=20,
)

SKILL_CODE_REVIEW = SkillDefinition(
    name="code_review",
    agent="reviewer",
    description=(
        "Review code output for quality, correctness, security issues, and style. "
        "Returns structured feedback and a pass/fail verdict. Can trigger a "
        "self-correction loop back to the coder agent when issues are found."
    ),
    tags=["review", "check", "validate", "lint", "audit", "quality", "security", "bugs"],
    priority=30,
)

# ── Roadmap skills (registered but not yet implemented) ──────────────────────

SKILL_TEST_GENERATION = SkillDefinition(
    name="test_generation",
    agent="tester",
    description=(
        "Generate comprehensive unit and integration tests for code changes. "
        "[ROADMAP — not yet available]"
    ),
    tags=["test", "unit", "pytest", "coverage"],
    priority=40,
    config={"roadmap": True},
)

SKILL_DOC_GENERATION = SkillDefinition(
    name="doc_generation",
    agent="docs",
    description=(
        "Auto-generate documentation, runbooks, and API references from code changes. "
        "[ROADMAP — not yet available]"
    ),
    tags=["docs", "documentation", "readme", "runbook", "api-docs"],
    priority=50,
    config={"roadmap": True},
)

SKILL_INCIDENT_TRIAGE = SkillDefinition(
    name="incident_triage",
    agent="incident",
    description=(
        "Summarise logs, isolate failures, and propose remediation steps. "
        "[ROADMAP — not yet available]"
    ),
    tags=["incident", "triage", "logs", "error", "failure", "outage"],
    priority=60,
    config={"roadmap": True},
)

SKILL_PIPELINE_OPTIMIZER = SkillDefinition(
    name="pipeline_optimizer",
    agent="pipeline",
    description=(
        "Identify expensive transformations in data pipelines and recommend optimisations. "
        "[ROADMAP — not yet available]"
    ),
    tags=["pipeline", "optimise", "performance", "spark", "etl"],
    priority=70,
    config={"roadmap": True},
)

SKILL_LEGACY_MIGRATOR = SkillDefinition(
    name="legacy_migration",
    agent="migrator",
    description=(
        "Convert legacy code patterns to modern equivalents (e.g. SQL → PySpark, "
        "Python 2 → 3). [ROADMAP — not yet available]"
    ),
    tags=["migrate", "legacy", "upgrade", "convert", "modernise"],
    priority=80,
    config={"roadmap": True},
)

SKILL_DATA_QUALITY = SkillDefinition(
    name="data_quality",
    agent="data_quality",
    description=(
        "Add schema drift checks, null spike detection, and reconciliation logic. "
        "[ROADMAP — not yet available]"
    ),
    tags=["data", "quality", "schema", "drift", "validation"],
    priority=90,
    config={"roadmap": True},
)

# ── New SE-focused skills ──────────────────────────────────────────────────────

SKILL_PR_AUTOMATION = SkillDefinition(
    name="pr_automation",
    agent="github_pr",
    description=(
        "Automatically generate PR descriptions, assess risk, produce inline review "
        "comments, and check merge readiness. Reduces senior reviewer bottleneck."
    ),
    tags=["pr", "pull request", "github", "review", "merge", "description", "devops"],
    priority=25,
)

SKILL_ARCHITECTURE_REVIEW = SkillDefinition(
    name="architecture_review",
    agent="architecture_advisor",
    description=(
        "Review system design specs or existing code and recommend architecture patterns, "
        "identify anti-patterns, and produce a phased implementation roadmap."
    ),
    tags=["architecture", "design", "system", "patterns", "microservices", "scalability", "adr"],
    priority=15,
)

SKILL_SYSTEM_DESIGN = SkillDefinition(
    name="system_design",
    agent="architecture_advisor",
    description=(
        "Design a new system from requirements: component breakdown, tech selection, "
        "data flow, scalability plan, and implementation roadmap."
    ),
    tags=["design", "system", "architecture", "components", "tech stack", "blueprint"],
    priority=16,
)

# ── Registry list ─────────────────────────────────────────────────────────────

ALL_SKILLS: list[SkillDefinition] = [
    SKILL_TASK_PLANNING,
    SKILL_CODE_GENERATION,
    SKILL_CODE_REVIEW,
    SKILL_PR_AUTOMATION,
    SKILL_ARCHITECTURE_REVIEW,
    SKILL_SYSTEM_DESIGN,
    SKILL_TEST_GENERATION,
    SKILL_DOC_GENERATION,
    SKILL_INCIDENT_TRIAGE,
    SKILL_PIPELINE_OPTIMIZER,
    SKILL_LEGACY_MIGRATOR,
    SKILL_DATA_QUALITY,
]
