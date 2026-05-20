"""sysrfx-core: tagged-section rendering engine for chat logs."""

from sysrfx_core.engine import ChatRenderer, Section, sanitize_control_chars

__all__ = ["ChatRenderer", "Section", "sanitize_control_chars"]
__version__ = "0.1.0"
