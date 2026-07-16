"""
MCP infrastructure demo — no API key or network required.

Starts both stdio MCP servers, shows schema discovery (tools/list) federated
across them, calls a filesystem tool over the protocol boundary, and reports
the latency the boundary costs vs an in-process connector call.

    python examples/mcp_demo.py
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from codeops.mcp.client import MCPClient, default_servers
from codeops.mcp.connectors import FileSystemConnector


def main() -> int:
    root = tempfile.mkdtemp(prefix="mcp-demo-")

    with MCPClient(default_servers(fs_root=root)) as client:
        # 1. Schema discovery, federated across servers.
        print("Discovered tools (tools/list) by server:")
        for server, names in client.registry.by_server().items():
            print(f"  {server:<11}: {', '.join(sorted(names))}")
        print(f"  total federated: {len(client.registry)} tools\n")

        # 2. Call a tool over the boundary.
        client.call_tool("write_file", {"path": "hello.txt", "content": "over the boundary"})
        got = client.call_tool("read_file", {"path": "hello.txt"})
        print(f"read_file via MCP -> {got!r}\n")

        # 3. What did the boundary cost?
        conn = FileSystemConnector(root_dir=root)
        n = 50
        t0 = time.perf_counter()
        for _ in range(n):
            conn.read_file("hello.txt")
        direct_ms = (time.perf_counter() - t0) / n * 1000

        t0 = time.perf_counter()
        for _ in range(n):
            client.call_tool("read_file", {"path": "hello.txt"})
        mcp_ms = (time.perf_counter() - t0) / n * 1000

        print(f"in-process read : {direct_ms:.3f} ms/call")
        print(f"MCP read        : {mcp_ms:.3f} ms/call")
        print(f"boundary cost   : {mcp_ms - direct_ms:.3f} ms/call "
              f"(~{mcp_ms / max(direct_ms, 1e-6):.0f}x)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
