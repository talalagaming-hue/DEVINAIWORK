"""sysrfx-core: tagged-section rendering engine for chat logs."""

from sysrfx_core.collector import (
    Collector,
    CommandResult,
    Runner,
    null_runner,
    subprocess_runner,
)
from sysrfx_core.engine import ChatRenderer, Section, sanitize_control_chars

__all__ = [
    "ChatRenderer",
    "Collector",
    "CommandResult",
    "Runner",
    "Section",
    "null_runner",
    "sanitize_control_chars",
    "subprocess_runner",
]
__version__ = "0.1.0"
