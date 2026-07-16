"""
tests/test_cli.py
─────────────────
Tests for CLI-boundary guards:
  - --max-iter must be >= 1 (range(0) would silently produce nothing)
  - _write_output must reject path-traversal in LLM-supplied file paths
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from codeops.cli import app, _write_output

runner = CliRunner()


# ── --max-iter bounds ─────────────────────────────────────────────────────────

def test_max_iter_zero_is_rejected():
    result = runner.invoke(app, ["run", "Build something", "--demo", "--max-iter", "0"])
    assert result.exit_code != 0

def test_max_iter_negative_is_rejected():
    result = runner.invoke(app, ["run", "Build something", "--demo", "--max-iter", "-3"])
    assert result.exit_code != 0


# ── _write_output traversal guard ─────────────────────────────────────────────

def test_write_output_blocks_path_traversal(tmp_path):
    outside = tmp_path / "outside_marker.py"
    output_dir = tmp_path / "out"
    malicious = (
        "---FILE: ../outside_marker.py---\n"
        "print('escaped')\n"
        "---END---\n"
    )
    _write_output(malicious, str(output_dir))

    # The traversal target must NOT have been created.
    assert not outside.exists()

def test_write_output_writes_safe_path(tmp_path):
    output_dir = tmp_path / "out"
    good = (
        "---FILE: pkg/module.py---\n"
        "print('ok')\n"
        "---END---\n"
    )
    _write_output(good, str(output_dir))

    written = output_dir / "pkg" / "module.py"
    assert written.exists()
    assert "print('ok')" in written.read_text()
