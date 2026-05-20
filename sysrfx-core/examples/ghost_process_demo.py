"""End-to-end demo of `ChatRenderer` on a fictional log scenario.

The strings below are *scripted demo fixtures*, not live reasoning — the
purpose of this script is to exercise the builder's chaining, ordering, and
escaping on a realistic multi-section payload and print the rendered output.

Run with:

    python examples/ghost_process_demo.py
"""

from __future__ import annotations

from sysrfx_core.engine import ChatRenderer


def build_scenario() -> str:
    """Render a fictional "ghost process" investigation log."""
    return (
        ChatRenderer()
        .chat("erafox: на сервере db-01 загрузка CPU 80%, но top ничего не показывает.")
        .monologue(
            "Hypothesis: a process is hiding from `top` either because (a) its "
            "name is being filtered by a user-side `~/.toprc`, (b) it lives in a "
            "different PID namespace (container), or (c) the kernel is reporting "
            "the CPU time against a kthread. Plan: rule these out by reading raw "
            "/proc directly and comparing per-CPU stats against the sum of "
            "per-process stats."
        )
        .tools("ssh db-01 'uptime && nproc'")
        .code(
            "# Sum CPU% across all PIDs in /proc and compare to mpstat\n"
            "awk '{s+=$1} END {print s}' /proc/*/stat 2>/dev/null"
        )
        .chat("Den: предварительно похоже на kthread, перепроверяю /proc напрямую.")
        .monologue(
            "If the per-PID sum is far below the per-CPU total, the load lives "
            "in kernel threads — those show up in /proc but `top` hides them by "
            "default (press `H` or `K` to toggle)."
        )
        .tools("ssh db-01 'ps -eLo pid,comm,pcpu --sort=-pcpu | head'")
        .chat("Den: подтверждено, виновник — kthread `kswapd0`. Эскалирую в DBA.")
        .render()
    )


def main() -> None:
    rendered = build_scenario()
    print(rendered)
    # Cheap structural assertions so the demo doubles as a smoke check.
    assert rendered.count("<ЧАТ>") == 3
    assert rendered.count("<МОНОЛОГ>") == 2
    assert rendered.count("<КОД>") == 1
    assert rendered.count("<ИНСТРУМЕНТЫ>") == 2
    for tag in ("ЧАТ", "МОНОЛОГ", "КОД", "ИНСТРУМЕНТЫ"):
        assert rendered.count(f"<{tag}>") == rendered.count(f"</{tag}>")


if __name__ == "__main__":
    main()
