"""Tests for the sysrfx_core.engine.ChatRenderer builder."""

from __future__ import annotations

import pytest

from sysrfx_core.engine import ChatRenderer, Section, sanitize_control_chars


def test_empty_render_returns_empty_string() -> None:
    assert ChatRenderer().render() == ""
    assert str(ChatRenderer()) == ""
    assert len(ChatRenderer()) == 0


def test_chat_only_renders_single_tag() -> None:
    rendered = ChatRenderer().chat("Привет").render()
    assert rendered == "<ЧАТ>Привет</ЧАТ>"


def test_builder_returns_self_for_chaining() -> None:
    builder = ChatRenderer()
    assert builder.chat("a") is builder
    assert builder.monologue("b") is builder
    assert builder.code("c") is builder
    assert builder.tools("d") is builder


def test_full_chain_preserves_call_order() -> None:
    rendered = (
        ChatRenderer()
        .chat("Привет, erafox.")
        .monologue("Need to confirm requirements before estimating.")
        .code("print('hello')")
        .tools("ls -la")
        .render()
    )
    assert rendered == (
        "<ЧАТ>Привет, erafox.</ЧАТ>\n"
        "<МОНОЛОГ>Need to confirm requirements before estimating.</МОНОЛОГ>\n"
        "<КОД>print('hello')</КОД>\n"
        "<ИНСТРУМЕНТЫ>ls -la</ИНСТРУМЕНТЫ>"
    )


def test_arbitrary_call_order_is_preserved() -> None:
    rendered = (
        ChatRenderer()
        .tools("ls")
        .chat("hi")
        .code("x = 1")
        .monologue("thinking")
        .render()
    )
    assert rendered == (
        "<ИНСТРУМЕНТЫ>ls</ИНСТРУМЕНТЫ>\n"
        "<ЧАТ>hi</ЧАТ>\n"
        "<КОД>x = 1</КОД>\n"
        "<МОНОЛОГ>thinking</МОНОЛОГ>"
    )


def test_repeated_sections_each_emit_their_own_tag() -> None:
    rendered = (
        ChatRenderer()
        .chat("first")
        .chat("second")
        .render()
    )
    assert rendered == "<ЧАТ>first</ЧАТ>\n<ЧАТ>second</ЧАТ>"


def test_literal_chat_tag_in_content_is_escaped() -> None:
    rendered = ChatRenderer().monologue("input contained <CHAT> earlier").render()
    assert rendered == "<МОНОЛОГ>input contained &lt;CHAT&gt; earlier</МОНОЛОГ>"


def test_literal_cyrillic_tag_in_content_is_escaped() -> None:
    rendered = ChatRenderer().chat("user said </ЧАТ> on purpose").render()
    assert rendered == "<ЧАТ>user said &lt;/ЧАТ&gt; on purpose</ЧАТ>"
    # The escaped content must not contain a raw closing tag that could
    # confuse a downstream parser.
    assert "</ЧАТ>" in rendered  # exactly one — the legitimate closer
    assert rendered.count("</ЧАТ>") == 1


def test_ampersand_is_escaped_first() -> None:
    # If '&' were escaped after '<' or '>' we'd end up with '&amp;lt;'.
    rendered = ChatRenderer().chat("a & <b>").render()
    assert rendered == "<ЧАТ>a &amp; &lt;b&gt;</ЧАТ>"


def test_multiline_content_preserved() -> None:
    payload = "line 1\nline 2\n\nline 4"
    rendered = ChatRenderer().code(payload).render()
    assert rendered == f"<КОД>{payload}</КОД>"


def test_empty_string_content_is_allowed() -> None:
    rendered = ChatRenderer().chat("").render()
    assert rendered == "<ЧАТ></ЧАТ>"


def test_unicode_content_is_preserved() -> None:
    rendered = ChatRenderer().chat("日本語 — Русский — emoji 🚀").render()
    assert rendered == "<ЧАТ>日本語 — Русский — emoji 🚀</ЧАТ>"


@pytest.mark.parametrize("method", ["chat", "monologue", "code", "tools"])
def test_non_string_content_raises_type_error(method: str) -> None:
    builder = ChatRenderer()
    with pytest.raises(TypeError):
        getattr(builder, method)(123)  # type: ignore[arg-type]


def test_sections_snapshot_is_immutable() -> None:
    builder = ChatRenderer().chat("hi")
    snapshot = builder.sections
    assert snapshot == (Section(tag="ЧАТ", content="hi"),)
    # Mutating the builder afterwards must not retroactively change the snapshot.
    builder.code("x = 1")
    assert snapshot == (Section(tag="ЧАТ", content="hi"),)
    assert len(builder.sections) == 2


def test_extend_appends_prebuilt_sections() -> None:
    builder = ChatRenderer().chat("hi")
    builder.extend([
        Section(tag="КОД", content="x = 1"),
        Section(tag="ИНСТРУМЕНТЫ", content="ls"),
    ])
    assert builder.render() == (
        "<ЧАТ>hi</ЧАТ>\n"
        "<КОД>x = 1</КОД>\n"
        "<ИНСТРУМЕНТЫ>ls</ИНСТРУМЕНТЫ>"
    )


def test_extend_rejects_unknown_tag() -> None:
    builder = ChatRenderer()
    with pytest.raises(ValueError):
        builder.extend([Section(tag="BOGUS", content="x")])


def test_extend_rejects_non_string_content() -> None:
    builder = ChatRenderer()
    with pytest.raises(TypeError):
        builder.extend([Section(tag="ЧАТ", content=42)])  # type: ignore[arg-type]


def test_tab_newline_cr_are_preserved_by_sanitizer() -> None:
    assert sanitize_control_chars("a\tb\nc\rd") == "a\tb\nc\rd"


def test_nul_and_bel_are_escaped_by_sanitizer() -> None:
    assert sanitize_control_chars("a\x00b\x07c") == "a\\u0000b\\u0007c"


def test_del_is_escaped_by_sanitizer() -> None:
    assert sanitize_control_chars("x\x7fy") == "x\\u007fy"


def test_all_forbidden_c0_controls_are_escaped() -> None:
    # 0x00-0x08, 0x0B, 0x0C, 0x0E-0x1F, 0x7F should all be replaced.
    forbidden = (
        [chr(i) for i in range(0x00, 0x09)]
        + [chr(0x0B), chr(0x0C)]
        + [chr(i) for i in range(0x0E, 0x20)]
        + [chr(0x7F)]
    )
    payload = "".join(forbidden)
    sanitized = sanitize_control_chars(payload)
    # No raw control byte should survive.
    for ch in forbidden:
        assert ch not in sanitized
    # Each one should appear as its escaped form.
    for ch in forbidden:
        assert f"\\u{ord(ch):04x}" in sanitized


def test_render_escapes_control_chars_in_content() -> None:
    rendered = ChatRenderer().tools("a\x00b\x01c").render()
    assert rendered == "<ИНСТРУМЕНТЫ>a\\u0000b\\u0001c</ИНСТРУМЕНТЫ>"


def test_render_preserves_tabs_and_newlines_inside_content() -> None:
    rendered = ChatRenderer().code("def f():\n\treturn 1\r\n").render()
    assert rendered == "<КОД>def f():\n\treturn 1\r\n</КОД>"


def test_render_control_char_sanitization_runs_before_xml_escape() -> None:
    # A raw '<' followed by a NUL should yield '&lt;' followed by '\u0000',
    # and not double-escape the backslash from the sanitizer output.
    rendered = ChatRenderer().chat("<\x00&").render()
    assert rendered == "<ЧАТ>&lt;\\u0000&amp;</ЧАТ>"


def test_complex_log_scenario_roundtrip() -> None:
    """A representative pipeline payload renders deterministically."""
    rendered = (
        ChatRenderer()
        .chat("erafox: нужна оценка по задаче X")
        .monologue("Estimating: needs requirement clarification before quoting.")
        .code("def estimate(x: int) -> int:\n    return x * 2")
        .tools("git status\n# nothing to commit")
        .chat("Den: уточни дедлайн, пожалуйста.")
        .render()
    )
    # Output must contain exactly 5 opening tags and 5 closing tags.
    for tag in ("ЧАТ", "МОНОЛОГ", "КОД", "ИНСТРУМЕНТЫ"):
        assert rendered.count(f"<{tag}>") == rendered.count(f"</{tag}>")
    assert rendered.count("<ЧАТ>") == 2
    assert rendered.count("<МОНОЛОГ>") == 1
    assert rendered.count("<КОД>") == 1
    assert rendered.count("<ИНСТРУМЕНТЫ>") == 1
