import subprocess
import unittest

from src.sysrfx_core.collector import CommandSpec, SysrfxCollector


class SysrfxCollectorTest(unittest.TestCase):
    def test_render_snapshot_wraps_code_and_tools_sections(self):
        specs = [
            CommandSpec("packages", ("python", "--version"), "code", "package stream"),
            CommandSpec("network", ("python", "--version"), "tools", "network stream"),
        ]

        def runner(command, timeout_seconds):
            del command, timeout_seconds
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="Proto Local Address\ntcp 0.0.0.0:80\n", stderr="")

        collector = SysrfxCollector(runner=runner)
        output = collector.render_snapshot(collector.collect(specs))

        self.assertIn("<КОД>", output)
        self.assertIn("<ИНСТРУМЕНТЫ>", output)
        self.assertIn("[Proto Local Address]", output)
        self.assertIn("renderer=tools", output)

    def test_redacts_command_line_secrets(self):
        text = "python app.py --token=abc123 password hunter2 api_key=xyz"

        redacted = SysrfxCollector.redact(text)

        self.assertNotIn("abc123", redacted)
        self.assertNotIn("hunter2", redacted)
        self.assertNotIn("xyz", redacted)
        self.assertIn("[REDACTED]", redacted)


if __name__ == "__main__":
    unittest.main()
