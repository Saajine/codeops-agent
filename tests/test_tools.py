"""
tests/test_tools.py
───────────────────
Tests for the GitHub tool definitions and BaseAgent's tool-execution loop.
The Anthropic client is faked, so these run without a network or API key.
"""

from __future__ import annotations

import uuid

import pytest

from codeops.agents.base_agent import BaseAgent
from codeops.mcp.connectors import GitHubConnector
from codeops.mcp.tools import GITHUB_TOOLS, GITHUB_TOOL_NAMES, build_github_dispatch
from codeops.memory.context import ContextManager
from codeops.memory.store import MemoryStore


# ── Fakes: minimal stand-ins for Anthropic Message / content blocks ───────────

class _Block:
    def __init__(self, type, **kw):
        self.type = type
        for k, v in kw.items():
            setattr(self, k, v)


class _Msg:
    def __init__(self, content, stop_reason):
        self.content = content
        self.stop_reason = stop_reason


class _FakeMessages:
    def __init__(self, script):
        self.script = list(script)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.script.pop(0)


class _FakeClient:
    def __init__(self, script):
        self.messages = _FakeMessages(script)


class _ToolAgent(BaseAgent):
    name = "tool_test"
    skills: list[str] = []
    system_prompt = "You are a test agent."

    def execute(self, task, context):  # pragma: no cover - not exercised here
        raise NotImplementedError


@pytest.fixture
def agent(tmp_path):
    a = _ToolAgent(store=MemoryStore(db_path=str(tmp_path / "t.db")))
    a._demo_mode = False  # force the real (faked) client path
    return a


# ── Tool definition tests ─────────────────────────────────────────────────────

class TestGitHubToolDefinitions:
    def test_seven_tools_match_connector_methods(self):
        assert len(GITHUB_TOOLS) == 7
        for name in GITHUB_TOOL_NAMES:
            assert callable(getattr(GitHubConnector, name)), name

    def test_required_fields_derived_from_signatures(self):
        by_name = {t["name"]: t for t in GITHUB_TOOLS}
        assert by_name["get_pull_request"]["input_schema"]["required"] == [
            "owner", "repo", "pr_number",
        ]
        # list_issues has defaults for state/labels → only owner+repo required.
        assert by_name["list_issues"]["input_schema"]["required"] == ["owner", "repo"]
        assert "state" in by_name["list_issues"]["input_schema"]["properties"]

    def test_dispatch_maps_names_to_bound_methods(self):
        dispatch = build_github_dispatch()
        assert set(dispatch) == GITHUB_TOOL_NAMES
        assert all(callable(fn) for fn in dispatch.values())


# ── _invoke_tool (argument validation + dispatch) ─────────────────────────────

class TestInvokeTool:
    def test_unknown_tool_is_error(self, agent):
        ok, msg = agent._invoke_tool(None, "nope", {})
        assert not ok and "Unknown tool" in msg

    def test_non_object_args_is_error(self, agent):
        ok, msg = agent._invoke_tool(lambda **k: "x", "t", ["not", "a", "dict"])
        assert not ok and "must be a JSON object" in msg

    def test_bad_arguments_is_error(self, agent):
        def needs_owner(owner, repo, pr_number):
            return {}
        ok, msg = agent._invoke_tool(needs_owner, "get_pull_request", {"owner": "o"})
        assert not ok and "Invalid arguments" in msg

    def test_success_serializes_result(self, agent):
        ok, payload = agent._invoke_tool(
            lambda **k: {"title": "hi"}, "get_pull_request", {"owner": "o"}
        )
        assert ok and "title" in payload

    def test_tool_exception_surfaces_as_error(self, agent):
        def boom(**k):
            raise RuntimeError("network down")
        ok, msg = agent._invoke_tool(boom, "get_pull_request", {})
        assert not ok and "network down" in msg


# ── _run_tool_loop (the agentic loop) ─────────────────────────────────────────

class TestRunToolLoop:
    def test_calls_tool_then_returns_final_text(self, agent):
        # Turn 1: model asks for get_pull_request. Turn 2: it finishes.
        script = [
            _Msg(
                [_Block("tool_use", id="t1", name="get_pull_request",
                        input={"owner": "o", "repo": "r", "pr_number": 1})],
                stop_reason="tool_use",
            ),
            _Msg([_Block("text", text="LGTM.")], stop_reason="end_turn"),
        ]
        agent._client = _FakeClient(script)

        called: list[dict] = []

        def fake_get_pr(owner, repo, pr_number):
            called.append({"owner": owner, "repo": repo, "pr_number": pr_number})
            return {"title": "Fix bug", "diff": "..."}

        messages = [{"role": "user", "content": "review it"}]
        final, tool_calls = agent._run_tool_loop(
            messages, GITHUB_TOOLS, {"get_pull_request": fake_get_pr}
        )

        assert final == "LGTM."
        assert called == [{"owner": "o", "repo": "r", "pr_number": 1}]
        assert tool_calls == [
            {"name": "get_pull_request",
             "input": {"owner": "o", "repo": "r", "pr_number": 1}, "ok": True}
        ]
        # assistant turn + tool_result turn were appended to history.
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"][0]["type"] == "tool_result"
        assert messages[-1]["content"][0]["tool_use_id"] == "t1"

    def test_two_tool_calls_before_finishing(self, agent):
        script = [
            _Msg([_Block("tool_use", id="a", name="get_pull_request",
                         input={"owner": "o", "repo": "r", "pr_number": 2})],
                 stop_reason="tool_use"),
            _Msg([_Block("tool_use", id="b", name="get_pr_files",
                         input={"owner": "o", "repo": "r", "pr_number": 2})],
                 stop_reason="tool_use"),
            _Msg([_Block("text", text="Reviewed.")], stop_reason="end_turn"),
        ]
        agent._client = _FakeClient(script)
        dispatch = {
            "get_pull_request": lambda **k: {"diff": "d"},
            "get_pr_files": lambda **k: [{"filename": "a.py"}],
        }
        final, tool_calls = agent._run_tool_loop([{"role": "user", "content": "go"}],
                                                 GITHUB_TOOLS, dispatch)
        assert final == "Reviewed."
        assert [c["name"] for c in tool_calls] == ["get_pull_request", "get_pr_files"]

    def test_iteration_cap_forces_final_answer(self, agent):
        # Model always asks for a tool; loop must stop at the cap and then
        # make one final no-tools call (which the fake returns as text).
        tool_turn = _Msg(
            [_Block("tool_use", id="x", name="get_pull_request", input={})],
            stop_reason="tool_use",
        )
        script = [tool_turn, tool_turn, _Msg([_Block("text", text="forced")], "end_turn")]
        agent._client = _FakeClient(script)

        # Patch the no-tools final call to a simple string return.
        agent._call_llm_streaming = lambda **kw: "capped answer"

        final, tool_calls = agent._run_tool_loop(
            [{"role": "user", "content": "go"}],
            GITHUB_TOOLS,
            {"get_pull_request": lambda **k: "ok"},
            max_iterations=2,
        )
        assert final == "capped answer"
        assert len(tool_calls) == 2  # exactly the cap
