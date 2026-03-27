#!/usr/bin/env python3
"""
examples/feature_build.py
─────────────────────────
Demo: Build a feature from a spec using the full Planner → Coder → Reviewer loop.

Usage:
    python examples/feature_build.py
    python examples/feature_build.py --task "Add JWT authentication to a FastAPI app"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make sure the package root is importable when running directly
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax

from codeops.orchestrator import Orchestrator

console = Console()

DEFAULT_TASK = """\
Feature: Rate-Limited In-Memory Cache with TTL

Build a production-ready Python module called `cache.py` that implements:

1. A thread-safe, in-memory LRU cache with TTL (time-to-live) expiry.
2. A rate limiter decorator that uses the cache to track request counts per key.
3. Type annotations throughout, following PEP 604 (X | Y) syntax.
4. A Cache class with methods: get(key), set(key, value, ttl_seconds), delete(key),
   clear(), and a property `size`.
5. A RateLimiter class with: allow(key, max_calls, window_seconds) → bool.
6. Full docstrings for all public methods.
7. A brief example showing both classes in use.

Requirements:
- No external dependencies (stdlib only).
- Thread-safe using threading.Lock.
- LRU eviction when cache is full (max_size configurable).
- Automatic cleanup of expired entries.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="CodeOps Agent — Feature Build Demo")
    parser.add_argument(
        "--task",
        type=str,
        default=DEFAULT_TASK,
        help="Feature specification (plain text)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=2,
        help="Max self-correction iterations (default: 2)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Directory to save generated code files (optional)",
    )
    args = parser.parse_args()

    console.print(
        Panel(
            "[bold cyan]CodeOps Agent[/bold cyan] — Feature Build Demo\n\n"
            "Agents: [magenta]Planner[/magenta] → [blue]Coder[/blue] → [yellow]Reviewer[/yellow]\n"
            "With self-correction loop enabled.",
            border_style="cyan",
        )
    )

    orchestrator = Orchestrator(max_iterations=args.max_iterations)
    result = orchestrator.run(args.task)

    # ── Display results ───────────────────────────────────────────────────────

    console.print("\n")
    console.print(Panel("[bold]Execution Plan[/bold]", border_style="blue"))
    if result.plan:
        console.print(Markdown(f"**{result.plan.get('title', 'Plan')}**"))
        console.print(Markdown(result.plan.get("description", "")))
        for step in result.plan.get("steps", []):
            console.print(
                f"  [cyan]{step['id']}.[/cyan] {step['title']} "
                f"[dim]({step.get('skill', '?')})[/dim]"
            )

    console.print("\n")
    console.print(Panel("[bold]Generated Code[/bold]", border_style="green"))

    if result.final_output:
        # Print the last code generation output with syntax highlighting
        # Detect language from first FILE block
        import re
        lang = "python"
        m = re.search(r"---FILE:\s*(.+?)---", result.final_output)
        if m:
            ext = m.group(1).rsplit(".", 1)[-1].lower()
            lang_map = {"py": "python", "ts": "typescript", "js": "javascript", "go": "go"}
            lang = lang_map.get(ext, "python")

        # Show first 200 lines
        lines = result.final_output.splitlines()
        preview = "\n".join(lines[:200])
        if len(lines) > 200:
            preview += f"\n\n[... {len(lines) - 200} more lines ...]"
        console.print(Syntax(preview, lang, theme="monokai", line_numbers=True))

    # ── Save to disk if requested ─────────────────────────────────────────────
    if args.output_dir and result.final_output:
        import re
        out_dir = Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        pattern = re.compile(r"---FILE:\s*(.+?)---\s*(.*?)---END---", re.DOTALL | re.IGNORECASE)
        saved = []
        for match in pattern.finditer(result.final_output):
            fpath = out_dir / match.group(1).strip()
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(match.group(2).strip(), encoding="utf-8")
            saved.append(str(fpath))
        if saved:
            console.print(f"\n[green]✓ Saved {len(saved)} file(s) to {args.output_dir}:[/green]")
            for f in saved:
                console.print(f"  {f}")

    # ── Print review summary ──────────────────────────────────────────────────
    review_results = [r for r in result.agent_results if r.skill == "code_review"]
    if review_results:
        last_review = review_results[-1]
        console.print("\n")
        console.print(Panel("[bold]Final Code Review[/bold]", border_style="yellow"))
        console.print(Markdown(last_review.output))

    # Exit code
    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
