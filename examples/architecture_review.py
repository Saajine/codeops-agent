#!/usr/bin/env python3
"""
examples/architecture_review.py
─────────────────────────────────
Demo: Architecture Advisor — reviews a system design spec or existing codebase
and produces recommendations, anti-pattern detection, and an implementation roadmap.

Enterprise use case:
  "Architecture & infrastructure maintenance with guided, repeatable workflows —
   mid-level engineers can maintain complex systems confidently."

Usage:
    python examples/architecture_review.py                   # built-in demo spec
    python examples/architecture_review.py --spec "Design a real-time chat system"
    python examples/architecture_review.py --file path/to/spec.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from codeops.agents.architecture_advisor import ArchitectureAdvisorAgent
from codeops.memory.context import ContextManager
from codeops.memory.store import MemoryStore

console = Console()

DEMO_SPEC = """\
## System: Real-Time Notification Service

We need to build a notification service for a SaaS platform with:
- 500K daily active users
- Notifications via: email, in-app, push (iOS/Android), SMS
- Sources: 15 different internal microservices that emit events
- Requirements:
  - Deliver in-app notifications in < 2s
  - Email/SMS within 60s
  - Users can configure preferences (opt-out per channel/type)
  - Full audit trail of all notifications sent
  - Retry failed deliveries with exponential backoff
  - Support notification templates with variable substitution

Current state: notifications are sent synchronously inline in each microservice,
causing timeout issues and coupling.

Tech stack we use: Python, FastAPI, PostgreSQL, Redis, AWS (SQS, SNS, SES).
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="CodeOps — Architecture Advisor Demo")
    parser.add_argument("--spec", type=str, help="System design spec as text")
    parser.add_argument("--file", type=str, help="Path to spec markdown file")
    args = parser.parse_args()

    if args.spec:
        spec = args.spec
    elif args.file:
        spec = Path(args.file).read_text()
    else:
        spec = DEMO_SPEC

    console.print(
        Panel(
            "[bold cyan]CodeOps Agent[/bold cyan] — Architecture Advisor Demo\n\n"
            "Agent: [blue]ArchitectureAdvisorAgent[/blue]\n"
            "Produces: Pattern recommendation · Anti-pattern detection · "
            "Component design · Scalability plan · Implementation roadmap",
            border_style="cyan",
        )
    )

    store = MemoryStore()
    context = ContextManager(persist=False)
    context.set_task(spec)

    agent = ArchitectureAdvisorAgent(store=store)

    with console.status("[cyan]🏗  Running architecture review…[/cyan]"):
        result = agent.execute(spec, context)

    console.print("\n")
    console.print(Panel("[bold]Architecture Review Report[/bold]", border_style="blue"))
    console.print(Markdown(result.output))

    meta = result.metadata
    console.print(
        f"\n[bold]Stats:[/bold] "
        f"Pattern: [cyan]{meta.get('pattern', '?')}[/cyan] | "
        f"Anti-patterns: [yellow]{meta.get('anti_patterns', 0)}[/yellow] | "
        f"Roadmap phases: {meta.get('phases', 0)} | "
        f"Confidence: {meta.get('confidence', '?').upper()}"
    )

    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
