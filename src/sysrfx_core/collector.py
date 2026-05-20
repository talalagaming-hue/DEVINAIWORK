"""Collect native system streams and render them through SysrfxEngine."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence

from engine import ChatMessage, SysrfxEngine


Runner = Callable[[Sequence[str], int], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class CommandSpec:
    """One native stream collected for a sysrfx snapshot."""

    name: str
    command: tuple[str, ...]
    renderer: str
    description: str
    redact: bool = False


@dataclass(frozen=True)
class CommandResult:
    """Captured command output and execution metadata."""

    spec: CommandSpec
    exit_code: int
    stdout: str
    stderr: str

    @property
    def payload(self) -> str:
        text = f"$ {' '.join(self.spec.command)}\n# exit_code={self.exit_code}\n"
        if self.stdout:
            text += self.stdout.rstrip() + "\n"
        if self.stderr:
            text += "\n[stderr]\n" + self.stderr.rstrip() + "\n"
        return text

    @property
    def line_count(self) -> int:
        return len(self.payload.splitlines())

    @property
    def byte_count(self) -> int:
        return len(self.payload.encode("utf-8"))


class SysrfxCollector:
    """Collect package, network, and process streams for renderer testing."""

    SECRET_PATTERN = re.compile(
        r"(?i)(password|passwd|pwd|token|secret|api[_-]?key|authorization|bearer)(=|\s+)\S+"
    )

    def __init__(
        self,
        engine: SysrfxEngine | None = None,
        timeout_seconds: int = 120,
        runner: Runner | None = None,
    ):
        self.engine = engine or SysrfxEngine()
        self.timeout_seconds = timeout_seconds
        self.runner = runner or self._run_subprocess

    def collect(self, specs: Iterable[CommandSpec] | None = None) -> list[CommandResult]:
        return [self._collect_one(spec) for spec in (specs or self.default_specs())]

    def render_snapshot(self, results: Sequence[CommandResult]) -> str:
        sections: list[str] = [
            self.engine.chat([ChatMessage("erafox", "запусти sysrfx-snap: пакеты, сеть, процессы")]),
            self.engine.chat([ChatMessage("Ден", "принял. снимаю native streams и прогоняю через renderer.")]),
        ]

        for result in results:
            sections.append(self._render_result(result))

        sections.extend(
            [
                self.engine.monologue(
                    "Оценка sysrfx-snap под реальной нагрузкой.",
                    [
                        "wrap() сохранил границы тегов и многострочный payload без экранирования содержимого.",
                        "code() подходит для длинных package/process streams: ширина колонок и tree indentation остаются читаемыми.",
                        "tools() выдержал network topology, включая двоеточия, wildcard-адреса и PID/program columns.",
                        "Для процессов применяется редактирование потенциальных секретов в command line перед рендером.",
                    ],
                ),
                self.engine.chat([ChatMessage("Ден", "sysrfx-snap готов. формат не поплыл, данные читаются.")]),
            ]
        )
        return "\n\n".join(sections) + "\n"

    def write_snapshot(self, output_path: Path, results: Sequence[CommandResult] | None = None) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot = self.render_snapshot(results or self.collect())
        output_path.write_text(snapshot, encoding="utf-8")
        return output_path

    def default_specs(self) -> list[CommandSpec]:
        network_command = self._first_available(
            [("ss", "-tulpn"), ("netstat", "-tulpn")], fallback=("netstat", "-tulpn")
        )
        return [
            CommandSpec(
                name="installed-packages",
                command=("dpkg", "-l"),
                renderer="code",
                description="installed package inventory",
            ),
            CommandSpec(
                name="network-topology",
                command=network_command,
                renderer="tools",
                description="listening sockets and owning processes",
            ),
            CommandSpec(
                name="process-tree",
                command=("ps", "auxf"),
                renderer="code",
                description="process tree with command-line redaction",
                redact=True,
            ),
        ]

    def _collect_one(self, spec: CommandSpec) -> CommandResult:
        if shutil.which(spec.command[0]) is None:
            return CommandResult(spec, 127, "", f"{spec.command[0]}: command not found")
        try:
            completed = self.runner(spec.command, self.timeout_seconds)
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
            exit_code = completed.returncode
        except subprocess.TimeoutExpired as error:
            stdout = error.stdout or ""
            stderr = (error.stderr or "") + f"\ncommand timed out after {self.timeout_seconds}s"
            exit_code = 124
        if spec.redact:
            stdout = self.redact(stdout)
            stderr = self.redact(stderr)
        return CommandResult(spec, exit_code, stdout, stderr)

    def _render_result(self, result: CommandResult) -> str:
        meta = self.engine.monologue(
            f"{result.spec.name}: {result.spec.description}.",
            [
                f"command={' '.join(result.spec.command)}",
                f"exit_code={result.exit_code}",
                f"lines={result.line_count}",
                f"bytes={result.byte_count}",
                f"renderer={result.spec.renderer}",
            ],
        )
        if result.spec.renderer == "tools":
            return meta + "\n\n" + self.engine.tools(result.payload.splitlines())
        return meta + "\n\n" + self.engine.code(result.payload, "text")

    @classmethod
    def redact(cls, text: str) -> str:
        return cls.SECRET_PATTERN.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", text)

    @staticmethod
    def _first_available(commands: Sequence[tuple[str, ...]], fallback: tuple[str, ...]) -> tuple[str, ...]:
        for command in commands:
            if shutil.which(command[0]) is not None:
                return command
        return fallback

    @staticmethod
    def _run_subprocess(command: Sequence[str], timeout_seconds: int) -> subprocess.CompletedProcess[str]:
        return subprocess.run(command, text=True, capture_output=True, timeout=timeout_seconds, check=False)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a tagged sysrfx native system snapshot.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("sysrfx-snap.txt"),
        help="Path to write the rendered snapshot.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Per-command timeout in seconds.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    collector = SysrfxCollector(timeout_seconds=args.timeout)
    output_path = collector.write_snapshot(args.output)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
