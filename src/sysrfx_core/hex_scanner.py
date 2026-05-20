"""Constrained Windows memory auditing helpers for sysrfx-core.

The auditor intentionally limits live memory reads and writes to the current
process. That keeps integration tests useful for defensive instrumentation
without shipping an arbitrary cross-process memory patcher.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


class HexScannerError(RuntimeError):
    """Base error for memory-auditing failures."""


class UnsupportedPlatformError(HexScannerError):
    """Raised when Windows-only APIs are requested elsewhere."""


class ExternalProcessDeniedError(HexScannerError):
    """Raised when a caller attempts to audit another process."""


class ProcessNotFoundError(HexScannerError):
    """Raised when a named process cannot be found."""


class MemoryAccessError(HexScannerError):
    """Raised when a Windows memory API call fails."""


class TrustedProcessAccessDeniedError(HexScannerError):
    """Raised when a process does not satisfy trusted-peer policy."""


@dataclass(frozen=True)
class Pattern:
    """Parsed byte signature with optional wildcards."""

    values: bytes
    mask: tuple[bool, ...]

    @property
    def length(self) -> int:
        return len(self.values)

    @property
    def has_wildcards(self) -> bool:
        return not all(self.mask)


@dataclass(frozen=True)
class MemoryPatch:
    """Result of a successful in-process memory patch."""

    address: int
    bytes_written: int


@dataclass(frozen=True)
class TrustedPeer:
    """Trusted peer metadata for IPC integrity checks."""

    pid: int
    process_name: str | None
    same_user: bool
    explicitly_trusted: bool
    name_trusted: bool
    current_process: bool
    memory_access_permitted: bool = False


@dataclass(frozen=True)
class DebugSession:
    """Safe diagnostic session metadata for a trusted peer."""

    peer: TrustedPeer
    attached: bool
    live_memory_access: bool
    reason: str


class TrustedProcessDiscovery:
    """Discover trusted peers without granting cross-process memory access."""

    DEFAULT_TRUSTED_NAMES = {"sysrfx-worker", "sysrfx-worker.exe", "notepad.exe"}

    def __init__(self, trusted_pids: Iterable[int] = (), trusted_names: Iterable[str] | None = None):
        self.trusted_pids = {int(pid) for pid in trusted_pids}
        names = self.DEFAULT_TRUSTED_NAMES if trusted_names is None else trusted_names
        self.trusted_names = {name.strip().lower() for name in names if name.strip()}

    def inspect_pid(self, pid: int, process_name: str | None = None) -> TrustedPeer:
        if pid <= 0:
            raise ValueError("pid must be greater than 0")
        same_user = self._same_user(pid)
        explicitly_trusted = pid in self.trusted_pids
        normalized_name = self._normalize_name(process_name)
        name_trusted = normalized_name in self.trusted_names
        current_process = pid == os.getpid()
        if not (same_user or explicitly_trusted or name_trusted or current_process):
            raise TrustedProcessAccessDeniedError(f"pid is not a trusted sysrfx peer: {pid}")
        return TrustedPeer(
            pid=pid,
            process_name=normalized_name,
            same_user=same_user,
            explicitly_trusted=explicitly_trusted,
            name_trusted=name_trusted,
            current_process=current_process,
            memory_access_permitted=current_process,
        )

    def is_trusted(self, pid: int) -> bool:
        try:
            self.inspect_pid(pid)
        except TrustedProcessAccessDeniedError:
            return False
        return True

    @staticmethod
    def _same_user(pid: int) -> bool:
        if pid == os.getpid():
            return True
        proc_path = Path("/proc") / str(pid)
        if proc_path.exists() and hasattr(os, "getuid"):
            try:
                return proc_path.stat().st_uid == os.getuid()
            except OSError:
                return False
        return False

    @staticmethod
    def _normalize_name(process_name: str | None) -> str | None:
        if process_name is None:
            return None
        normalized = process_name.strip().lower()
        return normalized or None


class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(wintypes.ULONG)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.CHAR * 260),
    ]


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", wintypes.LPVOID),
        ("AllocationBase", wintypes.LPVOID),
        ("AllocationProtect", wintypes.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    ]


class DebugEngine:
    """Audit byte patterns in the current process using Windows APIs.

    Trusted peer discovery is metadata-only. It supports IPC integrity checks
    and allow-list validation, but it does not authorize external memory reads
    or writes.
    """

    PROCESS_QUERY_INFORMATION = 0x0400
    PROCESS_VM_OPERATION = 0x0008
    PROCESS_VM_READ = 0x0010
    PROCESS_VM_WRITE = 0x0020
    TH32CS_SNAPPROCESS = 0x00000002
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
    MEM_COMMIT = 0x1000
    PAGE_GUARD = 0x100
    PAGE_NOACCESS = 0x01
    READABLE_PAGE_FLAGS = {0x02, 0x04, 0x08, 0x20, 0x40, 0x80}

    def __init__(
        self,
        current_process_only: bool = True,
        max_region_size: int = 8 * 1024 * 1024,
        trusted_pids: Iterable[int] = (),
        trusted_names: Iterable[str] | None = None,
    ):
        if max_region_size <= 0:
            raise ValueError("max_region_size must be greater than 0")
        self.current_process_only = current_process_only
        self.max_region_size = max_region_size
        self.trusted_discovery = TrustedProcessDiscovery(trusted_pids, trusted_names)

    def discover_trusted_peer(self, pid: int, process_name: str | None = None) -> TrustedPeer:
        """Validate PID trust for IPC self-attestation workflows."""
        return self.trusted_discovery.inspect_pid(pid, process_name)

    def discover_trusted_peer_by_name(self, process_name: str) -> TrustedPeer:
        """Resolve a process name and validate it as a trusted IPC peer."""
        pid = self.find_process_id_by_name(process_name)
        return self.discover_trusted_peer(pid, self._normalize_process_name(process_name))

    def attach_to_process(self, pid: int, process_name: str | None = None) -> DebugSession:
        """Create a safe diagnostic session for a trusted peer.

        External peers are eligible for IPC self-attestation/crash-dump workflows
        only. Live debugger attachment and cross-process memory access remain
        disabled unless the target is the current process.
        """
        peer = self.discover_trusted_peer(pid, process_name)
        if peer.current_process:
            return DebugSession(
                peer=peer,
                attached=True,
                live_memory_access=True,
                reason="current process self-debug session",
            )
        return DebugSession(
            peer=peer,
            attached=False,
            live_memory_access=False,
            reason="trusted peer metadata accepted; live external debugging requires an offline dump or peer self-attestation",
        )

    def read_debug_memory(self, pid: int, address: int, size: int, process_name: str | None = None) -> bytes:
        """Read memory for a current-process debug session only."""
        if address <= 0:
            raise ValueError("address must be greater than 0")
        if size <= 0:
            raise ValueError("size must be greater than 0")
        session = self.attach_to_process(pid, process_name)
        if not session.live_memory_access:
            raise ExternalProcessDeniedError("external live debug memory reads are disabled; use offline dumps")
        handle = self._open_process(pid, write=False)
        try:
            return self._read_process_memory(handle, address, size)
        finally:
            self._close_real_handle(handle)

    def write_debug_memory(self, pid: int, address: int, data: bytes, process_name: str | None = None) -> MemoryPatch:
        """Write memory for a current-process debug session only."""
        if address <= 0:
            raise ValueError("address must be greater than 0")
        if not data:
            raise ValueError("data must not be empty")
        session = self.attach_to_process(pid, process_name)
        if not session.live_memory_access:
            raise ExternalProcessDeniedError("external live debug memory writes are disabled; use offline dumps")
        handle = self._open_process(pid, write=True)
        try:
            written = self._write_process_memory(handle, address, data)
        finally:
            self._close_real_handle(handle)
        return MemoryPatch(address=address, bytes_written=written)

    def find_process_id_by_name(self, process_name: str) -> int:
        """Return the PID for a process name, preferring the current process."""
        target = self._normalize_process_name(process_name)
        if target == self.current_process_name():
            return os.getpid()
        self._ensure_windows()
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        snapshot = kernel32.CreateToolhelp32Snapshot(self.TH32CS_SNAPPROCESS, 0)
        if snapshot == self.INVALID_HANDLE_VALUE:
            self._raise_last_error("CreateToolhelp32Snapshot")

        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
        try:
            if not kernel32.Process32First(snapshot, ctypes.byref(entry)):
                self._raise_last_error("Process32First")
            while True:
                name = bytes(entry.szExeFile).split(b"\0", 1)[0].decode("mbcs", errors="ignore").lower()
                if name == target:
                    return int(entry.th32ProcessID)
                if not kernel32.Process32Next(snapshot, ctypes.byref(entry)):
                    break
        finally:
            kernel32.CloseHandle(snapshot)
        raise ProcessNotFoundError(f"process not found: {process_name}")

    def scan_pattern(self, process_name: str, signature: bytes | str | Pattern, max_matches: int = 256) -> list[int]:
        """Scan readable current-process memory for a byte signature."""
        if max_matches <= 0:
            raise ValueError("max_matches must be greater than 0")
        pattern = parse_signature(signature)
        pid = self.find_process_id_by_name(process_name)
        self._assert_pid_allowed(pid)
        handle = self._open_process(pid, write=False)
        try:
            return self._scan_handle(handle, pattern, max_matches)
        finally:
            self._close_real_handle(handle)

    def write_memory(self, process_name: str, address: int, data: bytes) -> MemoryPatch:
        """Patch current-process memory at an explicit address."""
        if address <= 0:
            raise ValueError("address must be greater than 0")
        if not data:
            raise ValueError("data must not be empty")
        pid = self.find_process_id_by_name(process_name)
        self._assert_pid_allowed(pid)
        handle = self._open_process(pid, write=True)
        try:
            written = self._write_process_memory(handle, address, data)
        finally:
            self._close_real_handle(handle)
        return MemoryPatch(address=address, bytes_written=written)

    def patch_first(self, process_name: str, signature: bytes | str, replacement: bytes) -> MemoryPatch:
        """Find the first current-process signature match and replace it."""
        pattern = parse_signature(signature)
        if len(replacement) != pattern.length:
            raise ValueError("replacement length must match signature length")
        matches = self.scan_pattern(process_name, pattern, max_matches=1)
        if not matches:
            raise MemoryAccessError("signature not found")
        return self.write_memory(process_name, matches[0], replacement)

    @staticmethod
    def current_process_name() -> str:
        return Path(sys.executable).name.lower()

    @staticmethod
    def _normalize_process_name(process_name: str) -> str:
        normalized = process_name.strip().lower()
        if not normalized:
            raise ValueError("process_name must not be empty")
        return normalized

    def _assert_pid_allowed(self, pid: int) -> None:
        if self.current_process_only and pid != os.getpid():
            raise ExternalProcessDeniedError(
                "live memory auditing is restricted to the current process; external process access is denied"
            )

    def _open_process(self, pid: int, write: bool) -> wintypes.HANDLE:
        self._ensure_windows()
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        access = self.PROCESS_QUERY_INFORMATION | self.PROCESS_VM_READ
        if write:
            access |= self.PROCESS_VM_OPERATION | self.PROCESS_VM_WRITE
        handle = kernel32.OpenProcess(access, False, pid)
        if not handle:
            self._raise_last_error("OpenProcess")
        return handle

    def _scan_handle(self, handle: wintypes.HANDLE, pattern: Pattern, max_matches: int) -> list[int]:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        address = 0
        matches: list[int] = []
        mbi = MEMORY_BASIC_INFORMATION()
        mbi_size = ctypes.sizeof(mbi)

        while kernel32.VirtualQueryEx(handle, ctypes.c_void_p(address), ctypes.byref(mbi), mbi_size):
            base = int(mbi.BaseAddress or 0)
            size = int(mbi.RegionSize or 0)
            if self._is_readable_region(mbi) and size > 0:
                for chunk_base, chunk in self._read_region_chunks(handle, base, size):
                    matches.extend(chunk_base + offset for offset in find_pattern_offsets(chunk, pattern))
                    if len(matches) >= max_matches:
                        return matches[:max_matches]
            next_address = base + size
            if next_address <= address:
                break
            address = next_address
        return matches

    def _read_region_chunks(self, handle: wintypes.HANDLE, base: int, size: int) -> Iterable[tuple[int, bytes]]:
        remaining = size
        offset = 0
        while remaining > 0:
            chunk_size = min(remaining, self.max_region_size)
            data = self._read_process_memory(handle, base + offset, chunk_size)
            if data:
                yield base + offset, data
            remaining -= chunk_size
            offset += chunk_size

    @classmethod
    def _is_readable_region(cls, mbi: MEMORY_BASIC_INFORMATION) -> bool:
        if mbi.State != cls.MEM_COMMIT:
            return False
        if mbi.Protect & cls.PAGE_GUARD or mbi.Protect & cls.PAGE_NOACCESS:
            return False
        return any(mbi.Protect & flag for flag in cls.READABLE_PAGE_FLAGS)

    @staticmethod
    def _read_process_memory(handle: wintypes.HANDLE, address: int, size: int) -> bytes:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        buffer = ctypes.create_string_buffer(size)
        read = ctypes.c_size_t(0)
        ok = kernel32.ReadProcessMemory(handle, ctypes.c_void_p(address), buffer, size, ctypes.byref(read))
        if not ok:
            return b""
        return buffer.raw[: read.value]

    @staticmethod
    def _write_process_memory(handle: wintypes.HANDLE, address: int, data: bytes) -> int:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        written = ctypes.c_size_t(0)
        buffer = ctypes.create_string_buffer(data)
        ok = kernel32.WriteProcessMemory(handle, ctypes.c_void_p(address), buffer, len(data), ctypes.byref(written))
        if not ok or written.value != len(data):
            DebugEngine._raise_last_error("WriteProcessMemory")
        return int(written.value)

    @staticmethod
    def _close_real_handle(handle: wintypes.HANDLE) -> None:
        if handle:
            ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(handle)

    @staticmethod
    def _ensure_windows() -> None:
        if platform.system() != "Windows":
            raise UnsupportedPlatformError("hex_scanner live memory APIs require Windows")

    @staticmethod
    def _raise_last_error(api_name: str) -> None:
        error_code = ctypes.get_last_error()
        raise MemoryAccessError(f"{api_name} failed with Windows error {error_code}")


MemoryAuditor = DebugEngine


def parse_signature(signature: bytes | str | Pattern) -> Pattern:
    """Parse bytes or strings like '48 8B ?? 00' into a Pattern."""
    if isinstance(signature, Pattern):
        return signature
    if isinstance(signature, bytes):
        if not signature:
            raise ValueError("signature must not be empty")
        return Pattern(signature, tuple(True for _ in signature))

    parts = signature.strip().split()
    if not parts:
        raise ValueError("signature must not be empty")

    values = bytearray()
    mask: list[bool] = []
    for part in parts:
        if part in {"?", "??"}:
            values.append(0)
            mask.append(False)
            continue
        if len(part) != 2:
            raise ValueError(f"invalid signature token: {part}")
        values.append(int(part, 16))
        mask.append(True)
    return Pattern(bytes(values), tuple(mask))


def find_pattern_offsets(buffer: bytes, pattern: Pattern) -> list[int]:
    """Return offsets where a parsed pattern appears in a buffer."""
    if pattern.length > len(buffer):
        return []
    if not pattern.has_wildcards:
        offsets: list[int] = []
        start = 0
        while True:
            index = buffer.find(pattern.values, start)
            if index == -1:
                return offsets
            offsets.append(index)
            start = index + 1

    matches: list[int] = []
    last_start = len(buffer) - pattern.length
    for offset in range(last_start + 1):
        candidate = zip(pattern.mask, pattern.values)
        if all(not required or buffer[offset + idx] == value for idx, (required, value) in enumerate(candidate)):
            matches.append(offset)
    return matches
