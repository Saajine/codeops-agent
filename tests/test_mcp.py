"""
tests/test_mcp.py
─────────────────
End-to-end tests for the MCP server layer. These spawn the two real stdio
servers (github + filesystem) as subprocesses and drive them through the
federating client. Only filesystem tools are actually invoked, so no network
or API key is required; the github server is started purely to prove
multi-server federation and schema discovery.
"""

from __future__ import annotations

import time

import pytest

from codeops.mcp.client import MCPClient, default_servers
from codeops.mcp.connectors import FileSystemConnector

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


@pytest.fixture(scope="module")
def mcp_client(tmp_path_factory):
    root = tmp_path_factory.mktemp("mcpfs")
    client = MCPClient(default_servers(fs_root=str(root))).start()
    client.fs_root = str(root)  # stash for filesystem assertions
    try:
        yield client
    finally:
        client.stop()


# ── Discovery + federation ────────────────────────────────────────────────────

class TestDiscoveryAndFederation:
    def test_both_servers_federated(self, mcp_client):
        grouped = mcp_client.registry.by_server()
        assert set(grouped) == {"github", "filesystem"}
        # 7 github read tools + 5 filesystem tools.
        assert len(mcp_client.registry) == 12

    def test_tools_from_each_server_present(self, mcp_client):
        names = set(mcp_client.registry.names())
        assert {"get_pull_request", "get_pr_files"} <= names  # github
        assert {"read_file", "write_file"} <= names           # filesystem

    def test_owner_maps_tool_to_server(self, mcp_client):
        assert mcp_client.registry.owner("get_pull_request") == "github"
        assert mcp_client.registry.owner("read_file") == "filesystem"
        assert mcp_client.registry.owner("does_not_exist") is None

    def test_schema_discovery_produces_input_schemas(self, mcp_client):
        tools = {t["name"]: t for t in mcp_client.registry.anthropic_tools()}
        gpr = tools["get_pull_request"]["input_schema"]
        assert gpr["type"] == "object"
        assert set(gpr["required"]) == {"owner", "repo", "pr_number"}
        # Derived from the server's type hints, discovered over tools/list.
        assert gpr["properties"]["pr_number"]["type"] == "integer"


# ── Calling tools over the boundary ───────────────────────────────────────────

class TestToolCalls:
    def test_write_then_read_round_trips(self, mcp_client):
        mcp_client.call_tool("write_file", {"path": "note.txt", "content": "hello mcp"})
        out = mcp_client.call_tool("read_file", {"path": "note.txt"})
        assert out == "hello mcp"
        # And it really hit the filesystem behind the server.
        assert (open(f"{mcp_client.fs_root}/note.txt").read()) == "hello mcp"

    def test_dispatch_callables_route_to_owning_server(self, mcp_client):
        dispatch = mcp_client.dispatch()
        assert set(dispatch) == set(mcp_client.registry.names())
        # The dispatch map is what BaseAgent._run_tool_loop consumes.
        mcp_client.call_tool("write_file", {"path": "d.txt", "content": "x"})
        assert dispatch["file_exists"](path="d.txt") == "true"

    def test_tool_error_propagates(self, mcp_client):
        # Reading a missing file must raise so the agent loop marks is_error.
        with pytest.raises(Exception):
            mcp_client.call_tool("read_file", {"path": "missing.txt"})


# ── Boundary cost (informational — the "what did it cost" answer) ─────────────

class TestBoundaryCost:
    def test_mcp_matches_in_process_result_and_report_latency(self, mcp_client, capsys):
        conn = FileSystemConnector(root_dir=mcp_client.fs_root)
        conn.write_file("bench.txt", "benchmark payload")

        n = 20
        t0 = time.perf_counter()
        for _ in range(n):
            direct = conn.read_file("bench.txt")
        direct_ms = (time.perf_counter() - t0) / n * 1000

        t0 = time.perf_counter()
        for _ in range(n):
            via_mcp = mcp_client.call_tool("read_file", {"path": "bench.txt"})
        mcp_ms = (time.perf_counter() - t0) / n * 1000

        assert direct == via_mcp  # identical result across the boundary
        with capsys.disabled():
            print(
                f"\n[boundary cost] in-process read: {direct_ms:.3f} ms | "
                f"MCP read: {mcp_ms:.3f} ms | overhead: {mcp_ms - direct_ms:.3f} ms/call"
            )
