"""
Shared context manager — the "working memory" that all agents read and write
within a single task execution.  Persisted to JSON after each update so that
sessions can be resumed.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codeops.config import config


class ContextManager:
    """
    In-memory context for a running task, with optional JSON persistence.

    All agents receive the same ContextManager instance so they share:
      - The original task description
      - The current execution plan (from PlannerAgent)
      - Each agent's outputs keyed by skill name
      - A running event log
      - The iteration counter (for self-correction loops)
    """

    def __init__(self, task_id: str | None = None, persist: bool = True) -> None:
        self.task_id: str = task_id or str(uuid.uuid4())
        self.persist = persist
        self._persist_path = Path(config.CONTEXT_FILE).with_suffix(f".{self.task_id[:8]}.json")

        # Core state
        self.task_description: str = ""
        self.plan: dict[str, Any] = {}
        self.agent_outputs: dict[str, Any] = {}   # skill_name → last output
        self.iteration: int = 0
        self.status: str = "pending"
        self.events: list[dict[str, Any]] = []
        self.metadata: dict[str, Any] = {}
        self.created_at: str = datetime.now(timezone.utc).isoformat()
        self.updated_at: str = self.created_at

    # ── Core accessors ────────────────────────────────────────────────────────

    def set_task(self, description: str) -> None:
        self.task_description = description
        self._log_event("task_set", {"description": description})
        self._save()

    def set_plan(self, plan: dict[str, Any]) -> None:
        self.plan = plan
        self._log_event("plan_set", {"steps": len(plan.get("steps", []))})
        self._save()

    def set_agent_output(self, skill: str, output: Any, agent_name: str = "") -> None:
        self.agent_outputs[skill] = {
            "output": output,
            "agent": agent_name,
            "iteration": self.iteration,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._log_event("agent_output", {"skill": skill, "agent": agent_name})
        self._save()

    def get_agent_output(self, skill: str) -> Any:
        entry = self.agent_outputs.get(skill)
        return entry["output"] if entry else None

    def increment_iteration(self) -> None:
        self.iteration += 1
        self._log_event("iteration", {"count": self.iteration})
        self._save()

    def set_status(self, status: str) -> None:
        self.status = status
        self._log_event("status_change", {"status": status})
        self._save()

    def set_metadata(self, key: str, value: Any) -> None:
        self.metadata[key] = value
        self._save()

    def get_metadata(self, key: str, default: Any = None) -> Any:
        return self.metadata.get(key, default)

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_description": self.task_description,
            "plan": self.plan,
            "agent_outputs": self.agent_outputs,
            "iteration": self.iteration,
            "status": self.status,
            "events": self.events[-50:],   # keep last 50 events
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContextManager":
        ctx = cls(task_id=data.get("task_id"))
        ctx.task_description = data.get("task_description", "")
        ctx.plan = data.get("plan", {})
        ctx.agent_outputs = data.get("agent_outputs", {})
        ctx.iteration = data.get("iteration", 0)
        ctx.status = data.get("status", "pending")
        ctx.events = data.get("events", [])
        ctx.metadata = data.get("metadata", {})
        ctx.created_at = data.get("created_at", datetime.now(timezone.utc).isoformat())
        return ctx

    # ── Persistence helpers ───────────────────────────────────────────────────

    def _save(self) -> None:
        self.updated_at = datetime.now(timezone.utc).isoformat()
        if not self.persist:
            return
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._persist_path, "w") as fh:
                json.dump(self.to_dict(), fh, indent=2)
        except Exception:
            pass  # non-fatal

    @classmethod
    def load(cls, task_id: str) -> "ContextManager | None":
        path = Path(config.CONTEXT_FILE).with_suffix(f".{task_id[:8]}.json")
        if not path.exists():
            return None
        try:
            with open(path) as fh:
                return cls.from_dict(json.load(fh))
        except Exception:
            return None

    # ── Event log ─────────────────────────────────────────────────────────────

    def _log_event(self, event_type: str, payload: dict[str, Any]) -> None:
        self.events.append(
            {
                "type": event_type,
                "payload": payload,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    def get_events(self, event_type: str | None = None) -> list[dict[str, Any]]:
        if event_type is None:
            return self.events
        return [e for e in self.events if e["type"] == event_type]

    # ── Display helpers ───────────────────────────────────────────────────────

    def summary(self) -> str:
        lines = [
            f"Task ID   : {self.task_id}",
            f"Status    : {self.status}",
            f"Iteration : {self.iteration}",
            f"Task      : {self.task_description[:80]}",
            f"Plan steps: {len(self.plan.get('steps', []))}",
            f"Outputs   : {list(self.agent_outputs.keys())}",
        ]
        return "\n".join(lines)
