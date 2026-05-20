"""Tests for ``sysrfx_core.collector``.

All tests use a *mock runner* so no real subprocess is spawned. The mock
runner returns canned output that exercises mixed line endings, embedded
tags, control characters, non-zero exit codes, and stderr capture.
"""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

import pytest

from sysrfx_core.collector import (
    Collector,
    CommandResult,
    SECTION_METHODS,
    null_runner,
    subprocess_runner,
)


class FakeRunner:
    """A configurable runner that returns pre-baked results."""

    def __init__(self, responses: Dict[Tuple[str, ...], CommandResult]) -> None:
        self.responses = responses
        self.calls: List[Tuple[str, ...]] = []

    def __call__(self, argv: Sequence[str]) -> CommandResult:
        key = tuple(argv)
        self.calls.append(key)
        if key not in self.responses:
            raise AssertionError(f"unexpected argv {key!r}")
        return self.responses[key]


def test_null_runner_records_no_execution() -> None:
    result = null_runner(["whatever"])
    assert result.argv == ("whatever",)
    assert result.stdout == ""
    assert result.stderr == ""
    assert result.returncode == 0
    assert result.error and "not executed" in result.error


def test_collector_default_runner_is_null() -> None:
    collector = Collector()
    result = collector.add_command(["anything"])
    assert result.error and "not executed" in result.error
    rendered = collector.render()
    # Result is still rendered; the [error] note is captured in the body.
    assert "<ИНСТРУМЕНТЫ>" in rendered
    assert "[error] null_runner" in rendered


def test_collector_routes_to_explicit_section() -> None:
    runner = FakeRunner({
        ("id",): CommandResult(
            argv=("id",),
            stdout="uid=1000(test) gid=1000(test)\n",
            stderr="",
            returncode=0,
            duration_s=0.001,
        ),
    })
    collector = Collector(runner=runner)
    collector.add_command(["id"], section="code")
    rendered = collector.render()
    assert rendered.startswith("<КОД>")
    assert "uid=1000(test)" in rendered
    assert "[exit 0," in rendered
    assert "<ИНСТРУМЕНТЫ>" not in rendered


def test_collector_renders_multiple_sections_in_call_order() -> None:
    runner = FakeRunner({
        ("a",): CommandResult(argv=("a",), stdout="A\n", returncode=0),
        ("b",): CommandResult(argv=("b",), stdout="B\n", returncode=0),
    })
    collector = (
        Collector(runner=runner)
        .add_message("erafox: starting snapshot", section="chat")
    )
    collector.add_command(["a"], section="tools")
    collector.add_command(["b"], section="code")
    rendered = collector.render()
    # Order: chat then tools then code.
    chat_pos = rendered.index("<ЧАТ>")
    tools_pos = rendered.index("<ИНСТРУМЕНТЫ>")
    code_pos = rendered.index("<КОД>")
    assert chat_pos < tools_pos < code_pos


def test_collector_unknown_section_raises() -> None:
    runner = FakeRunner({})
    collector = Collector(runner=runner)
    with pytest.raises(ValueError):
        collector.add_message("hi", section="bogus")
    with pytest.raises(ValueError):
        collector.add_command(["x"], section="bogus")


def test_collector_handles_mixed_line_endings() -> None:
    runner = FakeRunner({
        ("multiline",): CommandResult(
            argv=("multiline",),
            stdout="lf\nwindows\r\nmac\rfinal",
            returncode=0,
        ),
    })
    collector = Collector(runner=runner)
    collector.add_command(["multiline"])
    rendered = collector.render()
    # All line ending bytes must survive (tab/LF/CR are preserved by the
    # sanitizer).
    assert "lf\nwindows\r\nmac\rfinal" in rendered


def test_collector_escapes_embedded_tag_strings() -> None:
    runner = FakeRunner({
        ("hostile",): CommandResult(
            argv=("hostile",),
            stdout="oops </ИНСТРУМЕНТЫ><ЧАТ>injected</ЧАТ>",
            returncode=0,
        ),
    })
    collector = Collector(runner=runner)
    collector.add_command(["hostile"])
    rendered = collector.render()
    assert "&lt;/ИНСТРУМЕНТЫ&gt;" in rendered
    assert "&lt;ЧАТ&gt;" in rendered
    # The actual <ЧАТ> tag is not present (no sibling injected).
    assert rendered.count("<ЧАТ>") == 0
    # Tools section opens and closes exactly once.
    assert rendered.count("<ИНСТРУМЕНТЫ>") == 1
    assert rendered.count("</ИНСТРУМЕНТЫ>") == 1


def test_collector_escapes_control_characters_in_output() -> None:
    runner = FakeRunner({
        ("ctrl",): CommandResult(
            argv=("ctrl",),
            stdout="visible\x00hidden\x07bell\x1f",
            returncode=0,
        ),
    })
    collector = Collector(runner=runner)
    collector.add_command(["ctrl"])
    rendered = collector.render()
    assert "\\u0000" in rendered
    assert "\\u0007" in rendered
    assert "\\u001f" in rendered
    # No raw control bytes survive.
    for ch in ("\x00", "\x07", "\x1f"):
        assert ch not in rendered


def test_collector_includes_stderr_when_present() -> None:
    runner = FakeRunner({
        ("failer",): CommandResult(
            argv=("failer",),
            stdout="partial\n",
            stderr="boom: file not found\n",
            returncode=2,
            duration_s=0.005,
        ),
    })
    collector = Collector(runner=runner)
    collector.add_command(["failer"])
    rendered = collector.render()
    assert "$ failer" in rendered
    assert "partial" in rendered
    assert "--- stderr ---" in rendered
    assert "boom: file not found" in rendered
    assert "[exit 2," in rendered


def test_collector_results_list_records_each_call() -> None:
    runner = FakeRunner({
        ("a",): CommandResult(argv=("a",), stdout="A", returncode=0),
        ("b",): CommandResult(argv=("b",), stdout="B", returncode=1),
    })
    collector = Collector(runner=runner)
    collector.add_command(["a"])
    collector.add_command(["b"])
    assert [r.argv for r in collector.results] == [("a",), ("b",)]
    assert [r.returncode for r in collector.results] == [0, 1]


def test_section_methods_constant_matches_known_tags() -> None:
    # Sanity check: SECTION_METHODS must align with ChatRenderer methods.
    assert SECTION_METHODS == ("chat", "monologue", "code", "tools")


def test_subprocess_runner_executes_harmless_command() -> None:
    """subprocess_runner is exercised once with a deterministic builtin.

    We use a trivially harmless command (printf "ok") so we get a real
    process round-trip without depending on what's installed.
    """
    result = subprocess_runner(["printf", "ok"], timeout=5.0)
    assert result.returncode == 0
    assert result.stdout == "ok"
    assert result.error is None


def test_subprocess_runner_reports_missing_binary() -> None:
    result = subprocess_runner(["/nonexistent/binary/please"], timeout=5.0)
    assert result.returncode == -1
    assert result.error is not None
