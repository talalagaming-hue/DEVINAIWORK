"""Tagged renderer for sysrfx-style group chat transcripts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Iterable, Sequence


class RenderTag(str, Enum):
    """Supported transcript block tags."""

    CHAT = "ЧАТ"
    MONOLOGUE = "МОНОЛОГ"
    CODE = "КОД"
    TOOLS = "ИНСТРУМЕНТЫ"


@dataclass(frozen=True)
class ChatMessage:
    """One group-chat message."""

    sender: str
    text: str
    timestamp: str | None = None

    def render(self) -> str:
        header = self.sender if self.timestamp is None else f"{self.sender}, {self.timestamp}"
        return f"{header}\n{self.text.strip()}"


@dataclass
class SysrfxEngine:
    """Render tagged chat, rationale, code, and tool/action blocks.

    The engine only formats supplied content. It does not expose private model
    reasoning; monologue blocks are intended for concise technical summaries.
    """

    client_name: str = "erafox"
    contractor_name: str = "Ден"
    language: str = "ru"
    _booted: bool = field(default=False, init=False, repr=False)

    def boot(self) -> str:
        """Initialize the renderer and return a tagged readiness message."""
        self._booted = True
        return "\n\n".join(
            [
                self.tools(
                    [
                        "booting sysrfx-core...",
                        "[OK] render_tags loaded: ЧАТ, МОНОЛОГ, КОД, ИНСТРУМЕНТЫ",
                        "[OK] persona loaded: Den technical concise ru",
                        "[OK] engine ready",
                    ]
                ),
                self.chat([ChatMessage(self.contractor_name, "на месте. жду ввод.", self._now())]),
            ]
        )

    def chat(self, messages: Sequence[ChatMessage | tuple[str, str] | tuple[str, str, str]]) -> str:
        rendered: list[str] = []
        for message in messages:
            if isinstance(message, ChatMessage):
                rendered.append(message.render())
            elif len(message) == 2:
                sender, text = message
                rendered.append(ChatMessage(sender, text).render())
            else:
                sender, timestamp, text = message
                rendered.append(ChatMessage(sender, text, timestamp).render())
        return self.wrap(RenderTag.CHAT, "\n\n".join(rendered))

    def monologue(self, summary: str, details: Iterable[str] = ()) -> str:
        """Render a concise technical rationale block."""
        lines = [f"Задача: {summary.strip()}"]
        lines.extend(line.strip() for line in details if line.strip())
        return self.wrap(RenderTag.MONOLOGUE, "\n".join(lines))

    def code(self, source: str, language: str = "python") -> str:
        body = f"```{language}\n{source.rstrip()}\n```"
        return self.wrap(RenderTag.CODE, body)

    def tools(self, actions: Iterable[str]) -> str:
        body = "\n".join(self._format_action(action) for action in actions if action.strip())
        return self.wrap(RenderTag.TOOLS, body)

    def reply_as_den(self, erafox_input: str) -> str:
        """Render a deterministic Den response for integration tests."""
        normalized = " ".join(erafox_input.split())
        if not normalized:
            response = "пусто пришло. скинь задачу текстом."
            rationale = "Ввод пустой; нужен запрос для обработки."
        elif "код" in normalized.lower() or "engine" in normalized.lower():
            response = "принял. держу формат тегов, без лишнего шума."
            rationale = "Запрос относится к реализации или проверке движка; отвечаю коротко и технически."
        else:
            response = "вижу. разберу и отвечу по делу."
            rationale = "Запрос получен; требуется краткий технический ответ в стиле Den."

        return "\n\n".join(
            [
                self.chat([ChatMessage(self.client_name, normalized)]),
                self.monologue(rationale),
                self.chat([ChatMessage(self.contractor_name, response)]),
            ]
        )

    @staticmethod
    def wrap(tag: RenderTag | str, content: str) -> str:
        tag_value = tag.value if isinstance(tag, RenderTag) else str(tag)
        return f"<{tag_value}>\n{content.strip()}\n</{tag_value}>"

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%H:%M")

    @staticmethod
    def _format_action(action: str) -> str:
        clean = action.strip()
        if clean.startswith("["):
            return clean
        return f"[{clean}]"


def main() -> None:
    engine = SysrfxEngine()
    print(engine.boot())
    while True:
        try:
            user_input = input("> ")
        except EOFError:
            break
        if user_input.strip().lower() in {"exit", "quit"}:
            break
        print(engine.reply_as_den(user_input))


if __name__ == "__main__":
    main()
