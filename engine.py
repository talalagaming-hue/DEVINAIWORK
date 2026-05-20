"""
Transcript rendering engine for AI conversation logs.

Provides a small, dependency-free utility for serialising structured AI
transcript entries (chat lines, internal reasoning notes, code blocks, tool
invocations) into a tagged, human-readable text format.

The renderer is intentionally a pure formatter:

* It does not execute, evaluate, or roleplay any of the content it
  formats — it only wraps strings in tags.
* It has no behavioural ``persona`` modes; persona names, if any, are just
  data carried alongside an entry's text.

The tag vocabulary is configurable. Two presets are shipped:

* ``ENGLISH_TAGS`` — ``<chat>``, ``<monologue>``, ``<code>``, ``<tools>``
* ``CYRILLIC_TAGS`` — ``<ЧАТ>``, ``<МОНОЛОГ>``, ``<КОД>``, ``<ИНСТРУМЕНТЫ>``

UTF-8 input (including Cyrillic) is supported natively; the renderer never
encodes or transforms entry text beyond optional indentation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping


class EntryKind(str, Enum):
    """Logical kind of a transcript entry."""

    CHAT = "chat"
    MONOLOGUE = "monologue"
    CODE = "code"
    TOOLS = "tools"


# Default tag vocabularies. Tag *names* are the strings that appear between
# the angle brackets in the rendered output.
ENGLISH_TAGS: Mapping[EntryKind, str] = {
    EntryKind.CHAT: "chat",
    EntryKind.MONOLOGUE: "monologue",
    EntryKind.CODE: "code",
    EntryKind.TOOLS: "tools",
}

CYRILLIC_TAGS: Mapping[EntryKind, str] = {
    EntryKind.CHAT: "ЧАТ",
    EntryKind.MONOLOGUE: "МОНОЛОГ",
    EntryKind.CODE: "КОД",
    EntryKind.TOOLS: "ИНСТРУМЕНТЫ",
}


@dataclass(frozen=True)
class Entry:
    """A single transcript entry.

    Attributes:
        kind: Which logical channel this entry belongs to.
        text: Raw text content; rendered verbatim inside the tag.
        speaker: Optional speaker label (e.g. ``"erafox"``). Rendered as a
            ``speaker="..."`` attribute on the opening tag when set.
        language: Optional language hint for ``CODE`` entries (e.g.
            ``"python"``). Rendered as a ``lang="..."`` attribute.
        attributes: Arbitrary extra key/value attributes for the opening
            tag. Keys must be simple identifiers; values are converted with
            ``str()``.
    """

    kind: EntryKind
    text: str
    speaker: str | None = None
    language: str | None = None
    attributes: Mapping[str, str] = field(default_factory=dict)


class TranscriptRenderer:
    """Serialises :class:`Entry` objects into a tagged text transcript.

    The renderer is stateless aside from its configuration; it is safe to
    reuse a single instance across many ``render`` calls and across
    threads.

    Args:
        tags: Mapping from :class:`EntryKind` to the tag name to use.
            Defaults to :data:`ENGLISH_TAGS`.
        indent: Number of spaces to prepend to each line of ``text``
            inside the tag. ``0`` (the default) leaves text untouched.
        separator: String inserted between consecutive rendered entries.
            Defaults to a single blank line.
    """

    def __init__(
        self,
        tags: Mapping[EntryKind, str] | None = None,
        *,
        indent: int = 0,
        separator: str = "\n\n",
    ) -> None:
        resolved = dict(ENGLISH_TAGS if tags is None else tags)
        missing = [kind for kind in EntryKind if kind not in resolved]
        if missing:
            names = ", ".join(k.value for k in missing)
            raise ValueError(f"tags mapping is missing entries for: {names}")
        if indent < 0:
            raise ValueError("indent must be non-negative")

        self._tags: Mapping[EntryKind, str] = resolved
        self._indent = indent
        self._separator = separator

    # ------------------------------------------------------------------ #
    # Single-entry helpers
    # ------------------------------------------------------------------ #
    def chat(self, text: str, *, speaker: str | None = None) -> str:
        """Render a chat line."""
        return self.render_entry(Entry(EntryKind.CHAT, text, speaker=speaker))

    def monologue(self, text: str, *, speaker: str | None = None) -> str:
        """Render an internal-reasoning note."""
        return self.render_entry(
            Entry(EntryKind.MONOLOGUE, text, speaker=speaker)
        )

    def code(
        self,
        text: str,
        *,
        language: str | None = None,
        speaker: str | None = None,
    ) -> str:
        """Render a code block, optionally tagged with a language hint."""
        return self.render_entry(
            Entry(EntryKind.CODE, text, speaker=speaker, language=language)
        )

    def tools(self, text: str, *, speaker: str | None = None) -> str:
        """Render a tool-invocation record."""
        return self.render_entry(Entry(EntryKind.TOOLS, text, speaker=speaker))

    # ------------------------------------------------------------------ #
    # Generic rendering
    # ------------------------------------------------------------------ #
    def render_entry(self, entry: Entry) -> str:
        """Render a single :class:`Entry` to its tagged string form."""
        tag = self._tags[entry.kind]
        attrs: list[tuple[str, str]] = []
        if entry.speaker is not None:
            attrs.append(("speaker", entry.speaker))
        if entry.language is not None:
            if entry.kind is not EntryKind.CODE:
                raise ValueError(
                    "language attribute is only valid for CODE entries"
                )
            attrs.append(("lang", entry.language))
        for key, value in entry.attributes.items():
            if not key.isidentifier():
                raise ValueError(f"invalid attribute name: {key!r}")
            attrs.append((key, str(value)))

        opening = self._format_opening_tag(tag, attrs)
        body = self._indent_text(entry.text)
        return f"{opening}\n{body}\n</{tag}>"

    def render(self, entries: Iterable[Entry]) -> str:
        """Render an iterable of entries, joined by the configured separator."""
        return self._separator.join(self.render_entry(e) for e in entries)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    @staticmethod
    def _format_opening_tag(tag: str, attrs: list[tuple[str, str]]) -> str:
        if not attrs:
            return f"<{tag}>"
        rendered = " ".join(
            f'{key}="{_escape_attr(value)}"' for key, value in attrs
        )
        return f"<{tag} {rendered}>"

    def _indent_text(self, text: str) -> str:
        if self._indent == 0:
            return text
        pad = " " * self._indent
        return "\n".join(pad + line if line else line for line in text.split("\n"))


def _escape_attr(value: str) -> str:
    """Escape a value for use inside a double-quoted tag attribute."""
    return (
        value.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


__all__ = [
    "CYRILLIC_TAGS",
    "ENGLISH_TAGS",
    "Entry",
    "EntryKind",
    "TranscriptRenderer",
]
