"""
Demo mode — realistic mock responses for running CodeOps without an API key.

When CODEOPS_DEMO=1, the BaseAgent._call_llm() method uses these responses
instead of hitting the Anthropic API.  This lets you demo the full pipeline
in interviews, CI, or offline environments.
"""

from __future__ import annotations

import json
import time
import random

# ── Simulated latency ──────────────────────────────────────────────────────────

_SPEED = 0.02  # seconds per "token" for realistic streaming feel


def _simulate_typing(text: str) -> str:
    """Add a small delay to make demo mode feel realistic."""
    # Sleep proportional to output length, capped at 2s
    delay = min(len(text) * _SPEED * 0.01, 2.0)
    time.sleep(delay)
    return text


# ── Planner responses ─────────────────────────────────────────────────────────

def _planner_response(task: str) -> str:
    """Generate a realistic planner JSON response based on the task."""
    # Extract a short title from the task
    title = task.strip().split("\n")[0][:60]

    plan = {
        "title": title,
        "description": (
            f"Analysing the task and breaking it into implementation steps. "
            f"This plan covers design, implementation, testing, and review."
        ),
        "estimated_complexity": "medium",
        "steps": [
            {
                "id": 1,
                "title": "Core implementation",
                "description": (
                    f"Implement the main logic for: {title}. "
                    "Include type annotations, error handling, and docstrings."
                ),
                "skill": "code_generation",
                "depends_on": [],
                "acceptance_criteria": "Code compiles, passes type checks, handles edge cases",
            },
            {
                "id": 2,
                "title": "Code review and quality check",
                "description": (
                    "Review the implementation for correctness, security, performance, "
                    "and code quality. Verify error handling and edge cases."
                ),
                "skill": "code_review",
                "depends_on": [1],
                "acceptance_criteria": "Score >= 7/10, no critical or major issues",
            },
        ],
        "risks": [
            "Edge cases in input validation may need additional iteration",
            "Performance characteristics should be verified with realistic data",
        ],
        "tech_stack": ["python"],
    }
    return _simulate_typing(json.dumps(plan, indent=2))


# ── Coder responses ──────────────────────────────────────────────────────────

def _coder_response(task: str, iteration: int = 0) -> str:
    """Generate a realistic code output."""
    if iteration == 0:
        # First attempt — good but with a minor issue the reviewer will catch
        return _simulate_typing(
            '---FILE: src/rate_limiter.py---\n'
            '"""Rate limiter using the token bucket algorithm."""\n'
            '\n'
            'from __future__ import annotations\n'
            '\n'
            'import time\n'
            'import threading\n'
            'from dataclasses import dataclass, field\n'
            '\n'
            '\n'
            '@dataclass\n'
            'class RateLimiter:\n'
            '    """\n'
            '    Token-bucket rate limiter.\n'
            '\n'
            '    Args:\n'
            '        max_tokens: Maximum tokens in the bucket.\n'
            '        refill_rate: Tokens added per second.\n'
            '    """\n'
            '\n'
            '    max_tokens: int = 10\n'
            '    refill_rate: float = 1.0\n'
            '    _tokens: float = field(init=False)\n'
            '    _last_refill: float = field(init=False)\n'
            '    _lock: threading.Lock = field(init=False, default_factory=threading.Lock)\n'
            '\n'
            '    def __post_init__(self) -> None:\n'
            '        self._tokens = float(self.max_tokens)\n'
            '        self._last_refill = time.monotonic()\n'
            '\n'
            '    def acquire(self, tokens: int = 1) -> bool:\n'
            '        """Try to consume tokens.  Returns True if allowed."""\n'
            '        with self._lock:\n'
            '            self._refill()\n'
            '            if self._tokens >= tokens:\n'
            '                self._tokens -= tokens\n'
            '                return True\n'
            '            return False\n'
            '\n'
            '    def _refill(self) -> None:\n'
            '        now = time.monotonic()\n'
            '        elapsed = now - self._last_refill\n'
            '        self._tokens = min(\n'
            '            self.max_tokens,\n'
            '            self._tokens + elapsed * self.refill_rate,\n'
            '        )\n'
            '        self._last_refill = now\n'
            '---END---\n'
            '\n'
            '## Implementation Notes\n'
            '- Uses token-bucket algorithm for smooth rate limiting\n'
            '- Thread-safe via threading.Lock\n'
            '- monotonic clock prevents issues with system time changes\n'
        )
    else:
        # Revised version — addresses reviewer feedback
        return _simulate_typing(
            '---FILE: src/rate_limiter.py---\n'
            '"""Rate limiter using the token bucket algorithm."""\n'
            '\n'
            'from __future__ import annotations\n'
            '\n'
            'import time\n'
            'import threading\n'
            'from dataclasses import dataclass, field\n'
            '\n'
            '\n'
            '@dataclass\n'
            'class RateLimiter:\n'
            '    """\n'
            '    Thread-safe token-bucket rate limiter.\n'
            '\n'
            '    Args:\n'
            '        max_tokens: Maximum tokens in the bucket (must be > 0).\n'
            '        refill_rate: Tokens added per second (must be > 0).\n'
            '\n'
            '    Raises:\n'
            '        ValueError: If max_tokens or refill_rate are not positive.\n'
            '    """\n'
            '\n'
            '    max_tokens: int = 10\n'
            '    refill_rate: float = 1.0\n'
            '    _tokens: float = field(init=False)\n'
            '    _last_refill: float = field(init=False)\n'
            '    _lock: threading.Lock = field(init=False, default_factory=threading.Lock)\n'
            '\n'
            '    def __post_init__(self) -> None:\n'
            '        if self.max_tokens <= 0:\n'
            '            raise ValueError(f"max_tokens must be positive, got {self.max_tokens}")\n'
            '        if self.refill_rate <= 0:\n'
            '            raise ValueError(f"refill_rate must be positive, got {self.refill_rate}")\n'
            '        self._tokens = float(self.max_tokens)\n'
            '        self._last_refill = time.monotonic()\n'
            '\n'
            '    def acquire(self, tokens: int = 1) -> bool:\n'
            '        """Try to consume tokens.  Returns True if allowed."""\n'
            '        if tokens <= 0:\n'
            '            raise ValueError(f"tokens must be positive, got {tokens}")\n'
            '        with self._lock:\n'
            '            self._refill()\n'
            '            if self._tokens >= tokens:\n'
            '                self._tokens -= tokens\n'
            '                return True\n'
            '            return False\n'
            '\n'
            '    def wait_and_acquire(self, tokens: int = 1, timeout: float = 30.0) -> bool:\n'
            '        """Block until tokens are available or timeout expires."""\n'
            '        if tokens <= 0:\n'
            '            raise ValueError(f"tokens must be positive, got {tokens}")\n'
            '        deadline = time.monotonic() + timeout\n'
            '        while time.monotonic() < deadline:\n'
            '            if self.acquire(tokens):\n'
            '                return True\n'
            '            time.sleep(min(0.05, deadline - time.monotonic()))\n'
            '        return False\n'
            '\n'
            '    @property\n'
            '    def available_tokens(self) -> float:\n'
            '        """Current token count (read-only snapshot)."""\n'
            '        with self._lock:\n'
            '            self._refill()\n'
            '            return self._tokens\n'
            '\n'
            '    def _refill(self) -> None:\n'
            '        now = time.monotonic()\n'
            '        elapsed = now - self._last_refill\n'
            '        self._tokens = min(\n'
            '            self.max_tokens,\n'
            '            self._tokens + elapsed * self.refill_rate,\n'
            '        )\n'
            '        self._last_refill = now\n'
            '---END---\n'
            '\n'
            '## Implementation Notes\n'
            '- Added input validation per reviewer feedback\n'
            '- Added wait_and_acquire() for blocking use cases\n'
            '- Added available_tokens property for monitoring\n'
            '- Thread-safe via threading.Lock\n'
        )


# ── Reviewer responses ────────────────────────────────────────────────────────

def _reviewer_response_first() -> str:
    """First review — finds minor issues, requests revision."""
    review = {
        "verdict": "needs_revision",
        "score": 6,
        "summary": (
            "Solid implementation with good thread safety, but missing input "
            "validation and a blocking acquire variant."
        ),
        "issues": [
            {
                "severity": "major",
                "category": "correctness",
                "description": "No validation on constructor arguments — negative max_tokens or refill_rate would cause silent bugs.",
                "location": "src/rate_limiter.py:RateLimiter.__post_init__",
                "fix": "Add ValueError checks for max_tokens > 0 and refill_rate > 0.",
            },
            {
                "severity": "minor",
                "category": "correctness",
                "description": "acquire() accepts tokens=0 or negative values without error.",
                "location": "src/rate_limiter.py:RateLimiter.acquire",
                "fix": "Validate tokens > 0.",
            },
            {
                "severity": "suggestion",
                "category": "maintainability",
                "description": "Consider adding a blocking wait_and_acquire() method for common use cases.",
                "location": "src/rate_limiter.py",
                "fix": "Add a method that sleeps and retries until tokens are available or timeout.",
            },
        ],
        "strengths": [
            "Clean token-bucket implementation",
            "Thread-safe with proper locking",
            "Good use of monotonic clock",
            "Clear type annotations and docstrings",
        ],
        "required_changes": [
            "Add input validation for constructor arguments",
            "Validate acquire() token count",
        ],
        "suggested_changes": [
            "Add blocking wait_and_acquire() method",
            "Add available_tokens property for observability",
        ],
    }
    return _simulate_typing(json.dumps(review, indent=2))


def _reviewer_response_approved() -> str:
    """Second review — approves after fixes."""
    review = {
        "verdict": "approved",
        "score": 9,
        "summary": (
            "Excellent implementation. All previous issues addressed. "
            "Input validation, blocking acquire, and observability all added cleanly."
        ),
        "issues": [
            {
                "severity": "suggestion",
                "category": "performance",
                "description": "wait_and_acquire uses a polling loop — could use threading.Event for lower latency.",
                "location": "src/rate_limiter.py:RateLimiter.wait_and_acquire",
                "fix": "Optional future enhancement — current approach is fine for most use cases.",
            },
        ],
        "strengths": [
            "Proper input validation with clear error messages",
            "Thread-safe with correct locking granularity",
            "Blocking and non-blocking acquire variants",
            "Clean, readable code with good documentation",
            "Available tokens property for monitoring integration",
        ],
        "required_changes": [],
        "suggested_changes": [
            "Consider Event-based signaling for lower-latency blocking acquire",
        ],
    }
    return _simulate_typing(json.dumps(review, indent=2))


# ── Router ────────────────────────────────────────────────────────────────────

def demo_llm_response(agent_name: str, task: str, iteration: int = 0) -> str:
    """
    Main entry point for demo mode.  Returns a realistic mock response
    based on which agent is calling and the current iteration.
    """
    if agent_name == "planner":
        return _planner_response(task)
    elif agent_name == "coder":
        return _coder_response(task, iteration)
    elif agent_name == "reviewer":
        if iteration == 0:
            return _reviewer_response_first()
        else:
            return _reviewer_response_approved()
    elif agent_name == "architecture_advisor":
        return _simulate_typing(json.dumps({
            "assessment": "Well-structured system with clear separation of concerns.",
            "patterns_identified": ["Repository pattern", "Strategy pattern", "Observer pattern"],
            "recommendations": [
                "Consider adding a circuit breaker for external service calls",
                "Event-driven architecture would improve decoupling",
            ],
            "score": 8,
        }, indent=2))
    elif agent_name == "github_pr":
        return _simulate_typing(json.dumps({
            "title": "feat: add rate limiter implementation",
            "summary": "Adds a thread-safe token-bucket rate limiter with blocking and non-blocking acquire.",
            "risk_level": "low",
            "review_notes": ["Clean implementation", "Good test coverage"],
        }, indent=2))
    else:
        return _simulate_typing(f"Demo response for agent '{agent_name}' on task: {task[:100]}")
