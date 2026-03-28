"""
tests/test_demo.py
──────────────────
Tests for task-aware demo mode — verifies that different task types
produce contextual (not hardcoded) responses.
"""

from __future__ import annotations

import json

import pytest

from codeops.demo import _classify_task, demo_llm_response


class TestTaskClassification:
    def test_rate_limiter_detected(self):
        assert _classify_task("Build a rate limiter") == "rate_limiter"

    def test_cache_detected(self):
        assert _classify_task("Build an LRU cache with TTL") == "cache"

    def test_auth_detected(self):
        assert _classify_task("Add JWT authentication") == "auth"

    def test_api_detected(self):
        assert _classify_task("Create a REST API endpoint") == "api"

    def test_queue_detected(self):
        assert _classify_task("Build an async task queue") == "queue"

    def test_database_detected(self):
        assert _classify_task("Create a database migration system") == "database"

    def test_websocket_detected(self):
        assert _classify_task("Build a WebSocket chat server") == "websocket"

    def test_test_detected(self):
        assert _classify_task("Generate pytest tests") == "test"

    def test_unknown_falls_back_to_rate_limiter(self):
        assert _classify_task("Do something random") == "rate_limiter"

    def test_case_insensitive(self):
        assert _classify_task("Build a CACHE module") == "cache"


class TestDemoResponses:
    def test_planner_returns_valid_json(self):
        result = demo_llm_response("planner", "Build a cache")
        plan = json.loads(result)
        assert "title" in plan
        assert "steps" in plan
        assert len(plan["steps"]) >= 1

    def test_planner_contextual_tech_stack(self):
        result = demo_llm_response("planner", "Build an LRU cache")
        plan = json.loads(result)
        assert "collections" in plan["tech_stack"] or "threading" in plan["tech_stack"]

    def test_coder_returns_cache_code_for_cache_task(self):
        result = demo_llm_response("coder", "Build an LRU cache", iteration=0)
        assert "lru_cache" in result.lower() or "cache" in result.lower()
        assert "rate_limiter" not in result.lower()

    def test_coder_returns_auth_code_for_auth_task(self):
        result = demo_llm_response("coder", "Add JWT authentication", iteration=0)
        assert "auth" in result.lower()
        assert "rate_limiter" not in result.lower()

    def test_coder_returns_api_code_for_api_task(self):
        result = demo_llm_response("coder", "Build a REST API", iteration=0)
        assert "api" in result.lower()

    def test_coder_revision_differs_from_first(self):
        first = demo_llm_response("coder", "Build a rate limiter", iteration=0)
        second = demo_llm_response("coder", "Build a rate limiter", iteration=1)
        assert first != second

    def test_reviewer_first_pass_needs_revision(self):
        result = demo_llm_response("reviewer", "Build a cache", iteration=0)
        review = json.loads(result)
        assert review["verdict"] == "needs_revision"
        assert review["score"] < 7

    def test_reviewer_second_pass_approves(self):
        result = demo_llm_response("reviewer", "Build a cache", iteration=1)
        review = json.loads(result)
        assert review["verdict"] == "approved"
        assert review["score"] >= 7

    def test_tester_returns_test_code(self):
        result = demo_llm_response("tester", "Build a cache")
        assert "test_" in result.lower()
        assert "---FILE:" in result
        assert "---END---" in result

    def test_github_pr_contextual_title(self):
        result = demo_llm_response("github_pr", "Build an LRU cache")
        pr = json.loads(result)
        assert "cache" in pr["title"]

    def test_unknown_agent_returns_fallback(self):
        result = demo_llm_response("unknown_agent", "some task")
        assert "unknown_agent" in result
