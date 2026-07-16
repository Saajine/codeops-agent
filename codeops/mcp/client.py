"""
Multi-server MCP client + federating tool registry.

Connects to N stdio MCP servers, discovers each server's tools via tools/list
at startup (schema discovery), and federates them into a single registry that
maps every tool name to the server that owns it (multi-server orchestration).

The MCP SDK is async; this codebase is sync. We run one asyncio event loop in
a background thread and bridge across it. All server context managers are
entered and exited inside a single long-lived task (`_serve`) — anyio requires
that — while tool calls are submitted to the same loop from the sync side.

Integration: `registry.anthropic_tools()` + `dispatch()` plug straight into
BaseAgent._run_tool_loop, so agents call federated MCP tools with no change to
the loop itself.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Callable

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)


# ── Federating registry ───────────────────────────────────────────────────────

class FederatedToolRegistry:
    """Holds every discovered tool and the server that owns it."""

    def __init__(self) -> None:
        # tool name -> {"server", "description", "input_schema"}
        self._by_name: dict[str, dict[str, Any]] = {}

    def register(self, server: str, name: str, description: str, input_schema: dict[str, Any]) -> None:
        if name in self._by_name:
            logger.warning(
                "Tool name collision on '%s' (%s vs %s) — keeping the first.",
                name, self._by_name[name]["server"], server,
            )
            return
        self._by_name[name] = {
            "server": server,
            "description": description or "",
            "input_schema": input_schema,
        }

    def owner(self, name: str) -> str | None:
        entry = self._by_name.get(name)
        return entry["server"] if entry else None

    def names(self) -> list[str]:
        return list(self._by_name)

    def anthropic_tools(self) -> list[dict[str, Any]]:
        """Federated tools in Anthropic tool-definition format."""
        return [
            {"name": name, "description": e["description"], "input_schema": e["input_schema"]}
            for name, e in self._by_name.items()
        ]

    def by_server(self) -> dict[str, list[str]]:
        grouped: dict[str, list[str]] = {}
        for name, e in self._by_name.items():
            grouped.setdefault(e["server"], []).append(name)
        return grouped

    def __len__(self) -> int:
        return len(self._by_name)


# ── Multi-server client ───────────────────────────────────────────────────────

class MCPClient:
    """Manages several stdio MCP servers and federates their tools."""

    def __init__(self, servers: dict[str, StdioServerParameters]) -> None:
        self._servers = servers
        self.registry = FederatedToolRegistry()

        self._sessions: dict[str, ClientSession] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._shutdown: asyncio.Event | None = None
        self._connected = threading.Event()
        self._error: Exception | None = None

    # -- lifecycle ------------------------------------------------------------

    def start(self, timeout: float = 30.0) -> "MCPClient":
        """Spawn the servers, initialize sessions, and run tools/list discovery."""
        self._thread = threading.Thread(target=self._run, name="mcp-loop", daemon=True)
        self._thread.start()
        if not self._connected.wait(timeout=timeout):
            raise RuntimeError("MCP servers did not start within timeout")
        if self._error:
            raise self._error
        logger.info(
            "MCP discovery: %d tools across %d servers %s",
            len(self.registry), len(self._servers), self.registry.by_server(),
        )
        return self

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve())
        finally:
            self._loop.close()

    async def _serve(self) -> None:
        """One task owns every server context for the client's whole lifetime."""
        self._shutdown = asyncio.Event()
        try:
            async with AsyncExitStack() as stack:
                for name, params in self._servers.items():
                    read, write = await stack.enter_async_context(stdio_client(params))
                    session = await stack.enter_async_context(ClientSession(read, write))
                    await session.initialize()
                    self._sessions[name] = session

                    # tools/list == schema discovery, literally.
                    listed = await session.list_tools()
                    for tool in listed.tools:
                        self.registry.register(
                            server=name,
                            name=tool.name,
                            description=tool.description or "",
                            input_schema=tool.inputSchema,
                        )
                self._connected.set()
                await self._shutdown.wait()  # hold contexts open until stop()
        except Exception as exc:  # noqa: BLE001 — report to the waiting start()
            self._error = exc
            self._connected.set()

    def stop(self) -> None:
        if self._loop and self._shutdown and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._shutdown.set)
        if self._thread:
            self._thread.join(timeout=10)

    def __enter__(self) -> "MCPClient":
        return self.start()

    def __exit__(self, *exc: Any) -> None:
        self.stop()

    # -- tool calls -----------------------------------------------------------

    def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Route a tool call to the owning server; return its text result.

        Raises RuntimeError on an MCP tool error so the agent loop marks it as
        an error tool_result and lets the model recover.
        """
        server = self.registry.owner(name)
        if server is None:
            raise ValueError(f"No MCP server owns tool '{name}'")
        if self._loop is None:
            raise RuntimeError("MCP client is not started")
        future = asyncio.run_coroutine_threadsafe(
            self._call(server, name, arguments), self._loop
        )
        return future.result(timeout=60)

    async def _call(self, server: str, name: str, arguments: dict[str, Any]) -> str:
        result = await self._sessions[server].call_tool(name, arguments)
        text = "\n".join(
            block.text for block in result.content if getattr(block, "type", None) == "text"
        )
        if result.isError:
            raise RuntimeError(text or f"tool '{name}' returned an error")
        return text

    def dispatch(self) -> dict[str, Callable[..., str]]:
        """A name -> callable map for BaseAgent._run_tool_loop.

        Each callable forwards its keyword args to the owning server. The `_n`
        default binds the tool name per-entry (avoids the classic closure bug).
        """
        return {
            name: (lambda _n=name, **kwargs: self.call_tool(_n, kwargs))
            for name in self.registry.names()
        }


# ── Default wiring ────────────────────────────────────────────────────────────

# Project root (…/codeops-agent), so subprocesses can `-m codeops.…` regardless
# of the working directory or whether the package is installed.
_PROJECT_ROOT = str(Path(__file__).resolve().parents[2])


def default_servers(fs_root: str | None = None) -> dict[str, StdioServerParameters]:
    """The two built-in servers, launched with this interpreter and env."""
    env = os.environ.copy()
    env["PYTHONPATH"] = _PROJECT_ROOT + os.pathsep + env.get("PYTHONPATH", "")
    if fs_root:
        env["CODEOPS_FS_ROOT"] = fs_root
    return {
        "github": StdioServerParameters(
            command=sys.executable,
            args=["-m", "codeops.mcp.servers.github_server"],
            env=env,
        ),
        "filesystem": StdioServerParameters(
            command=sys.executable,
            args=["-m", "codeops.mcp.servers.filesystem_server"],
            env=env,
        ),
    }
