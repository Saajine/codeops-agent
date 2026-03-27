#!/usr/bin/env python3
"""
examples/incident_triage.py
────────────────────────────
Demo: Simulate an incident triage scenario.

This example shows how CodeOps Agent can analyse error logs, identify root
causes, and propose fixes — demonstrating the orchestrator's flexibility even
before the dedicated IncidentTriageAgent is built (roadmap).

For now we use the Planner + Coder pipeline to analyse the logs and generate
a diagnostic + remediation script.

Usage:
    python examples/incident_triage.py
    python examples/incident_triage.py --log-file path/to/app.log
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from codeops.orchestrator import Orchestrator

console = Console()

# ── Simulated incident log ────────────────────────────────────────────────────

SIMULATED_LOG = """\
2024-03-15 09:00:01 INFO  [app] Starting payment service v2.3.1
2024-03-15 09:00:02 INFO  [db] Connected to postgres://prod-db:5432/payments
2024-03-15 09:00:05 INFO  [app] Listening on :8080
2024-03-15 09:12:34 ERROR [payment] Transaction failed: connection timeout after 30s
2024-03-15 09:12:34 ERROR [db] Pool exhausted: all 20 connections in use
2024-03-15 09:12:35 ERROR [payment] Transaction failed: connection timeout after 30s
2024-03-15 09:12:35 WARN  [app] Queue depth: 450 (threshold: 100)
2024-03-15 09:12:40 ERROR [db] Pool exhausted: all 20 connections in use
2024-03-15 09:12:41 ERROR [payment] Retry 1/3 failed for txn_8x9k2p: db unavailable
2024-03-15 09:12:43 ERROR [payment] Retry 2/3 failed for txn_8x9k2p: db unavailable
2024-03-15 09:12:45 ERROR [payment] Retry 3/3 failed for txn_8x9k2p: db unavailable
2024-03-15 09:12:45 ERROR [payment] Transaction txn_8x9k2p PERMANENTLY FAILED
2024-03-15 09:12:46 CRIT  [app] Circuit breaker OPEN: payment-service → postgres
2024-03-15 09:12:46 ERROR [app] 503 Service Unavailable returned to 89 clients
2024-03-15 09:13:01 WARN  [db] Long-running query detected (45s): SELECT * FROM transactions WHERE status='pending' ORDER BY created_at
2024-03-15 09:13:02 ERROR [db] DeadlockException on table 'transactions': pid=1234 vs pid=5678
2024-03-15 09:13:05 ERROR [db] DeadlockException on table 'transactions': pid=2341 vs pid=6789
2024-03-15 09:15:00 INFO  [app] Circuit breaker attempting HALF-OPEN
2024-03-15 09:15:02 ERROR [db] Pool exhausted: all 20 connections in use
2024-03-15 09:15:02 CRIT  [app] Circuit breaker remaining OPEN
2024-03-15 09:16:00 CRIT  [ops] PagerDuty alert triggered: payment-service DOWN
2024-03-15 09:16:30 INFO  [ops] On-call engineer notified
"""

TRIAGE_TASK_TEMPLATE = """\
## Production Incident — Payment Service Outage

You are an expert Site Reliability Engineer (SRE). Analyse the following production
logs and produce:

1. **Root Cause Analysis**: What caused the outage? (be specific about the chain of events)
2. **Immediate Mitigation Script**: A runnable Python/bash script to restore service.
3. **Permanent Fix**: Code changes to prevent recurrence (with file paths and full implementations).
4. **Monitoring Improvements**: New alerts/metrics to add to catch this earlier.

### Log Output
```
{logs}
```

Prioritise correctness and production safety in all code suggestions.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="CodeOps Agent — Incident Triage Demo")
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Path to a log file to analyse (default: built-in simulated log)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=1,
        help="Max self-correction iterations (default: 1)",
    )
    args = parser.parse_args()

    if args.log_file:
        p = Path(args.log_file)
        if not p.exists():
            console.print(f"[red]Log file not found: {args.log_file}[/red]")
            sys.exit(1)
        logs = p.read_text(encoding="utf-8")
        console.print(f"[cyan]Loaded {len(logs.splitlines())} log lines from {p.name}[/cyan]")
    else:
        logs = SIMULATED_LOG
        console.print("[cyan]Using built-in simulated payment service incident log[/cyan]")

    task = TRIAGE_TASK_TEMPLATE.format(logs=logs[:6000])  # cap at 6K chars

    console.print(
        Panel(
            "[bold cyan]CodeOps Agent[/bold cyan] — Incident Triage Demo\n\n"
            "Agents: [magenta]Planner[/magenta] → [blue]Coder[/blue] → [yellow]Reviewer[/yellow]\n"
            "[dim]Note: Dedicated IncidentTriageAgent is on the roadmap.[/dim]",
            border_style="cyan",
        )
    )

    orchestrator = Orchestrator(max_iterations=args.max_iterations)
    result = orchestrator.run(task)

    console.print("\n")
    console.print(Panel("[bold]Incident Analysis & Remediation[/bold]", border_style="red"))

    if result.final_output:
        # Show the generated RCA + fix code
        lines = result.final_output.splitlines()
        preview = "\n".join(lines[:300])
        if len(lines) > 300:
            preview += f"\n\n[... {len(lines) - 300} more lines ...]"
        console.print(Markdown(preview))

    # Status
    status_color = "green" if result.success else "red"
    console.print(
        f"\n[{status_color}]Triage complete — {result.status.upper()}[/{status_color}] "
        f"| Task ID: {result.task_id}"
    )

    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
