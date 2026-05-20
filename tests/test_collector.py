import subprocess
import tempfile
import unittest
from pathlib import Path

from src.sysrfx_core.collector import CommandSpec, SysrfxCollector, parse_args


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

    def test_parse_args_rejects_non_positive_timeout(self):
        with self.assertRaises(SystemExit):
            parse_args(["--timeout", "0"])

        with self.assertRaises(SystemExit):
            parse_args(["--timeout", "-5"])

        self.assertEqual(parse_args(["--timeout", "1"]).timeout, 1)

    def test_empty_specs_do_not_run_default_collection(self):
        def runner(command, timeout_seconds):
            del timeout_seconds
            self.fail(f"unexpected command execution: {command}")

        collector = SysrfxCollector(runner=runner)

        self.assertEqual(collector.collect([]), [])

    def test_empty_results_do_not_run_default_collection(self):
        def runner(command, timeout_seconds):
            del timeout_seconds
            self.fail(f"unexpected command execution: {command}")

        collector = SysrfxCollector(runner=runner)
        with tempfile.TemporaryDirectory() as tmpdir:
            output = collector.write_snapshot(Path(tmpdir) / "empty-snap.txt", results=[])

            text = output.read_text(encoding="utf-8")

        self.assertIn("<ЧАТ>", text)
        self.assertIn("sysrfx-snap готов", text)
        self.assertNotIn("command=dpkg -l", text)


if __name__ == "__main__":
    unittest.main()
