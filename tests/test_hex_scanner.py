import os
import unittest

from src.sysrfx_core.hex_scanner import (
    ExternalProcessDeniedError,
    MemoryAuditor,
    TrustedProcessAccessDeniedError,
    TrustedProcessDiscovery,
    find_pattern_offsets,
    parse_signature,
)


class HexScannerTest(unittest.TestCase):
    def test_parse_signature_supports_wildcards(self):
        pattern = parse_signature("48 8B ?? 00")

        self.assertEqual(pattern.values, b"\x48\x8b\x00\x00")
        self.assertEqual(pattern.mask, (True, True, False, True))
        self.assertTrue(pattern.has_wildcards)

    def test_find_pattern_offsets_exact_and_wildcard(self):
        self.assertEqual(find_pattern_offsets(b"abcabc", parse_signature(b"abc")), [0, 3])
        self.assertEqual(find_pattern_offsets(b"A1Z A2Z", parse_signature("41 ?? 5A")), [0, 4])

    def test_external_pid_is_denied_by_default(self):
        auditor = MemoryAuditor(current_process_only=True)

        with self.assertRaises(ExternalProcessDeniedError):
            auditor._assert_pid_allowed(os.getpid() + 100000)

    def test_current_process_name_is_normalized(self):
        self.assertTrue(MemoryAuditor.current_process_name())
        self.assertEqual(
            MemoryAuditor._normalize_process_name("  NOTEPAD.EXE "),
            "notepad.exe",
        )

    def test_trusted_discovery_accepts_current_process(self):
        peer = TrustedProcessDiscovery().inspect_pid(os.getpid(), "python")

        self.assertTrue(peer.current_process)
        self.assertTrue(peer.same_user)
        self.assertFalse(peer.memory_access_permitted)

    def test_trusted_discovery_accepts_explicit_pid_without_memory_permission(self):
        peer = TrustedProcessDiscovery([999999]).inspect_pid(999999, "sysrfx-child.exe")

        self.assertTrue(peer.explicitly_trusted)
        self.assertFalse(peer.current_process)
        self.assertFalse(peer.memory_access_permitted)

    def test_trusted_discovery_rejects_unknown_pid(self):
        with self.assertRaises(TrustedProcessAccessDeniedError):
            TrustedProcessDiscovery().inspect_pid(999999)

    def test_memory_auditor_discovers_trusted_peer_metadata(self):
        auditor = MemoryAuditor(trusted_pids=[999999])

        peer = auditor.discover_trusted_peer(999999, "sysrfx-child.exe")

        self.assertEqual(peer.pid, 999999)
        self.assertFalse(peer.memory_access_permitted)


if __name__ == "__main__":
    unittest.main()
