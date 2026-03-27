"""
CodeOps Agent CLI — powered by Typer.

Usage:
    codeops run "Build a rate limiter in Python"
    codeops run "Build a rate limiter" --demo
    codeops plan "Add authentication to the API"
    codeops review --skill code_review "Review this Flask app"
    codeops skills
    codeops history
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from codeops import __version__
from codeops.config import config
from codeops.orchestrator import Orchestrator
from codeops.skills.registry import registry

app = typer.Typer(
    name="codeops",
    help="Multi-agent dev workflow automation powered by Claude.",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()


# ── Main command: run the full pipeline ──────────────────────────────────────

@app.command()
def run(
    task: str = typer.Argument(..., help="Task description — what you want built or fixed."),
    demo: bool = typer.Option(False, "--demo", "-d", help="Run in demo mode (no API key needed)."),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Override the Claude model."),
    max_iterations: Optional[int] = typer.Option(None, "--max-iter", "-i", help="Max self-correction iterations."),
    output_dir: Optional[str] = typer.Option(None, "--output", "-o", help="Directory to write generated files."),
) -> None:
    """Run the full plan -> code -> review -> fix pipeline."""
    if demo:
        os.environ["CODEOPS_DEMO"] = "1"
        config.DEMO_MODE = True

    if model:
        config.MODEL = model

    _print_header(task)

    orchestrator = Orchestrator(max_iterations=max_iterations)
    result = orchestrator.run(task)

    # Show final output
    if result.final_output:
        console.print()
        console.print(Panel(
            Syntax(result.final_output, "python", theme="monokai", line_numbers=True),
            title="Generated Code",
            border_style="green" if result.success else "yellow",
        ))

    # Write files to disk if requested
    if output_dir and result.success:
        _write_output(result.final_output, output_dir)

    # Exit code
    raise typer.Exit(code=0 if result.success else 1)


# ── Plan only ────────────────────────────────────────────────────────────────

@app.command()
def plan(
    task: str = typer.Argument(..., help="Task to plan."),
    demo: bool = typer.Option(False, "--demo", "-d", help="Run in demo mode."),
) -> None:
    """Generate an execution plan without running it."""
    if demo:
        os.environ["CODEOPS_DEMO"] = "1"
        config.DEMO_MODE = True

    _print_header(task)

    orchestrator = Orchestrator()
    result = orchestrator.run_single_skill("task_planning", task)

    if result.success:
        console.print(Panel(
            Syntax(result.output, "json", theme="monokai"),
            title="Execution Plan",
            border_style="cyan",
        ))
    else:
        console.print(f"[red]Planning failed:[/red] {result.output}")


# ── Single skill ─────────────────────────────────────────────────────────────

@app.command()
def review(
    task: str = typer.Argument(..., help="Code or description to review."),
    demo: bool = typer.Option(False, "--demo", "-d", help="Run in demo mode."),
) -> None:
    """Run code review on a task or code snippet."""
    if demo:
        os.environ["CODEOPS_DEMO"] = "1"
        config.DEMO_MODE = True

    _print_header(task)

    orchestrator = Orchestrator()
    result = orchestrator.run_single_skill("code_review", task)

    console.print(Panel(result.output, title="Code Review", border_style="magenta"))


# ── List skills ──────────────────────────────────────────────────────────────

@app.command()
def skills() -> None:
    """List all registered skills and their status."""
    table = Table(title="CodeOps Skills", show_header=True)
    table.add_column("Skill", style="cyan")
    table.add_column("Agent", style="magenta")
    table.add_column("Status", style="green")
    table.add_column("Description")

    for skill in sorted(registry._skills.values(), key=lambda s: s.priority):
        is_roadmap = skill.config.get("roadmap", False)
        status = "[yellow]roadmap[/yellow]" if is_roadmap else "[green]active[/green]"
        table.add_row(skill.name, skill.agent, status, skill.description[:60] + "...")

    console.print(table)


# ── Task history ─────────────────────────────────────────────────────────────

@app.command()
def history(
    limit: int = typer.Option(10, "--limit", "-n", help="Number of recent tasks to show."),
) -> None:
    """Show recent task history from the memory store."""
    from codeops.memory.store import MemoryStore

    store = MemoryStore()
    tasks = store.list_tasks(limit=limit)

    if not tasks:
        console.print("[dim]No task history yet. Run a task first![/dim]")
        return

    table = Table(title="Recent Tasks", show_header=True)
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Status", style="green")
    table.add_column("Task")
    table.add_column("Created")

    for t in tasks:
        sid = t["id"][:8]
        status_style = {
            "success": "green", "failed": "red", "pending": "yellow",
        }.get(t["status"], "white")
        table.add_row(
            sid,
            f"[{status_style}]{t['status']}[/{status_style}]",
            t["description"][:60],
            t.get("created_at", "")[:19],
        )

    console.print(table)


# ── Version ──────────────────────────────────────────────────────────────────

@app.command()
def version() -> None:
    """Show the CodeOps Agent version."""
    console.print(f"[bold cyan]CodeOps Agent[/bold cyan] v{__version__}")
    console.print(f"Model: {config.MODEL}")
    console.print(f"Demo mode: {'[green]on[/green]' if config.DEMO_MODE else '[dim]off[/dim]'}")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _print_header(task: str) -> None:
    mode = "[yellow][DEMO][/yellow] " if config.DEMO_MODE else ""
    console.print(Panel(
        f"{mode}[bold cyan]CodeOps Agent[/bold cyan] v{__version__}\n"
        f"Model: [dim]{config.MODEL}[/dim]\n\n"
        f"[white]{task[:200]}{'...' if len(task) > 200 else ''}[/white]",
        border_style="cyan",
    ))


def _write_output(output: str, output_dir: str) -> None:
    """Write generated code files to the output directory."""
    import re
    from pathlib import Path

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Try to extract ---FILE: path--- blocks
    pattern = re.compile(r"---FILE:\s*(.+?)---\s*(.*?)---END---", re.DOTALL | re.IGNORECASE)
    matches = list(pattern.finditer(output))

    if matches:
        for match in matches:
            fpath = out / match.group(1).strip()
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(match.group(2).strip())
            console.print(f"  [green]wrote[/green] {fpath}")
    else:
        # Single file fallback
        fpath = out / "generated_code.py"
        fpath.write_text(output)
        console.print(f"  [green]wrote[/green] {fpath}")


# ── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    """CLI entry point."""
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL, logging.INFO),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    app()


if __name__ == "__main__":
    main()
