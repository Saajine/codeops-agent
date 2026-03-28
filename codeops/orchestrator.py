"""
Orchestrator / Router — the brain of CodeOps Agent.

Responsibilities:
  1. Accept a task description (plain text, GitHub issue, feature spec).
  2. Route to the PlannerAgent to decompose it.
  3. Walk the plan step-by-step, dispatching each step to the right agent
     via the SkillRegistry.
  4. Run the self-correction loop (plan → code → review → fix, max N iterations).
  5. Emit rich console output via Rich so users see real-time progress.
  6. Persist everything to the MemoryStore.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from codeops.agents.base_agent import AgentResult, BaseAgent
from codeops.agents.architecture_advisor import ArchitectureAdvisorAgent
from codeops.agents.coder import CoderAgent
from codeops.agents.github_pr import GitHubPRAgent
from codeops.agents.planner import PlannerAgent
from codeops.agents.reviewer import ReviewerAgent
from codeops.agents.test_generator import TestGeneratorAgent
from codeops.config import config
from codeops.memory.context import ContextManager
from codeops.memory.store import MemoryStore
from codeops.skills.registry import registry

logger = logging.getLogger(__name__)
console = Console()


@dataclass
class OrchestratorResult:
    """Final result returned to the caller after full pipeline execution."""

    task_id: str
    task_description: str
    status: str                          # "success" | "partial" | "failed"
    plan: dict[str, Any] = field(default_factory=dict)
    agent_results: list[AgentResult] = field(default_factory=list)
    final_output: str = ""
    iterations: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.status == "success"

    def summary_table(self) -> Table:
        table = Table(title="CodeOps Execution Summary", show_header=True)
        table.add_column("Agent", style="cyan")
        table.add_column("Skill", style="magenta")
        table.add_column("Status", style="green")
        table.add_column("Output Preview")
        for r in self.agent_results:
            status_style = "green" if r.success else "red" if r.status == "error" else "yellow"
            table.add_row(
                r.agent_name,
                r.skill,
                f"[{status_style}]{r.status}[/{status_style}]",
                r.output[:80] + ("…" if len(r.output) > 80 else ""),
            )
        return table


class Orchestrator:
    """
    Routes tasks to specialised agents, manages the self-correction loop,
    and aggregates results.
    """

    def __init__(
        self,
        max_iterations: int | None = None,
        store: MemoryStore | None = None,
    ) -> None:
        self.max_iterations = max_iterations or config.MAX_ITERATIONS
        self.store = store or MemoryStore()

        # Initialise agents and register them with the skill registry
        self._agents: dict[str, BaseAgent] = {}
        self._init_agents()

    # ── Public API ────────────────────────────────────────────────────────────

    def run(self, task: str, task_id: str | None = None) -> OrchestratorResult:
        """
        Main entry-point.  Runs the full plan → code → review pipeline.

        Args:
            task    : free-form task description or GitHub issue body.
            task_id : optional stable ID for resumption / tracking.

        Returns:
            OrchestratorResult with all agent outputs and final status.
        """
        config.validate()

        task_id = task_id or str(uuid.uuid4())
        context = ContextManager(task_id=task_id)
        context.set_task(task)
        self.store.save_task(task_id, task)

        console.print(
            Panel(
                f"[bold cyan]CodeOps Agent[/bold cyan]\n\n"
                f"[white]{task[:200]}{'…' if len(task) > 200 else ''}[/white]",
                title="🚀 New Task",
                border_style="cyan",
            )
        )

        all_results: list[AgentResult] = []

        try:
            # ── Step 1: Plan ──────────────────────────────────────────────────
            plan_result = self._run_agent("planner", "task_planning", task, context)
            all_results.append(plan_result)

            if plan_result.status == "error":
                return self._build_result(task_id, task, "failed", context, all_results)

            plan = context.plan
            steps = plan.get("steps", [])

            if not steps:
                return self._build_result(task_id, task, "failed", context, all_results)

            # ── Step 2: Execute each step ────────────────────────────────────
            for step in steps:
                step_results = self._execute_step(step, context)
                all_results.extend(step_results)

                # If a step fatally errored, stop
                last = step_results[-1] if step_results else None
                if last and last.status == "error" and last.next_action == "abort":
                    context.set_status("failed")
                    break

            # Determine final status
            final_status = self._determine_final_status(all_results)
            context.set_status(final_status)
            self.store.update_task_status(task_id, final_status)

            result = self._build_result(task_id, task, final_status, context, all_results)
            self._print_summary(result)
            return result

        except Exception as exc:
            logger.exception("Orchestrator error: %s", exc)
            context.set_status("failed")
            self.store.update_task_status(task_id, "failed")
            return self._build_result(task_id, task, "failed", context, all_results)

    def run_single_skill(
        self, skill_name: str, task: str, task_id: str | None = None
    ) -> AgentResult:
        """
        Bypass the planner and execute a single skill directly.
        Useful for targeted operations like 'just review this code'.
        """
        config.validate()
        task_id = task_id or str(uuid.uuid4())
        context = ContextManager(task_id=task_id)
        context.set_task(task)

        skill = registry.get_skill(skill_name)
        if not skill:
            return AgentResult(
                agent_name="orchestrator",
                skill=skill_name,
                output=f"Unknown skill: {skill_name}",
                status="error",
                next_action="abort",
            )

        return self._run_agent(skill.agent, skill_name, task, context)

    # ── Step execution ────────────────────────────────────────────────────────

    def _execute_step(
        self, step: dict[str, Any], context: ContextManager
    ) -> list[AgentResult]:
        """Execute a single plan step, including its self-correction loop."""
        skill = step.get("skill", "code_generation")
        step_task = f"{step.get('title', '')}\n\n{step.get('description', '')}"
        results: list[AgentResult] = []

        console.print(
            f"\n[bold]Step {step.get('id', '?')}:[/bold] [cyan]{step.get('title', '')}[/cyan] "
            f"[dim](skill: {skill})[/dim]"
        )

        # Code-generation steps get the review + self-correction loop
        if skill == "code_generation":
            results = self._run_code_review_loop(step_task, context)
        else:
            agent_name = self._get_agent_for_skill(skill)
            if agent_name:
                result = self._run_agent(agent_name, skill, step_task, context)
                results.append(result)
            else:
                console.print(f"  [yellow]⚠ No agent for skill '{skill}', skipping.[/yellow]")

        return results

    def _run_code_review_loop(
        self, task: str, context: ContextManager
    ) -> list[AgentResult]:
        """
        plan → code → review → (fix → review)*  up to max_iterations.
        """
        results: list[AgentResult] = []

        for i in range(self.max_iterations):
            context.iteration = i

            # Code
            code_result = self._run_agent("coder", "code_generation", task, context)
            results.append(code_result)

            if code_result.status == "error":
                break

            # Review
            review_result = self._run_agent("reviewer", "code_review", task, context)
            results.append(review_result)

            if review_result.status == "error":
                break

            if review_result.next_action == "done":
                console.print(
                    f"  [green]✓ Code approved on iteration {i + 1}[/green]"
                )
                break

            if i < self.max_iterations - 1:
                score = review_result.metadata.get("score", "?")
                console.print(
                    f"  [yellow]↻ Revision needed (score {score}/10) — "
                    f"iteration {i + 2}/{self.max_iterations}[/yellow]"
                )
                context.increment_iteration()
            else:
                console.print(
                    f"  [yellow]⚠ Max iterations reached — accepting best attempt[/yellow]"
                )

        return results

    # ── Agent dispatch ────────────────────────────────────────────────────────

    def _run_agent(
        self, agent_name: str, skill: str, task: str, context: ContextManager
    ) -> AgentResult:
        agent = self._agents.get(agent_name)
        if not agent:
            return AgentResult(
                agent_name=agent_name,
                skill=skill,
                output=f"Agent '{agent_name}' not registered.",
                status="error",
                next_action="abort",
            )

        label_map = {
            "planner": "🗺  Planning",
            "coder": "⚙  Coding",
            "reviewer": "🔍  Reviewing",
            "tester": "🧪  Generating Tests",
            "github_pr": "🔀  PR Automation",
            "architecture_advisor": "🏗  Architecture Review",
        }
        label = label_map.get(agent_name, f"▶  {agent_name}")

        with Progress(
            SpinnerColumn(),
            TextColumn(f"[cyan]{label}…"),
            transient=True,
            console=console,
        ) as progress:
            progress.add_task("", total=None)
            result = agent.execute(task, context)

        # Display status icon
        icon = "✓" if result.success else ("✗" if result.status == "error" else "⚠")
        color = "green" if result.success else ("red" if result.status == "error" else "yellow")
        console.print(f"  [{color}]{icon} {agent_name}[/{color}] → {result.status}")

        return result

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _init_agents(self) -> None:
        """Instantiate all built-in agents and register them."""
        agent_instances: list[BaseAgent] = [
            PlannerAgent(store=self.store),
            CoderAgent(store=self.store),
            ReviewerAgent(store=self.store),
            GitHubPRAgent(store=self.store),
            ArchitectureAdvisorAgent(store=self.store),
            TestGeneratorAgent(store=self.store),
        ]
        for agent in agent_instances:
            self._agents[agent.name] = agent
            registry.register_agent_class(agent.name, type(agent))

    def _get_agent_for_skill(self, skill_name: str) -> str | None:
        skill = registry.get_skill(skill_name)
        return skill.agent if skill else None

    @staticmethod
    def _determine_final_status(results: list[AgentResult]) -> str:
        if not results:
            return "failed"
        errors = sum(1 for r in results if r.status == "error")
        if errors == len(results):
            return "failed"
        # If the last review approved or there were no review results, call it success
        review_results = [r for r in results if r.skill == "code_review"]
        if review_results and review_results[-1].next_action == "done":
            return "success"
        if errors == 0:
            return "success"
        return "partial"

    @staticmethod
    def _build_result(
        task_id: str,
        task: str,
        status: str,
        context: ContextManager,
        all_results: list[AgentResult],
    ) -> OrchestratorResult:
        final_output = ""
        # Last code generation output is the primary deliverable
        code_output = context.get_agent_output("code_generation")
        if code_output:
            final_output = code_output

        return OrchestratorResult(
            task_id=task_id,
            task_description=task,
            status=status,
            plan=context.plan,
            agent_results=all_results,
            final_output=final_output,
            iterations=context.iteration + 1,
            metadata={"context": context.to_dict()},
        )

    @staticmethod
    def _print_summary(result: OrchestratorResult) -> None:
        console.print()
        console.print(result.summary_table())
        status_color = "green" if result.success else "yellow" if result.status == "partial" else "red"
        console.print(
            f"\n[{status_color}]Pipeline complete — {result.status.upper()}[/{status_color}] "
            f"in {result.iterations} iteration(s) | Task ID: {result.task_id}"
        )
