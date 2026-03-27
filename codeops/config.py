"""
CodeOps Agent Configuration
Centralised settings loaded from environment variables / .env file.
"""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the project root (two levels up from this file)
_ROOT = Path(__file__).parent.parent
load_dotenv(_ROOT / ".env")


class Config:
    """Singleton-style configuration object."""

    # ── LLM ──────────────────────────────────────────────────────────────────
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    MODEL: str = os.getenv("CODEOPS_MODEL", "claude-sonnet-4-6")
    MAX_TOKENS: int = int(os.getenv("CODEOPS_MAX_TOKENS", "16000"))

    # ── Agent loop ────────────────────────────────────────────────────────────
    MAX_ITERATIONS: int = int(os.getenv("CODEOPS_MAX_ITERATIONS", "3"))

    # ── External services ────────────────────────────────────────────────────
    GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")

    # ── Persistence ──────────────────────────────────────────────────────────
    DB_PATH: str = os.getenv("CODEOPS_DB_PATH", str(_ROOT / "codeops_memory.db"))
    CONTEXT_FILE: str = os.getenv("CODEOPS_CONTEXT_FILE", str(_ROOT / "codeops_context.json"))

    # ── Demo mode ──────────────────────────────────────────────────────────────
    DEMO_MODE: bool = os.getenv("CODEOPS_DEMO", "").lower() in ("1", "true", "yes")

    # ── Logging ───────────────────────────────────────────────────────────────
    LOG_LEVEL: str = os.getenv("CODEOPS_LOG_LEVEL", "INFO")

    @classmethod
    def validate(cls) -> None:
        """Raise if critical config is missing (skipped in demo mode)."""
        if cls.DEMO_MODE:
            return
        if not cls.ANTHROPIC_API_KEY:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY is not set. "
                "Copy .env.example → .env and add your key, "
                "or run with CODEOPS_DEMO=1 for demo mode."
            )


config = Config()
