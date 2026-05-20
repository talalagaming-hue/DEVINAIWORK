"""Stress test for ChatRenderer with large, adversarial synthetic payloads.

This test does NOT capture any real system state. It generates synthetic
fixtures that *resemble* the shape of common shell outputs (long whitespace-
delimited columns, many lines) while deliberately seeding every kind of byte
the renderer has to handle correctly:

- All forbidden C0 control characters (``\\x00`` - ``\\x08``, ``\\x0B``,
  ``\\x0C``, ``\\x0E`` - ``\\x1F``) and DEL (``\\x7F``).
- Dense ``<``, ``>``, ``&`` so the XML escape path is exercised heavily.
- Literal ``<ЧАТ>``-style tag strings inside content to make sure they cannot
  break out into sibling sections.
- Embedded newlines, tabs, and carriage returns to confirm whitespace is
  preserved.
- Multi-byte UTF-8 characters mixed in.

The test also enforces a soft performance budget so a regression that makes
``render()`` quadratic shows up as a CI failure.
"""

from __future__ import annotations

import random
import re
import time
from typing import List

import pytest

from sysrfx_core.engine import ChatRenderer


def _build_dpkg_like_lines(rng: random.Random, n_lines: int) -> str:
    """Lines shaped like ``dpkg -l`` output, with synthetic package names."""
    lines: List[str] = [
        "Desired=Unknown/Install/Remove/Purge/Hold",
        "| Status=Not/Inst/Conf-files/Unpacked/halF-conf/Half-inst/trig-aWait/Trig-pend",
        "|/ Err?=(none)/Reinst-required (Status,Err: uppercase=bad)",
        "+++-============================================-=====================-============-",
    ]
    for i in range(n_lines):
        name = f"synthpkg-{i:06d}"
        version = f"{rng.randint(0, 9)}.{rng.randint(0, 99)}.{rng.randint(0, 999)}-{rng.randint(1, 50)}"
        arch = rng.choice(["amd64", "arm64", "all", "i386"])
        desc = "fixture package <test> & demo " + ("x" * rng.randint(8, 64))
        lines.append(f"ii  {name:<44} {version:<21} {arch:<12} {desc}")
    return "\n".join(lines)


def _build_netstat_like_lines(rng: random.Random, n_lines: int) -> str:
    """Lines shaped like ``netstat -tulpn`` output, with synthetic addresses."""
    lines: List[str] = [
        "Active Internet connections (only servers)",
        "Proto Recv-Q Send-Q Local Address           Foreign Address         State       PID/Program name",
    ]
    for i in range(n_lines):
        proto = rng.choice(["tcp", "tcp6", "udp", "udp6"])
        port = rng.randint(1024, 65535)
        local = f"0.0.0.0:{port}"
        foreign = "0.0.0.0:*"
        state = rng.choice(["LISTEN", ""])
        prog = f"{i % 30000}/synthproc-{i:04d}"
        lines.append(f"{proto:<6}{0:>7}{0:>7} {local:<23} {foreign:<23} {state:<11} {prog}")
    return "\n".join(lines)


def _build_ps_like_lines(rng: random.Random, n_lines: int) -> str:
    """Lines shaped like ``ps auxf`` output, with synthetic commands."""
    lines: List[str] = [
        "USER       PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND",
    ]
    for i in range(n_lines):
        user = rng.choice(["synth", "root", "daemon", "nobody"])
        pid = i + 1
        cpu = rng.uniform(0.0, 5.0)
        mem = rng.uniform(0.0, 3.0)
        vsz = rng.randint(1000, 5_000_000)
        rss = rng.randint(100, 500_000)
        # Commands deliberately include shell operators that must be escaped.
        cmd = rng.choice([
            "sleep 30 && echo done > /tmp/x",
            "grep -E '<tag>|&amp;' input.log",
            "python3 -m synth.worker --shard=" + str(i),
            "sh -c 'while true; do echo .; sleep 1; done'",
        ])
        lines.append(
            f"{user:<10} {pid:>5} {cpu:4.1f} {mem:4.1f} {vsz:>7} {rss:>6} ?        Ss   00:00   0:00 {cmd}"
        )
    return "\n".join(lines)


def _build_adversarial_blob(rng: random.Random, size_bytes: int) -> str:
    """Random adversarial blob that includes every forbidden control char.

    The blob is roughly ``size_bytes`` long. It mixes:
      * the full set of forbidden C0 control characters,
      * dense ``<``, ``>``, ``&``,
      * literal closing tags for every known section,
      * multi-byte unicode.
    """
    forbidden_controls = (
        [chr(i) for i in range(0x00, 0x09)]
        + [chr(0x0B), chr(0x0C)]
        + [chr(i) for i in range(0x0E, 0x20)]
        + [chr(0x7F)]
    )
    bait = [
        "<ЧАТ>", "</ЧАТ>", "<МОНОЛОГ>", "</МОНОЛОГ>",
        "<КОД>", "</КОД>", "<ИНСТРУМЕНТЫ>", "</ИНСТРУМЕНТЫ>",
        "<script>", "&amp;", "&#0;", "&#x41;",
        "日本語", "Русский", "🚀",
        "<<>>&&", "&&&<<<>>>",
    ]
    chunks: List[str] = []
    total = 0
    while total < size_bytes:
        choice = rng.random()
        if choice < 0.15:
            piece = rng.choice(forbidden_controls)
        elif choice < 0.4:
            piece = rng.choice(bait)
        else:
            piece = "".join(
                rng.choice("abcdefghijklmnopqrstuvwxyz0123456789 <>&\n\t")
                for _ in range(rng.randint(8, 64))
            )
        chunks.append(piece)
        total += len(piece.encode("utf-8"))
    return "".join(chunks)


@pytest.fixture(scope="module")
def stress_fixture() -> dict:
    rng = random.Random(0xC0FFEE)
    dpkg_block = _build_dpkg_like_lines(rng, n_lines=5_000)
    netstat_block = _build_netstat_like_lines(rng, n_lines=2_000)
    ps_block = _build_ps_like_lines(rng, n_lines=2_000)
    adversarial = _build_adversarial_blob(rng, size_bytes=512 * 1024)
    return {
        "dpkg": dpkg_block,
        "netstat": netstat_block,
        "ps": ps_block,
        "adversarial": adversarial,
    }


def test_stress_payload_total_input_size(stress_fixture: dict) -> None:
    total = sum(len(v.encode("utf-8")) for v in stress_fixture.values())
    # Should be on the order of ~1 MB of synthetic data; assert a lower bound
    # so the fixture cannot silently shrink to nothing.
    assert total > 750_000, f"stress fixture too small: {total} bytes"


def test_stress_render_is_well_formed(stress_fixture: dict) -> None:
    rendered = (
        ChatRenderer()
        .chat("erafox: synthetic stress fixture; no real system state captured.")
        .tools(stress_fixture["netstat"])
        .code(stress_fixture["dpkg"])
        .tools(stress_fixture["ps"])
        .monologue("Adversarial blob follows.")
        .code(stress_fixture["adversarial"])
        .render()
    )

    # No forbidden C0 control character (other than tab/newline/CR) should
    # survive in the rendered output -- they must all be escaped to \uXXXX.
    forbidden = (
        [chr(i) for i in range(0x00, 0x09)]
        + [chr(0x0B), chr(0x0C)]
        + [chr(i) for i in range(0x0E, 0x20)]
        + [chr(0x7F)]
    )
    for ch in forbidden:
        assert ch not in rendered, f"forbidden control char U+{ord(ch):04X} leaked"

    # Tag opens/closes balance exactly.
    for tag in ("ЧАТ", "МОНОЛОГ", "КОД", "ИНСТРУМЕНТЫ"):
        assert rendered.count(f"<{tag}>") == rendered.count(f"</{tag}>")

    # Section counts match what we appended.
    assert rendered.count("<ЧАТ>") == 1
    assert rendered.count("<МОНОЛОГ>") == 1
    assert rendered.count("<КОД>") == 2
    assert rendered.count("<ИНСТРУМЕНТЫ>") == 2

    # Literal '<ЧАТ>' that appeared inside the adversarial blob must have been
    # escaped to '&lt;ЧАТ&gt;', i.e. it cannot survive as a real opening tag.
    # We assert that the number of real opening tags equals the number of real
    # closing tags by parsing instead of by counting raw substrings:
    open_close = re.findall(r"</?(ЧАТ|МОНОЛОГ|КОД|ИНСТРУМЕНТЫ)>", rendered)
    # Even number of matches (each open has a close).
    assert len(open_close) % 2 == 0
    # And exactly twice the section count.
    assert len(open_close) == 2 * 6

    # No raw '&' that isn't part of an entity reference.
    # All '&' should be '&amp;' (or '&lt;' / '&gt;' technically don't have '&'
    # followed by 'amp', but we just check there's no stray '&' followed by
    # whitespace, end-of-string, or a non-entity char).
    stray_amp = re.search(r"&(?!amp;|lt;|gt;|quot;|apos;)", rendered)
    assert stray_amp is None, f"stray '&' at position {stray_amp.start() if stray_amp else -1}"


def test_stress_render_perf_budget(stress_fixture: dict) -> None:
    """Soft perf budget: render the full payload in well under 5 seconds.

    The intent is to catch accidental quadratic regressions (e.g. someone
    swaps the str.join for repeated string concatenation). A modern CI worker
    handles the ~1 MB fixture in tens of milliseconds; we set a generous
    upper bound so this is robust to noisy runners.
    """
    builder = (
        ChatRenderer()
        .tools(stress_fixture["netstat"])
        .code(stress_fixture["dpkg"])
        .tools(stress_fixture["ps"])
        .code(stress_fixture["adversarial"])
    )
    start = time.perf_counter()
    rendered = builder.render()
    elapsed = time.perf_counter() - start
    assert elapsed < 5.0, f"render took {elapsed:.3f}s, perf budget exceeded"
    # And the output must actually be non-trivially long.
    assert len(rendered) > 500_000


def test_stress_render_is_idempotent(stress_fixture: dict) -> None:
    """Rendering the same builder twice must produce byte-identical output."""
    builder = ChatRenderer().code(stress_fixture["adversarial"]).tools(stress_fixture["ps"])
    a = builder.render()
    b = builder.render()
    assert a == b
