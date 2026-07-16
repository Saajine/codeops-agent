"""
Eval harness: run each golden case through a runner, capture the ordered tool
names, compare to the expected sequence, report pass/fail + a score.

A runner is any callable: input string -> (action, ordered_tool_names).
`planner_runner` grades the offline tool-planner policy. A live-model runner
(drive github_pr's tool loop, capture tool_calls order) plugs in the same way
when ANTHROPIC_API_KEY is set — the grader below is unchanged.

    python evals/harness.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from codeops.agents.tool_planner import plan_tools
from evals.golden_cases import CASES


def planner_runner(task: str) -> tuple[str, list[str]]:
    plan = plan_tools(task)
    return plan.action, plan.tools


def grade(cases: list[dict], runner) -> list[dict]:
    results = []
    for c in cases:
        action, tools = runner(c["input"])
        if c["kind"] == "tools":
            ok = action == "proceed" and tools == c["expected"]
            expected = " → ".join(c["expected"]) or "(none)"
        else:  # refuse / escalate
            ok = action == c["kind"]
            expected = c["kind"].upper()
        got = " → ".join(tools) if tools else action.upper()
        results.append({"name": c["name"], "expected": expected, "got": got, "ok": ok})
    return results


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run the golden-case tool-selection eval.")
    parser.add_argument(
        "--min-score",
        type=int,
        default=len(CASES),
        help="Minimum passing cases for exit 0 (default: all). CI gates at the known-good bar.",
    )
    args = parser.parse_args(argv)

    results = grade(CASES, planner_runner)
    w = max(len(r["name"]) for r in results)
    print(f"{'case':<{w}}  {'':1}  {'expected':<32}  got")
    print("-" * (w + 40))
    for r in results:
        mark = "✓" if r["ok"] else "✗"
        print(f"{r['name']:<{w}}  {mark}  {r['expected']:<32}  {r['got']}")
    passed = sum(r["ok"] for r in results)
    print("-" * (w + 40))
    print(f"SCORE: {passed}/{len(results)}  (bar: {args.min_score})")
    return 0 if passed >= args.min_score else 1


if __name__ == "__main__":
    raise SystemExit(main())
