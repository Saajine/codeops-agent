"""
Persistent storage layer backed by SQLite.
Stores task history, agent outputs, and session metadata across runs.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

from codeops.config import config


class MemoryStore:
    """SQLite-backed persistent memory for agents."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = Path(db_path or config.DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ── Schema ────────────────────────────────────────────────────────────────

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id          TEXT PRIMARY KEY,
                    description TEXT NOT NULL,
                    status      TEXT NOT NULL DEFAULT 'pending',
                    created_at  TEXT NOT NULL,
                    updated_at  TEXT NOT NULL,
                    metadata    TEXT DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS agent_outputs (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id     TEXT NOT NULL,
                    agent_name  TEXT NOT NULL,
                    skill       TEXT NOT NULL,
                    output      TEXT NOT NULL,
                    status      TEXT NOT NULL,
                    iteration   INTEGER NOT NULL DEFAULT 0,
                    created_at  TEXT NOT NULL,
                    FOREIGN KEY (task_id) REFERENCES tasks(id)
                );

                CREATE TABLE IF NOT EXISTS plans (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id     TEXT NOT NULL,
                    plan_json   TEXT NOT NULL,
                    created_at  TEXT NOT NULL,
                    FOREIGN KEY (task_id) REFERENCES tasks(id)
                );

                CREATE TABLE IF NOT EXISTS code_artifacts (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id     TEXT NOT NULL,
                    file_path   TEXT NOT NULL,
                    content     TEXT NOT NULL,
                    language    TEXT,
                    created_at  TEXT NOT NULL,
                    FOREIGN KEY (task_id) REFERENCES tasks(id)
                );
                """
            )

    # ── Connection helper ─────────────────────────────────────────────────────

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ── Tasks ─────────────────────────────────────────────────────────────────

    def save_task(self, task_id: str, description: str, metadata: dict[str, Any] | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO tasks (id, description, status, created_at, updated_at, metadata)
                VALUES (?, ?, 'pending', ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    description=excluded.description,
                    updated_at=excluded.updated_at,
                    metadata=excluded.metadata
                """,
                (task_id, description, now, now, json.dumps(metadata or {})),
            )

    def update_task_status(self, task_id: str, status: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE tasks SET status=?, updated_at=? WHERE id=?",
                (status, datetime.now(timezone.utc).isoformat(), task_id),
            )

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            return dict(row) if row else None

    def list_tasks(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    # ── Agent outputs ─────────────────────────────────────────────────────────

    def save_agent_output(
        self,
        task_id: str,
        agent_name: str,
        skill: str,
        output: str,
        status: str,
        iteration: int = 0,
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO agent_outputs
                    (task_id, agent_name, skill, output, status, iteration, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (task_id, agent_name, skill, output, status, iteration, now),
            )
            return cursor.lastrowid  # type: ignore[return-value]

    def get_agent_outputs(self, task_id: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM agent_outputs WHERE task_id=? ORDER BY created_at",
                (task_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    # ── Plans ─────────────────────────────────────────────────────────────────

    def save_plan(self, task_id: str, plan: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO plans (task_id, plan_json, created_at) VALUES (?, ?, ?)",
                (task_id, json.dumps(plan), datetime.now(timezone.utc).isoformat()),
            )

    def get_latest_plan(self, task_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM plans WHERE task_id=? ORDER BY created_at DESC LIMIT 1",
                (task_id,),
            ).fetchone()
            if row:
                return json.loads(dict(row)["plan_json"])
            return None

    # ── Code artifacts ────────────────────────────────────────────────────────

    def save_code_artifact(
        self, task_id: str, file_path: str, content: str, language: str | None = None
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO code_artifacts (task_id, file_path, content, language, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (task_id, file_path, content, language, datetime.now(timezone.utc).isoformat()),
            )

    def get_code_artifacts(self, task_id: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM code_artifacts WHERE task_id=? ORDER BY created_at",
                (task_id,),
            ).fetchall()
            return [dict(r) for r in rows]
