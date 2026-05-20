"""``sysrfx-snap`` command-line entry point.

The CLI exists so an operator can wire arbitrary commands into a
:class:`Collector` from the shell. It deliberately ships no default
commands: every command must be supplied via ``--cmd``. Sections are
explicit, so the CLI never decides on its own what to run or where the
output lands.

Usage:

    sysrfx-snap --cmd tools:"echo hello" --cmd code:"date -u"

Each ``--cmd`` argument is ``SECTION:COMMAND``. ``SECTION`` must be one of
``chat``, ``monologue``, ``code``, ``tools``. ``COMMAND`` is parsed with
``shlex.split`` by default; pass ``--shell`` to run it through ``/bin/sh -c``
instead.
"""

from __future__ import annotations

import argparse
import shlex
import sys
from functools import partial
from typing import List, Optional, Sequence, Tuple

from sysrfx_core.collector import (
    Collector,
    Runner,
    SECTION_METHODS,
    subprocess_runner,
)

__all__ = ["main", "build_parser", "parse_cmd_spec"]


def parse_cmd_spec(spec: str) -> Tuple[str, str]:
    """Split a ``SECTION:COMMAND`` spec into its two parts."""
    if ":" not in spec:
        raise ValueError(
            f"--cmd value {spec!r} must be in 'SECTION:COMMAND' form."
        )
    section, _, command = spec.partition(":")
    section = section.strip()
    if section not in SECTION_METHODS:
        raise ValueError(
            f"--cmd section {section!r} must be one of {SECTION_METHODS}."
        )
    if not command:
        raise ValueError(f"--cmd value {spec!r} has an empty COMMAND part.")
    return section, command


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sysrfx-snap",
        description=(
            "Run operator-supplied commands and render their captured output "
            "as a tagged sysrfx-core transcript. The CLI has no default "
            "commands; every invocation must list its commands explicitly."
        ),
    )
    parser.add_argument(
        "--cmd",
        action="append",
        default=[],
        metavar="SECTION:COMMAND",
        help=(
            "Run COMMAND and append its rendered result to the given "
            "SECTION (chat|monologue|code|tools). Repeat for multiple "
            "commands. Required."
        ),
    )
    parser.add_argument(
        "--message",
        action="append",
        default=[],
        metavar="SECTION:TEXT",
        help=(
            "Append a free-form text message to the given section. Useful "
            "for a leading chat header or inline monologue notes."
        ),
    )
    parser.add_argument(
        "--shell",
        action="store_true",
        help="Execute commands via '/bin/sh -c' instead of shlex.split.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        metavar="SECONDS",
        help="Per-command timeout in seconds (default: 30).",
    )
    return parser


def _resolve_argv(command: str, *, use_shell: bool) -> Sequence[str]:
    if use_shell:
        return ("/bin/sh", "-c", command)
    return shlex.split(command)


def main(argv: Optional[List[str]] = None, *, runner: Optional[Runner] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.cmd and not args.message:
        parser.error("at least one --cmd or --message is required.")

    try:
        cmd_specs = [parse_cmd_spec(spec) for spec in args.cmd]
        msg_specs = [parse_cmd_spec(spec) for spec in args.message]
    except ValueError as exc:
        parser.error(str(exc))
        return 2  # pragma: no cover - parser.error exits before this.

    effective_runner: Runner = runner if runner is not None else partial(
        subprocess_runner, timeout=args.timeout
    )

    collector = Collector(runner=effective_runner)

    for section, text in msg_specs:
        collector.add_message(text, section=section)

    worst_returncode = 0
    for section, command in cmd_specs:
        result = collector.add_command(
            _resolve_argv(command, use_shell=args.shell),
            section=section,
        )
        if result.returncode != 0 and result.returncode > worst_returncode:
            worst_returncode = result.returncode

    sys.stdout.write(collector.render())
    if not collector.render().endswith("\n"):
        sys.stdout.write("\n")
    sys.stdout.flush()
    return worst_returncode


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
