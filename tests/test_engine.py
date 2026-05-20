"""Unit tests for the transcript rendering engine."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make the repo root importable so ``import engine`` works regardless of
# how pytest is invoked.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import (  # noqa: E402  (path manipulation above)
    CYRILLIC_TAGS,
    ENGLISH_TAGS,
    Entry,
    EntryKind,
    TranscriptRenderer,
)


# --------------------------------------------------------------------------- #
# Basic single-entry rendering
# --------------------------------------------------------------------------- #
def test_chat_default_tag():
    r = TranscriptRenderer()
    assert r.chat("hello") == "<chat>\nhello\n</chat>"


def test_monologue_default_tag():
    r = TranscriptRenderer()
    assert r.monologue("thinking...") == "<monologue>\nthinking...\n</monologue>"


def test_tools_default_tag():
    r = TranscriptRenderer()
    assert r.tools("ran ls") == "<tools>\nran ls\n</tools>"


def test_code_without_language():
    r = TranscriptRenderer()
    assert r.code("print(1)") == "<code>\nprint(1)\n</code>"


def test_code_with_language_attribute():
    r = TranscriptRenderer()
    rendered = r.code("print(1)", language="python")
    assert rendered == '<code lang="python">\nprint(1)\n</code>'


def test_speaker_attribute_is_rendered():
    r = TranscriptRenderer()
    rendered = r.chat("привет", speaker="erafox")
    assert rendered == '<chat speaker="erafox">\nпривет\n</chat>'


# --------------------------------------------------------------------------- #
# Cyrillic / Unicode handling
# --------------------------------------------------------------------------- #
def test_cyrillic_tag_preset():
    r = TranscriptRenderer(CYRILLIC_TAGS)
    assert r.chat("Здравствуйте") == "<ЧАТ>\nЗдравствуйте\n</ЧАТ>"
    assert r.monologue("обдумываю") == "<МОНОЛОГ>\nобдумываю\n</МОНОЛОГ>"
    assert r.code("print('Привет')") == "<КОД>\nprint('Привет')\n</КОД>"
    assert r.tools("ls -la") == "<ИНСТРУМЕНТЫ>\nls -la\n</ИНСТРУМЕНТЫ>"


def test_unicode_text_is_preserved_verbatim():
    r = TranscriptRenderer()
    text = "emoji 🚀 mixed Кириллица 中文"
    assert text in r.chat(text)


# --------------------------------------------------------------------------- #
# Entry / multi-entry rendering
# --------------------------------------------------------------------------- #
def test_render_entry_passes_through_extra_attributes():
    r = TranscriptRenderer()
    entry = Entry(
        kind=EntryKind.TOOLS,
        text="result",
        attributes={"tool": "shell", "exit_code": 0},
    )
    rendered = r.render_entry(entry)
    assert rendered.startswith('<tools tool="shell" exit_code="0">')


def test_render_joins_with_blank_line_by_default():
    r = TranscriptRenderer()
    out = r.render(
        [
            Entry(EntryKind.CHAT, "hi"),
            Entry(EntryKind.MONOLOGUE, "thinking"),
        ]
    )
    assert out == "<chat>\nhi\n</chat>\n\n<monologue>\nthinking\n</monologue>"


def test_render_respects_custom_separator():
    r = TranscriptRenderer(separator="\n---\n")
    out = r.render([Entry(EntryKind.CHAT, "a"), Entry(EntryKind.CHAT, "b")])
    assert "\n---\n" in out


def test_render_empty_iterable_returns_empty_string():
    r = TranscriptRenderer()
    assert r.render([]) == ""


# --------------------------------------------------------------------------- #
# Indentation
# --------------------------------------------------------------------------- #
def test_indent_pads_each_line():
    r = TranscriptRenderer(indent=2)
    rendered = r.chat("line1\nline2")
    assert rendered == "<chat>\n  line1\n  line2\n</chat>"


def test_indent_preserves_blank_lines():
    r = TranscriptRenderer(indent=4)
    rendered = r.monologue("a\n\nb")
    assert rendered == "<monologue>\n    a\n\n    b\n</monologue>"


# --------------------------------------------------------------------------- #
# Attribute escaping
# --------------------------------------------------------------------------- #
def test_attribute_values_are_escaped():
    r = TranscriptRenderer()
    rendered = r.chat("body", speaker='quote"&<>')
    assert 'speaker="quote&quot;&amp;&lt;&gt;"' in rendered


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def test_missing_tag_mapping_raises():
    incomplete = {EntryKind.CHAT: "chat"}
    with pytest.raises(ValueError, match="missing entries"):
        TranscriptRenderer(incomplete)


def test_negative_indent_raises():
    with pytest.raises(ValueError, match="indent"):
        TranscriptRenderer(indent=-1)


def test_language_attribute_only_valid_for_code():
    r = TranscriptRenderer()
    with pytest.raises(ValueError, match="CODE"):
        r.render_entry(Entry(EntryKind.CHAT, "hi", language="python"))


def test_invalid_attribute_name_raises():
    r = TranscriptRenderer()
    bad = Entry(EntryKind.CHAT, "hi", attributes={"not an ident": "x"})
    with pytest.raises(ValueError, match="invalid attribute name"):
        r.render_entry(bad)


# --------------------------------------------------------------------------- #
# Preset sanity check
# --------------------------------------------------------------------------- #
def test_english_and_cyrillic_presets_cover_all_kinds():
    for preset in (ENGLISH_TAGS, CYRILLIC_TAGS):
        for kind in EntryKind:
            assert kind in preset
            assert preset[kind]  # non-empty string
