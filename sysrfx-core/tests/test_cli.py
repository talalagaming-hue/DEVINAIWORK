"""Tests for ``sysrfx_core.cli``.

The CLI is invoked via its ``main()`` entry point with a mock runner so the
tests never spawn a real subprocess. The CLI is responsible for parsing
``--cmd SECTION:COMMAND`` specs, splitting commands into argv, wiring the
runner into a :class:`Collector`, and printing the rendered transcript to
stdout.
"""

from __future__ import annotations

import re
from typing import Dict, List, Sequence, Tuple

import pytest

from sysrfx_core.cli import main, parse_cmd_spec
from sysrfx_core.collector import CommandResult


class CapturedRunner:
    def __init__(self, responses: Dict[Tuple[str, ...], CommandResult]) -> None:
        self.responses = responses
        self.calls: List[Tuple[str, ...]] = []

    def __call__(self, argv: Sequence[str]) -> CommandResult:
        key = tuple(argv)
        self.calls.append(key)
        if key not in self.responses:
            raise AssertionError(f"unexpected argv {key!r}")
        return self.responses[key]


def test_parse_cmd_spec_basic() -> None:
    assert parse_cmd_spec("tools:id") == ("tools", "id")
    assert parse_cmd_spec("code:lsb_release -a") == ("code", "lsb_release -a")


def test_parse_cmd_spec_strips_section_whitespace() -> None:
    assert parse_cmd_spec(" tools : id ") == ("tools", " id ")


def test_parse_cmd_spec_rejects_missing_colon() -> None:
    with pytest.raises(ValueError):
        parse_cmd_spec("id")


def test_parse_cmd_spec_rejects_bad_section() -> None:
    with pytest.raises(ValueError):
        parse_cmd_spec("logs:id")


def test_parse_cmd_spec_rejects_empty_command() -> None:
    with pytest.raises(ValueError):
        parse_cmd_spec("tools:")


def test_parse_cmd_spec_preserves_colons_in_command() -> None:
    # Only the first ':' separates section from command; subsequent ones
    # stay in the command verbatim.
    assert parse_cmd_spec("tools:echo a:b:c") == ("tools", "echo a:b:c")


def test_cli_requires_at_least_one_cmd_or_message(capsys: pytest.CaptureFixture) -> None:
    with pytest.raises(SystemExit):
        main([], runner=lambda argv: CommandResult(argv=tuple(argv)))
    err = capsys.readouterr().err
    assert "at least one --cmd or --message is required" in err


def test_cli_end_to_end_with_mock_runner(capsys: pytest.CaptureFixture) -> None:
    # shlex.split passes literal characters through; '\n' inside single
    # quotes is the two characters '\' and 'n', not a newline. The mock
    # response is what printf would actually emit: a real newline.
    runner = CapturedRunner({
        ("printf", "first\\nsecond\\n"): CommandResult(
            argv=("printf", "first\\nsecond\\n"),
            stdout="first\nsecond\n",
            returncode=0,
            duration_s=0.001,
        ),
        ("echo", "hello"): CommandResult(
            argv=("echo", "hello"),
            stdout="hello\n",
            returncode=0,
            duration_s=0.0005,
        ),
    })
    rc = main(
        [
            "--message", "chat:erafox: starting",
            "--cmd", "tools:echo hello",
            "--cmd", "code:printf 'first\\nsecond\\n'",
        ],
        runner=runner,
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert out.startswith("<ЧАТ>erafox: starting</ЧАТ>")
    assert "<ИНСТРУМЕНТЫ>$ echo hello" in out
    assert "<КОД>" in out
    assert "first\nsecond" in out
    # Mock runner saw exactly the two commands.
    assert runner.calls == [
        ("echo", "hello"),
        ("printf", "first\\nsecond\\n"),
    ]


def test_cli_preserves_argument_order_across_flag_kinds(
    capsys: pytest.CaptureFixture,
) -> None:
    """Interleaved --message and --cmd flags must render in CLI order."""
    runner = CapturedRunner({
        ("first",): CommandResult(argv=("first",), stdout="A", returncode=0),
        ("second",): CommandResult(argv=("second",), stdout="B", returncode=0),
    })
    rc = main(
        [
            "--message", "chat:line 1",
            "--cmd", "tools:first",
            "--message", "monologue:between",
            "--cmd", "code:second",
            "--message", "chat:line 5",
        ],
        runner=runner,
    )
    assert rc == 0
    out = capsys.readouterr().out

    # Extract just the opening tag of each section in document order; the
    # sequence must match the CLI argument order exactly.
    opens = re.findall(r"<(ЧАТ|МОНОЛОГ|КОД|ИНСТРУМЕНТЫ)>", out)
    assert opens == ["ЧАТ", "ИНСТРУМЕНТЫ", "МОНОЛОГ", "КОД", "ЧАТ"]

    # Sanity check: the runner was still called only twice, in order.
    assert runner.calls == [("first",), ("second",)]


def test_cli_propagates_worst_returncode(capsys: pytest.CaptureFixture) -> None:
    runner = CapturedRunner({
        ("ok",): CommandResult(argv=("ok",), stdout="ok", returncode=0),
        ("bad",): CommandResult(argv=("bad",), stdout="", stderr="boom", returncode=7),
    })
    rc = main(
        ["--cmd", "tools:ok", "--cmd", "code:bad"],
        runner=runner,
    )
    assert rc == 7
    out = capsys.readouterr().out
    assert "[exit 7," in out


def test_cli_rejects_unknown_section_via_parser_error(capsys: pytest.CaptureFixture) -> None:
    runner = CapturedRunner({})
    with pytest.raises(SystemExit):
        main(["--cmd", "logs:id"], runner=runner)
    err = capsys.readouterr().err
    assert "must be one of" in err


def test_cli_shell_mode_wraps_in_sh_c(capsys: pytest.CaptureFixture) -> None:
    seen: List[Sequence[str]] = []

    def runner(argv: Sequence[str]) -> CommandResult:
        seen.append(tuple(argv))
        return CommandResult(argv=tuple(argv), stdout="ok", returncode=0)

    rc = main(["--shell", "--cmd", "tools:echo a && echo b"], runner=runner)
    assert rc == 0
    assert seen == [("/bin/sh", "-c", "echo a && echo b")]
