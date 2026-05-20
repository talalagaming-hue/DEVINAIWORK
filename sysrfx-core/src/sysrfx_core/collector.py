"""Collector: drives a ``ChatRenderer`` from an injected command runner.

``Collector`` is intentionally agnostic of how commands actually execute.
A caller supplies a ``Runner`` callable; the collector calls it, captures the
``CommandResult``, and appends a human-readable summary to the appropriate
``ChatRenderer`` section.

The library ships:

- ``null_runner``: the default. Records the call but does not execute the
  command. Importing this module never causes a subprocess to run.
- ``subprocess_runner``: a thin wrapper around ``subprocess.run`` that the
  CLI uses. Callers must opt in explicitly.

Tests should always inject their own runner so that no real subprocess is
spawned during pytest runs.
"""

from __future__ import annotations

import shlex
import subprocess
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple

from sysrfx_core.engine import ChatRenderer

__all__ = [
    "CommandResult",
    "Runner",
    "Collector",
    "null_runner",
    "subprocess_runner",
    "SECTION_METHODS",
]

# Map a section name (as used on the CLI / by callers) to the ChatRenderer
# method that appends a section with that tag. Keeping this in one place
# avoids ad-hoc dispatch in the Collector and the CLI.
SECTION_METHODS: Tuple[str, ...] = ("chat", "monologue", "code", "tools")


@dataclass(frozen=True)
class CommandResult:
    """Captured outcome of a single command invocation."""

    argv: Tuple[str, ...]
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0
    duration_s: float = 0.0
    error: Optional[str] = None

    @property
    def commandline(self) -> str:
        """Shell-quoted command line, for display only."""
        return " ".join(shlex.quote(a) for a in self.argv)


Runner = Callable[[Sequence[str]], CommandResult]


def null_runner(argv: Sequence[str]) -> CommandResult:
    """Runner that records the call but does not execute anything.

    Used as the default for :class:`Collector` so that constructing a
    collector and calling ``add_command`` is side-effect-free unless the
    caller explicitly wires in an executing runner.
    """
    return CommandResult(
        argv=tuple(argv),
        stdout="",
        stderr="",
        returncode=0,
        duration_s=0.0,
        error="null_runner: command not executed (no runner configured)",
    )


def subprocess_runner(argv: Sequence[str], *, timeout: float = 30.0) -> CommandResult:
    """Runner that executes ``argv`` via :func:`subprocess.run`.

    Captures stdout, stderr, exit code, and wall-clock duration. On timeout
    or any ``OSError`` the result's ``error`` field is populated and
    ``returncode`` is set to ``-1``; the caller can decide how to react.
    """
    argv_t = tuple(argv)
    start = time.perf_counter()
    try:
        proc = subprocess.run(
            list(argv_t),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            argv=argv_t,
            stdout=exc.stdout if isinstance(exc.stdout, str) else "",
            stderr=exc.stderr if isinstance(exc.stderr, str) else "",
            returncode=-1,
            duration_s=time.perf_counter() - start,
            error=f"timeout after {timeout}s",
        )
    except (OSError, ValueError) as exc:
        return CommandResult(
            argv=argv_t,
            stdout="",
            stderr="",
            returncode=-1,
            duration_s=time.perf_counter() - start,
            error=str(exc),
        )
    return CommandResult(
        argv=argv_t,
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
        returncode=proc.returncode,
        duration_s=time.perf_counter() - start,
        error=None,
    )


def _format_result(result: CommandResult) -> str:
    """Format a ``CommandResult`` into the human-readable text that goes
    into a section body."""
    lines: List[str] = [f"$ {result.commandline}"]
    if result.stdout:
        lines.append(result.stdout.rstrip("\n"))
    if result.stderr:
        lines.append("--- stderr ---")
        lines.append(result.stderr.rstrip("\n"))
    if result.error:
        lines.append(f"[error] {result.error}")
    lines.append(
        f"[exit {result.returncode}, {result.duration_s * 1000:.2f} ms]"
    )
    return "\n".join(lines)


@dataclass
class Collector:
    """Records commands and free-form messages into a ``ChatRenderer``.

    The runner is injected, defaulting to :func:`null_runner` so that
    importing or constructing a ``Collector`` never executes a subprocess.
    Tests pass a mock runner; the CLI wires :func:`subprocess_runner`.
    """

    runner: Runner = field(default=null_runner)
    renderer: ChatRenderer = field(default_factory=ChatRenderer)
    results: List[CommandResult] = field(default_factory=list)

    def add_message(self, content: str, *, section: str = "chat") -> "Collector":
        """Append a free-form message to the given section."""
        self._append_to_section(section, content)
        return self

    def add_command(
        self,
        argv: Sequence[str],
        *,
        section: str = "tools",
    ) -> CommandResult:
        """Run ``argv`` via the injected runner and append the result.

        Returns the :class:`CommandResult` so callers can branch on
        ``returncode`` or ``error``.
        """
        if section not in SECTION_METHODS:
            raise ValueError(
                f"Unknown section {section!r}; expected one of {SECTION_METHODS}."
            )
        result = self.runner(tuple(argv))
        self.results.append(result)
        self._append_to_section(section, _format_result(result))
        return result

    def render(self) -> str:
        """Render the accumulated transcript."""
        return self.renderer.render()

    def _append_to_section(self, section: str, content: str) -> None:
        if section not in SECTION_METHODS:
            raise ValueError(
                f"Unknown section {section!r}; expected one of {SECTION_METHODS}."
            )
        getattr(self.renderer, section)(content)
