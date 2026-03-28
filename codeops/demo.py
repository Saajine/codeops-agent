"""
Demo mode — realistic mock responses for running CodeOps without an API key.

When CODEOPS_DEMO=1, the BaseAgent._call_llm() method uses these responses
instead of hitting the Anthropic API.  This lets you demo the full pipeline
in interviews, CI, or offline environments.

Task-aware: parses task keywords to generate contextual code examples
instead of always returning a rate limiter.
"""

from __future__ import annotations

import json
import re
import time
import random

# ── Simulated latency ──────────────────────────────────────────────────────────

_SPEED = 0.02  # seconds per "token" for realistic streaming feel


def _simulate_typing(text: str) -> str:
    """Add a small delay to make demo mode feel realistic."""
    delay = min(len(text) * _SPEED * 0.01, 2.0)
    time.sleep(delay)
    return text


# ── Task classification ──────────────────────────────────────────────────────

_TASK_PATTERNS: list[tuple[str, str]] = [
    (r"rate.?limit", "rate_limiter"),
    (r"cache|lru|ttl", "cache"),
    (r"auth|login|jwt|token|session|oauth", "auth"),
    (r"api|endpoint|rest|fastapi|flask|route", "api"),
    (r"queue|worker|job|celery|async.*task", "queue"),
    (r"database|db|sql|orm|model|schema|migration", "database"),
    (r"test|pytest|unittest|coverage|spec", "test"),
    (r"websocket|socket|realtime|real.?time|chat", "websocket"),
]


def _classify_task(task: str) -> str:
    """Determine task type from keywords. Falls back to 'rate_limiter'."""
    lower = task.lower()
    for pattern, task_type in _TASK_PATTERNS:
        if re.search(pattern, lower):
            return task_type
    return "rate_limiter"


# ── Planner responses ─────────────────────────────────────────────────────────

def _planner_response(task: str) -> str:
    """Generate a realistic planner JSON response based on the task."""
    title = task.strip().split("\n")[0][:60]
    task_type = _classify_task(task)

    # Contextual plan details based on task type
    plan_details = {
        "rate_limiter": {
            "desc": "Implement a thread-safe rate limiter using token bucket algorithm.",
            "steps_desc": "Token bucket implementation with threading support",
            "tech": ["python", "threading"],
        },
        "cache": {
            "desc": "Build a thread-safe LRU cache with TTL expiration.",
            "steps_desc": "LRU cache with O(1) operations and time-based eviction",
            "tech": ["python", "collections", "threading"],
        },
        "auth": {
            "desc": "Implement JWT-based authentication middleware with secure token handling.",
            "steps_desc": "Auth middleware with JWT validation, refresh tokens, and role-based access",
            "tech": ["python", "jwt", "bcrypt"],
        },
        "api": {
            "desc": "Build a RESTful API with input validation and error handling.",
            "steps_desc": "API endpoints with Pydantic models, middleware, and structured error responses",
            "tech": ["python", "fastapi", "pydantic"],
        },
        "queue": {
            "desc": "Build an async task queue with retry logic and dead letter handling.",
            "steps_desc": "Task queue with configurable retries, backoff, and failure isolation",
            "tech": ["python", "asyncio", "redis"],
        },
        "database": {
            "desc": "Build a repository pattern with connection pooling and migrations.",
            "steps_desc": "Database layer with repository pattern, connection pooling, and schema management",
            "tech": ["python", "sqlite3", "sqlalchemy"],
        },
        "test": {
            "desc": "Generate comprehensive test suite with fixtures and edge cases.",
            "steps_desc": "Test generation with parametrized tests, mocking, and coverage targets",
            "tech": ["python", "pytest", "pytest-mock"],
        },
        "websocket": {
            "desc": "Build a WebSocket server with rooms, broadcasting, and reconnection.",
            "steps_desc": "WebSocket handler with room management and message broadcasting",
            "tech": ["python", "websockets", "asyncio"],
        },
    }

    details = plan_details.get(task_type, plan_details["rate_limiter"])

    plan = {
        "title": title,
        "description": details["desc"],
        "estimated_complexity": "medium",
        "steps": [
            {
                "id": 1,
                "title": "Core implementation",
                "description": details["steps_desc"],
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
        "tech_stack": details["tech"],
    }
    return _simulate_typing(json.dumps(plan, indent=2))


# ── Coder responses ──────────────────────────────────────────────────────────

_CODE_TEMPLATES: dict[str, tuple[str, str]] = {
    "rate_limiter": (
        "src/rate_limiter.py",
        '"""Rate limiter using the token bucket algorithm."""\n'
        "\n"
        "from __future__ import annotations\n"
        "\n"
        "import time\n"
        "import threading\n"
        "from dataclasses import dataclass, field\n"
        "\n"
        "\n"
        "@dataclass\n"
        "class RateLimiter:\n"
        '    """Thread-safe token-bucket rate limiter."""\n'
        "\n"
        "    max_tokens: int = 10\n"
        "    refill_rate: float = 1.0\n"
        "    _tokens: float = field(init=False)\n"
        "    _last_refill: float = field(init=False)\n"
        "    _lock: threading.Lock = field(init=False, default_factory=threading.Lock)\n"
        "\n"
        "    def __post_init__(self) -> None:\n"
        "        self._tokens = float(self.max_tokens)\n"
        "        self._last_refill = time.monotonic()\n"
        "\n"
        "    def acquire(self, tokens: int = 1) -> bool:\n"
        '        """Try to consume tokens.  Returns True if allowed."""\n'
        "        with self._lock:\n"
        "            self._refill()\n"
        "            if self._tokens >= tokens:\n"
        "                self._tokens -= tokens\n"
        "                return True\n"
        "            return False\n"
        "\n"
        "    def _refill(self) -> None:\n"
        "        now = time.monotonic()\n"
        "        elapsed = now - self._last_refill\n"
        "        self._tokens = min(\n"
        "            self.max_tokens,\n"
        "            self._tokens + elapsed * self.refill_rate,\n"
        "        )\n"
        "        self._last_refill = now\n"
    ),
    "cache": (
        "src/lru_cache.py",
        '"""Thread-safe LRU cache with TTL expiration."""\n'
        "\n"
        "from __future__ import annotations\n"
        "\n"
        "import time\n"
        "import threading\n"
        "from collections import OrderedDict\n"
        "from dataclasses import dataclass, field\n"
        "from typing import Any, Hashable\n"
        "\n"
        "\n"
        "@dataclass\n"
        "class CacheEntry:\n"
        "    value: Any\n"
        "    expires_at: float\n"
        "\n"
        "\n"
        "class LRUCache:\n"
        '    """Thread-safe LRU cache with time-based eviction."""\n'
        "\n"
        "    def __init__(self, capacity: int = 128, ttl: float = 300.0) -> None:\n"
        "        if capacity <= 0:\n"
        '            raise ValueError(f"capacity must be positive, got {capacity}")\n'
        "        self._capacity = capacity\n"
        "        self._ttl = ttl\n"
        "        self._store: OrderedDict[Hashable, CacheEntry] = OrderedDict()\n"
        "        self._lock = threading.Lock()\n"
        "        self._hits = 0\n"
        "        self._misses = 0\n"
        "\n"
        "    def get(self, key: Hashable) -> Any | None:\n"
        '        """Retrieve a value, returning None if missing or expired."""\n'
        "        with self._lock:\n"
        "            entry = self._store.get(key)\n"
        "            if entry is None:\n"
        "                self._misses += 1\n"
        "                return None\n"
        "            if time.monotonic() > entry.expires_at:\n"
        "                del self._store[key]\n"
        "                self._misses += 1\n"
        "                return None\n"
        "            self._store.move_to_end(key)\n"
        "            self._hits += 1\n"
        "            return entry.value\n"
        "\n"
        "    def put(self, key: Hashable, value: Any) -> None:\n"
        '        """Insert or update a cache entry."""\n'
        "        with self._lock:\n"
        "            if key in self._store:\n"
        "                self._store.move_to_end(key)\n"
        "            self._store[key] = CacheEntry(\n"
        "                value=value, expires_at=time.monotonic() + self._ttl\n"
        "            )\n"
        "            if len(self._store) > self._capacity:\n"
        "                self._store.popitem(last=False)\n"
        "\n"
        "    @property\n"
        "    def hit_rate(self) -> float:\n"
        "        total = self._hits + self._misses\n"
        "        return self._hits / total if total > 0 else 0.0\n"
    ),
    "auth": (
        "src/auth_middleware.py",
        '"""JWT authentication middleware with role-based access control."""\n'
        "\n"
        "from __future__ import annotations\n"
        "\n"
        "import hashlib\n"
        "import hmac\n"
        "import json\n"
        "import time\n"
        "import base64\n"
        "from dataclasses import dataclass\n"
        "from typing import Any\n"
        "\n"
        "\n"
        "@dataclass\n"
        "class AuthUser:\n"
        '    """Authenticated user context."""\n'
        "    user_id: str\n"
        "    email: str\n"
        "    roles: list[str]\n"
        "\n"
        "    def has_role(self, role: str) -> bool:\n"
        "        return role in self.roles\n"
        "\n"
        "\n"
        "class AuthError(Exception):\n"
        '    """Base authentication error."""\n'
        "    def __init__(self, message: str, status_code: int = 401) -> None:\n"
        "        super().__init__(message)\n"
        "        self.status_code = status_code\n"
        "\n"
        "\n"
        "class AuthMiddleware:\n"
        '    """Validates JWT tokens and enforces role-based access."""\n'
        "\n"
        "    def __init__(self, secret: str, issuer: str = \"codeops\") -> None:\n"
        "        if not secret:\n"
        '            raise ValueError("JWT secret must not be empty")\n'
        "        self._secret = secret.encode()\n"
        "        self._issuer = issuer\n"
        "\n"
        "    def authenticate(self, token: str) -> AuthUser:\n"
        '        """Validate a JWT token and return the authenticated user."""\n'
        "        try:\n"
        '            parts = token.split(".")\n'
        "            if len(parts) != 3:\n"
        '                raise AuthError("Malformed token")\n'
        "            header_b64, payload_b64, signature = parts\n"
        '            expected_sig = hmac.new(\n'
        '                self._secret, f"{header_b64}.{payload_b64}".encode(), hashlib.sha256\n'
        "            ).hexdigest()\n"
        "            if not hmac.compare_digest(signature, expected_sig):\n"
        '                raise AuthError("Invalid signature")\n'
        "            payload = json.loads(base64.urlsafe_b64decode(payload_b64 + \"==\"))\n"
        '            if payload.get("exp", 0) < time.time():\n'
        '                raise AuthError("Token expired")\n'
        "            return AuthUser(\n"
        '                user_id=payload["sub"],\n'
        '                email=payload.get("email", ""),\n'
        '                roles=payload.get("roles", []),\n'
        "            )\n"
        "        except (KeyError, json.JSONDecodeError) as exc:\n"
        '            raise AuthError(f"Invalid token payload: {exc}") from exc\n'
        "\n"
        "    def require_role(self, user: AuthUser, role: str) -> None:\n"
        '        """Raise 403 if user lacks the required role."""\n'
        "        if not user.has_role(role):\n"
        '            raise AuthError(f"Missing required role: {role}", status_code=403)\n'
    ),
    "api": (
        "src/api.py",
        '"""RESTful API with input validation and structured error handling."""\n'
        "\n"
        "from __future__ import annotations\n"
        "\n"
        "from dataclasses import dataclass, field\n"
        "from typing import Any\n"
        "from datetime import datetime\n"
        "\n"
        "\n"
        "@dataclass\n"
        "class APIResponse:\n"
        '    """Standardised API response envelope."""\n'
        "    data: Any = None\n"
        "    error: str | None = None\n"
        "    status: int = 200\n"
        "    meta: dict[str, Any] = field(default_factory=dict)\n"
        "\n"
        "    def to_dict(self) -> dict[str, Any]:\n"
        "        result: dict[str, Any] = {\"status\": self.status}\n"
        "        if self.error:\n"
        "            result[\"error\"] = self.error\n"
        "        else:\n"
        "            result[\"data\"] = self.data\n"
        "        if self.meta:\n"
        "            result[\"meta\"] = self.meta\n"
        "        return result\n"
        "\n"
        "\n"
        "@dataclass\n"
        "class Item:\n"
        '    """Domain model with validation."""\n'
        "    id: str\n"
        "    name: str\n"
        "    price: float\n"
        "    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())\n"
        "\n"
        "    def __post_init__(self) -> None:\n"
        "        if not self.name.strip():\n"
        '            raise ValueError("Item name must not be empty")\n'
        "        if self.price < 0:\n"
        '            raise ValueError(f"Price must be non-negative, got {self.price}")\n'
        "\n"
        "\n"
        "class ItemService:\n"
        '    """In-memory CRUD service with validation."""\n'
        "\n"
        "    def __init__(self) -> None:\n"
        "        self._items: dict[str, Item] = {}\n"
        "\n"
        "    def create(self, item_id: str, name: str, price: float) -> APIResponse:\n"
        "        if item_id in self._items:\n"
        '            return APIResponse(error="Item already exists", status=409)\n'
        "        try:\n"
        "            item = Item(id=item_id, name=name, price=price)\n"
        "        except ValueError as exc:\n"
        "            return APIResponse(error=str(exc), status=400)\n"
        "        self._items[item_id] = item\n"
        "        return APIResponse(data=item.__dict__, status=201)\n"
        "\n"
        "    def get(self, item_id: str) -> APIResponse:\n"
        "        item = self._items.get(item_id)\n"
        "        if not item:\n"
        '            return APIResponse(error="Item not found", status=404)\n'
        "        return APIResponse(data=item.__dict__)\n"
        "\n"
        "    def list_items(self, limit: int = 50) -> APIResponse:\n"
        "        items = list(self._items.values())[:limit]\n"
        "        return APIResponse(\n"
        "            data=[i.__dict__ for i in items],\n"
        '            meta={"total": len(self._items), "limit": limit},\n'
        "        )\n"
    ),
    "queue": (
        "src/task_queue.py",
        '"""Async task queue with retry logic and dead letter handling."""\n'
        "\n"
        "from __future__ import annotations\n"
        "\n"
        "import time\n"
        "import uuid\n"
        "import threading\n"
        "from collections import deque\n"
        "from dataclasses import dataclass, field\n"
        "from enum import Enum\n"
        "from typing import Any, Callable\n"
        "\n"
        "\n"
        "class TaskStatus(Enum):\n"
        '    PENDING = "pending"\n'
        '    RUNNING = "running"\n'
        '    SUCCESS = "success"\n'
        '    FAILED = "failed"\n'
        '    DEAD = "dead"\n'
        "\n"
        "\n"
        "@dataclass\n"
        "class Task:\n"
        "    id: str = field(default_factory=lambda: str(uuid.uuid4()))\n"
        "    name: str = \"\"\n"
        "    payload: dict[str, Any] = field(default_factory=dict)\n"
        "    status: TaskStatus = TaskStatus.PENDING\n"
        "    retries: int = 0\n"
        "    max_retries: int = 3\n"
        "    error: str = \"\"\n"
        "\n"
        "\n"
        "class TaskQueue:\n"
        '    """Simple task queue with retry and dead letter support."""\n'
        "\n"
        "    def __init__(self, max_retries: int = 3) -> None:\n"
        "        self._queue: deque[Task] = deque()\n"
        "        self._dead_letter: list[Task] = []\n"
        "        self._completed: list[Task] = []\n"
        "        self._max_retries = max_retries\n"
        "        self._lock = threading.Lock()\n"
        "\n"
        "    def enqueue(self, name: str, payload: dict[str, Any] | None = None) -> Task:\n"
        "        task = Task(name=name, payload=payload or {}, max_retries=self._max_retries)\n"
        "        with self._lock:\n"
        "            self._queue.append(task)\n"
        "        return task\n"
        "\n"
        "    def process(self, handler: Callable[[Task], None]) -> Task | None:\n"
        "        with self._lock:\n"
        "            if not self._queue:\n"
        "                return None\n"
        "            task = self._queue.popleft()\n"
        "        task.status = TaskStatus.RUNNING\n"
        "        try:\n"
        "            handler(task)\n"
        "            task.status = TaskStatus.SUCCESS\n"
        "            self._completed.append(task)\n"
        "        except Exception as exc:\n"
        "            task.retries += 1\n"
        "            task.error = str(exc)\n"
        "            if task.retries >= task.max_retries:\n"
        "                task.status = TaskStatus.DEAD\n"
        "                self._dead_letter.append(task)\n"
        "            else:\n"
        "                task.status = TaskStatus.PENDING\n"
        "                with self._lock:\n"
        "                    self._queue.append(task)\n"
        "        return task\n"
        "\n"
        "    @property\n"
        "    def dead_letters(self) -> list[Task]:\n"
        "        return list(self._dead_letter)\n"
    ),
    "database": (
        "src/repository.py",
        '"""Repository pattern with connection pooling."""\n'
        "\n"
        "from __future__ import annotations\n"
        "\n"
        "import sqlite3\n"
        "import threading\n"
        "from contextlib import contextmanager\n"
        "from dataclasses import dataclass\n"
        "from typing import Any, Generator\n"
        "\n"
        "\n"
        "@dataclass\n"
        "class User:\n"
        "    id: int\n"
        "    username: str\n"
        "    email: str\n"
        "\n"
        "\n"
        "class Database:\n"
        '    """SQLite wrapper with thread-local connections."""\n'
        "\n"
        "    def __init__(self, path: str = \":memory:\") -> None:\n"
        "        self._path = path\n"
        "        self._local = threading.local()\n"
        "\n"
        "    @contextmanager\n"
        "    def connection(self) -> Generator[sqlite3.Connection, None, None]:\n"
        "        if not hasattr(self._local, \"conn\"):\n"
        "            self._local.conn = sqlite3.connect(self._path)\n"
        "            self._local.conn.row_factory = sqlite3.Row\n"
        "        yield self._local.conn\n"
        "\n"
        "    def execute(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:\n"
        "        with self.connection() as conn:\n"
        "            cursor = conn.execute(sql, params)\n"
        "            conn.commit()\n"
        "            return [dict(row) for row in cursor.fetchall()]\n"
        "\n"
        "\n"
        "class UserRepository:\n"
        '    """CRUD repository for User entities."""\n'
        "\n"
        "    def __init__(self, db: Database) -> None:\n"
        "        self._db = db\n"
        "        self._ensure_table()\n"
        "\n"
        "    def _ensure_table(self) -> None:\n"
        "        self._db.execute(\n"
        '            "CREATE TABLE IF NOT EXISTS users "\n'
        '            "(id INTEGER PRIMARY KEY, username TEXT UNIQUE, email TEXT)"\n'
        "        )\n"
        "\n"
        "    def create(self, username: str, email: str) -> User:\n"
        "        rows = self._db.execute(\n"
        '            "INSERT INTO users (username, email) VALUES (?, ?) RETURNING *",\n'
        "            (username, email),\n"
        "        )\n"
        "        row = rows[0]\n"
        '        return User(id=row["id"], username=row["username"], email=row["email"])\n'
        "\n"
        "    def get_by_id(self, user_id: int) -> User | None:\n"
        '        rows = self._db.execute("SELECT * FROM users WHERE id = ?", (user_id,))\n'
        "        if not rows:\n"
        "            return None\n"
        "        row = rows[0]\n"
        '        return User(id=row["id"], username=row["username"], email=row["email"])\n'
    ),
    "websocket": (
        "src/ws_server.py",
        '"""WebSocket server with rooms and broadcasting."""\n'
        "\n"
        "from __future__ import annotations\n"
        "\n"
        "import json\n"
        "import uuid\n"
        "from dataclasses import dataclass, field\n"
        "from typing import Any\n"
        "\n"
        "\n"
        "@dataclass\n"
        "class Client:\n"
        "    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])\n"
        "    username: str = \"anonymous\"\n"
        "    rooms: set[str] = field(default_factory=set)\n"
        "\n"
        "\n"
        "class RoomManager:\n"
        '    """Manages WebSocket rooms and message broadcasting."""\n'
        "\n"
        "    def __init__(self) -> None:\n"
        "        self._rooms: dict[str, set[str]] = {}  # room_name -> {client_ids}\n"
        "        self._clients: dict[str, Client] = {}  # client_id -> Client\n"
        "        self._outbox: list[tuple[str, dict[str, Any]]] = []  # (client_id, message)\n"
        "\n"
        "    def connect(self, username: str = \"anonymous\") -> Client:\n"
        "        client = Client(username=username)\n"
        "        self._clients[client.id] = client\n"
        "        return client\n"
        "\n"
        "    def disconnect(self, client_id: str) -> None:\n"
        "        client = self._clients.pop(client_id, None)\n"
        "        if client:\n"
        "            for room in client.rooms:\n"
        "                self._rooms.get(room, set()).discard(client_id)\n"
        "\n"
        "    def join(self, client_id: str, room: str) -> None:\n"
        "        if client_id not in self._clients:\n"
        '            raise ValueError(f"Unknown client: {client_id}")\n'
        "        self._rooms.setdefault(room, set()).add(client_id)\n"
        "        self._clients[client_id].rooms.add(room)\n"
        "\n"
        "    def broadcast(self, room: str, message: dict[str, Any], exclude: str | None = None) -> int:\n"
        '        """Send a message to all clients in a room. Returns count sent."""\n'
        "        members = self._rooms.get(room, set())\n"
        "        count = 0\n"
        "        for cid in members:\n"
        "            if cid != exclude:\n"
        "                self._outbox.append((cid, message))\n"
        "                count += 1\n"
        "        return count\n"
        "\n"
        "    def drain_outbox(self) -> list[tuple[str, dict[str, Any]]]:\n"
        "        messages = list(self._outbox)\n"
        "        self._outbox.clear()\n"
        "        return messages\n"
    ),
}

# Revision templates add validation and extra features
_CODE_REVISIONS: dict[str, tuple[str, str]] = {
    "rate_limiter": (
        "src/rate_limiter.py",
        '"""Rate limiter using the token bucket algorithm."""\n'
        "\n"
        "from __future__ import annotations\n"
        "\n"
        "import time\n"
        "import threading\n"
        "from dataclasses import dataclass, field\n"
        "\n"
        "\n"
        "@dataclass\n"
        "class RateLimiter:\n"
        '    """\n'
        "    Thread-safe token-bucket rate limiter.\n"
        "\n"
        "    Raises:\n"
        "        ValueError: If max_tokens or refill_rate are not positive.\n"
        '    """\n'
        "\n"
        "    max_tokens: int = 10\n"
        "    refill_rate: float = 1.0\n"
        "    _tokens: float = field(init=False)\n"
        "    _last_refill: float = field(init=False)\n"
        "    _lock: threading.Lock = field(init=False, default_factory=threading.Lock)\n"
        "\n"
        "    def __post_init__(self) -> None:\n"
        "        if self.max_tokens <= 0:\n"
        '            raise ValueError(f"max_tokens must be positive, got {self.max_tokens}")\n'
        "        if self.refill_rate <= 0:\n"
        '            raise ValueError(f"refill_rate must be positive, got {self.refill_rate}")\n'
        "        self._tokens = float(self.max_tokens)\n"
        "        self._last_refill = time.monotonic()\n"
        "\n"
        "    def acquire(self, tokens: int = 1) -> bool:\n"
        '        """Try to consume tokens.  Returns True if allowed."""\n'
        "        if tokens <= 0:\n"
        '            raise ValueError(f"tokens must be positive, got {tokens}")\n'
        "        with self._lock:\n"
        "            self._refill()\n"
        "            if self._tokens >= tokens:\n"
        "                self._tokens -= tokens\n"
        "                return True\n"
        "            return False\n"
        "\n"
        "    def wait_and_acquire(self, tokens: int = 1, timeout: float = 30.0) -> bool:\n"
        '        """Block until tokens are available or timeout expires."""\n'
        "        if tokens <= 0:\n"
        '            raise ValueError(f"tokens must be positive, got {tokens}")\n'
        "        deadline = time.monotonic() + timeout\n"
        "        while time.monotonic() < deadline:\n"
        "            if self.acquire(tokens):\n"
        "                return True\n"
        "            time.sleep(min(0.05, deadline - time.monotonic()))\n"
        "        return False\n"
        "\n"
        "    @property\n"
        "    def available_tokens(self) -> float:\n"
        "        with self._lock:\n"
        "            self._refill()\n"
        "            return self._tokens\n"
        "\n"
        "    def _refill(self) -> None:\n"
        "        now = time.monotonic()\n"
        "        elapsed = now - self._last_refill\n"
        "        self._tokens = min(\n"
        "            self.max_tokens,\n"
        "            self._tokens + elapsed * self.refill_rate,\n"
        "        )\n"
        "        self._last_refill = now\n"
    ),
}


def _coder_response(task: str, iteration: int = 0) -> str:
    """Generate a realistic code output based on the task type."""
    task_type = _classify_task(task)

    if iteration == 0:
        fname, code = _CODE_TEMPLATES.get(task_type, _CODE_TEMPLATES["rate_limiter"])
    else:
        # Use revision if available, otherwise just return the template
        fname, code = _CODE_REVISIONS.get(
            task_type,
            _CODE_TEMPLATES.get(task_type, _CODE_TEMPLATES["rate_limiter"]),
        )

    notes_first = (
        "## Implementation Notes\n"
        "- Clean implementation with type annotations\n"
        "- Thread-safe via threading.Lock\n"
        "- Handles basic edge cases\n"
    )
    notes_revised = (
        "## Implementation Notes\n"
        "- Added input validation per reviewer feedback\n"
        "- Enhanced API with additional methods\n"
        "- Thread-safe via threading.Lock\n"
    )

    notes = notes_revised if iteration > 0 else notes_first
    return _simulate_typing(f"---FILE: {fname}---\n{code}---END---\n\n{notes}")


# ── Reviewer responses ────────────────────────────────────────────────────────

def _reviewer_response_first(task: str) -> str:
    """First review — finds minor issues, requests revision."""
    task_type = _classify_task(task)
    fname = _CODE_TEMPLATES.get(task_type, _CODE_TEMPLATES["rate_limiter"])[0]

    review = {
        "verdict": "needs_revision",
        "score": 6,
        "summary": (
            "Solid implementation with good structure, but missing input "
            "validation and could benefit from additional error handling."
        ),
        "issues": [
            {
                "severity": "major",
                "category": "correctness",
                "description": "No validation on constructor arguments — invalid values would cause silent bugs.",
                "location": fname,
                "fix": "Add ValueError checks for all constructor parameters.",
            },
            {
                "severity": "minor",
                "category": "correctness",
                "description": "Public methods accept zero or negative values without error.",
                "location": fname,
                "fix": "Validate inputs in public methods.",
            },
            {
                "severity": "suggestion",
                "category": "maintainability",
                "description": "Consider adding convenience methods for common use cases.",
                "location": fname,
                "fix": "Add helper methods to improve API ergonomics.",
            },
        ],
        "strengths": [
            "Clean implementation with good structure",
            "Thread-safe with proper locking",
            "Clear type annotations and docstrings",
        ],
        "required_changes": [
            "Add input validation for constructor arguments",
            "Validate public method parameters",
        ],
        "suggested_changes": [
            "Add convenience methods",
            "Add observability hooks (metrics/properties)",
        ],
    }
    return _simulate_typing(json.dumps(review, indent=2))


def _reviewer_response_approved(task: str) -> str:
    """Second review — approves after fixes."""
    review = {
        "verdict": "approved",
        "score": 9,
        "summary": (
            "Excellent implementation. All previous issues addressed. "
            "Input validation, error handling, and API completeness are all solid."
        ),
        "issues": [
            {
                "severity": "suggestion",
                "category": "performance",
                "description": "Polling loop could use Event-based signaling for lower latency.",
                "location": "general",
                "fix": "Optional future enhancement — current approach is fine.",
            },
        ],
        "strengths": [
            "Proper input validation with clear error messages",
            "Thread-safe with correct locking granularity",
            "Clean, readable code with good documentation",
            "Comprehensive API with good ergonomics",
        ],
        "required_changes": [],
        "suggested_changes": [
            "Consider Event-based signaling for lower latency in blocking operations",
        ],
    }
    return _simulate_typing(json.dumps(review, indent=2))


# ── Test generator responses ────────────────────────────────────────────────

def _test_generator_response(task: str) -> str:
    """Generate a realistic test suite based on the task."""
    task_type = _classify_task(task)
    fname = _CODE_TEMPLATES.get(task_type, _CODE_TEMPLATES["rate_limiter"])[0]
    module = fname.replace("src/", "").replace(".py", "")

    # Build a contextual test suite
    test_code = (
        f'"""Auto-generated test suite for {module}."""\n'
        "\n"
        "from __future__ import annotations\n"
        "\n"
        "import pytest\n"
        "import threading\n"
        "import time\n"
        f"\n"
        f"from {module} import *\n"
        "\n"
        "\n"
        "class TestBasicFunctionality:\n"
        '    """Core feature tests."""\n'
        "\n"
        "    def test_creation_with_defaults(self):\n"
        f"        obj = {module.title().replace('_', '')}()\n"
        "        assert obj is not None\n"
        "\n"
        "    def test_creation_with_custom_params(self):\n"
        f"        # Verify custom initialization works\n"
        "        assert True  # Parametrized in real generation\n"
        "\n"
        "    def test_basic_operation(self):\n"
        "        # Verify primary operation works\n"
        "        assert True\n"
        "\n"
        "\n"
        "class TestEdgeCases:\n"
        '    """Edge case and boundary tests."""\n'
        "\n"
        "    def test_invalid_negative_input(self):\n"
        "        with pytest.raises(ValueError):\n"
        f"            {module.title().replace('_', '')}(-1)  # Should reject negative\n"
        "\n"
        "    def test_zero_input(self):\n"
        "        with pytest.raises(ValueError):\n"
        f"            {module.title().replace('_', '')}(0)  # Should reject zero\n"
        "\n"
        "    def test_boundary_values(self):\n"
        "        # Test at capacity limits\n"
        "        assert True\n"
        "\n"
        "\n"
        "class TestThreadSafety:\n"
        '    """Concurrency tests."""\n'
        "\n"
        "    def test_concurrent_access(self):\n"
        f"        obj = {module.title().replace('_', '')}()\n"
        "        errors: list[Exception] = []\n"
        "\n"
        "        def worker():\n"
        "            try:\n"
        "                for _ in range(100):\n"
        "                    pass  # Exercise main operations\n"
        "            except Exception as e:\n"
        "                errors.append(e)\n"
        "\n"
        "        threads = [threading.Thread(target=worker) for _ in range(10)]\n"
        "        for t in threads:\n"
        "            t.start()\n"
        "        for t in threads:\n"
        "            t.join()\n"
        "        assert len(errors) == 0\n"
    )

    test_meta = json.dumps({
        "test_file": f"tests/test_{module}.py",
        "test_count": 7,
        "coverage_estimate": "85%",
        "categories": ["basic", "edge_cases", "thread_safety"],
        "framework": "pytest",
    }, indent=2)

    return _simulate_typing(
        f"---FILE: tests/test_{module}.py---\n"
        f"{test_code}"
        f"---END---\n\n"
        f"## Test Generation Summary\n"
        f"```json\n{test_meta}\n```\n"
    )


# ── Router ────────────────────────────────────────────────────────────────────

def demo_llm_response(agent_name: str, task: str, iteration: int = 0) -> str:
    """
    Main entry point for demo mode.  Returns a realistic mock response
    based on which agent is calling, the task content, and the current iteration.
    """
    if agent_name == "planner":
        return _planner_response(task)
    elif agent_name == "coder":
        return _coder_response(task, iteration)
    elif agent_name == "reviewer":
        if iteration == 0:
            return _reviewer_response_first(task)
        else:
            return _reviewer_response_approved(task)
    elif agent_name == "tester":
        return _test_generator_response(task)
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
        task_type = _classify_task(task)
        return _simulate_typing(json.dumps({
            "title": f"feat: add {task_type.replace('_', ' ')} implementation",
            "summary": f"Adds a production-ready {task_type.replace('_', ' ')} with validation and tests.",
            "risk_level": "low",
            "review_notes": ["Clean implementation", "Good test coverage"],
        }, indent=2))
    else:
        return _simulate_typing(f"Demo response for agent '{agent_name}' on task: {task[:100]}")
