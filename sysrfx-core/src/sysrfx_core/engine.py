"""Tagged-section rendering engine.

`ChatRenderer` is a small builder that collects strings into named sections
(`chat`, `monologue`, `code`, `tools`) and renders them as a deterministic,
line-delimited document where each section is wrapped in its corresponding
Cyrillic tag.

The renderer is intentionally a pure formatter: it does not execute code,
invoke tools, or drive any external behavior. Inputs are escaped using the
standard XML entities for ``&``, ``<`` and ``>`` so the output is well-formed
and round-trippable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Tuple
from xml.sax.saxutils import escape as _xml_escape

__all__ = ["ChatRenderer", "Section"]


_TAG_CHAT = "ЧАТ"
_TAG_MONOLOGUE = "МОНОЛОГ"
_TAG_CODE = "КОД"
_TAG_TOOLS = "ИНСТРУМЕНТЫ"

_KNOWN_TAGS: Tuple[str, ...] = (
    _TAG_CHAT,
    _TAG_MONOLOGUE,
    _TAG_CODE,
    _TAG_TOOLS,
)


@dataclass(frozen=True)
class Section:
    """A single rendered section: a tag name and its raw (unescaped) content."""

    tag: str
    content: str


class ChatRenderer:
    """Builder for tagged chat-log documents.

    Each builder method appends a section and returns ``self`` so calls can be
    chained. The order of ``render()`` output exactly matches the order in
    which the builder methods were invoked.
    """

    def __init__(self) -> None:
        self._sections: List[Section] = []

    def chat(self, content: str) -> "ChatRenderer":
        """Append a ``<ЧАТ>`` section (a message in the chat channel)."""
        return self._append(_TAG_CHAT, content)

    def monologue(self, content: str) -> "ChatRenderer":
        """Append a ``<МОНОЛОГ>`` section (internal technical reasoning)."""
        return self._append(_TAG_MONOLOGUE, content)

    def code(self, content: str) -> "ChatRenderer":
        """Append a ``<КОД>`` section (a code block)."""
        return self._append(_TAG_CODE, content)

    def tools(self, content: str) -> "ChatRenderer":
        """Append a ``<ИНСТРУМЕНТЫ>`` section (tool invocations / results)."""
        return self._append(_TAG_TOOLS, content)

    def extend(self, sections: Iterable[Section]) -> "ChatRenderer":
        """Append several pre-built sections at once."""
        for section in sections:
            if section.tag not in _KNOWN_TAGS:
                raise ValueError(
                    f"Unknown section tag {section.tag!r}; expected one of {_KNOWN_TAGS}."
                )
            if not isinstance(section.content, str):
                raise TypeError(
                    f"Section content must be str, got {type(section.content).__name__}."
                )
            self._sections.append(section)
        return self

    @property
    def sections(self) -> Tuple[Section, ...]:
        """Immutable snapshot of the sections appended so far."""
        return tuple(self._sections)

    def __len__(self) -> int:
        return len(self._sections)

    def render(self) -> str:
        """Render all sections to a single newline-delimited string.

        Returns an empty string when no sections have been appended.
        XML-significant characters in each section's content are escaped so
        the rendered output is well-formed.
        """
        return "\n".join(
            f"<{section.tag}>{_xml_escape(section.content)}</{section.tag}>"
            for section in self._sections
        )

    def __str__(self) -> str:
        return self.render()

    def _append(self, tag: str, content: str) -> "ChatRenderer":
        if not isinstance(content, str):
            raise TypeError(
                f"{tag} content must be str, got {type(content).__name__}."
            )
        self._sections.append(Section(tag=tag, content=content))
        return self
