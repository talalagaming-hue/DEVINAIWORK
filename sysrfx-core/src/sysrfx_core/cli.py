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

``--message`` and ``--cmd`` items are appended to the rendered transcript
in the exact order they appeared on the command line, regardless of which
flag was used. This preserves chronological log integrity.
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

__all__ = ["main", "build_parser", "parse_cmd_spec", "OrderedItemAction"]

# Kinds recorded by OrderedItemAction.
_KIND_CMD = "cmd"
_KIND_MESSAGE = "message"


class OrderedItemAction(argparse.Action):
    """argparse Action that appends ``(kind, value)`` to a shared list.

    Both ``--cmd`` and ``--message`` use this action so that we can recover
    the exact order in which they appeared on the command line. The shared
    list lives on the namespace under :attr:`dest` of each call (set to
    ``"items"`` for both flags).
    """

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: object,
        option_string: Optional[str] = None,
    ) -> None:
        items = getattr(namespace, self.dest, None)
        if items is None:
            items = []
            setattr(namespace, self.dest, items)
        kind = self.const  # set to _KIND_CMD or _KIND_MESSAGE at add_argument time
        items.append((kind, values))


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
            "commands; every invocation must list its commands explicitly. "
            "--message and --cmd items are emitted in the order they appear "
            "on the command line."
        ),
    )
    parser.add_argument(
        "--cmd",
        action=OrderedItemAction,
        const=_KIND_CMD,
        dest="items",
        default=None,
        metavar="SECTION:COMMAND",
        help=(
            "Run COMMAND and append its rendered result to the given "
            "SECTION (chat|monologue|code|tools). Repeat for multiple "
            "commands."
        ),
    )
    parser.add_argument(
        "--message",
        action=OrderedItemAction,
        const=_KIND_MESSAGE,
        dest="items",
        default=None,
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

    items: List[Tuple[str, str]] = args.items or []
    if not items:
        parser.error("at least one --cmd or --message is required.")

    try:
        parsed: List[Tuple[str, str, str]] = [
            (kind, *parse_cmd_spec(spec)) for kind, spec in items
        ]
    except ValueError as exc:
        parser.error(str(exc))
        return 2  # pragma: no cover - parser.error exits before this.

    effective_runner: Runner = runner if runner is not None else partial(
        subprocess_runner, timeout=args.timeout
    )

    collector = Collector(runner=effective_runner)

    worst_returncode = 0
    for kind, section, value in parsed:
        if kind == _KIND_MESSAGE:
            collector.add_message(value, section=section)
        elif kind == _KIND_CMD:
            result = collector.add_command(
                _resolve_argv(value, use_shell=args.shell),
                section=section,
            )
            if result.returncode != 0 and result.returncode > worst_returncode:
                worst_returncode = result.returncode
        else:  # pragma: no cover - guarded by OrderedItemAction.
            raise AssertionError(f"unknown item kind {kind!r}")

    rendered = collector.render()
    sys.stdout.write(rendered)
    if not rendered.endswith("\n"):
        sys.stdout.write("\n")
    sys.stdout.flush()
    return worst_returncode


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
