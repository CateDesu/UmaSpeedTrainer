#!/usr/bin/env python3
"""
inject.py

Minimal DLL injector. Run from real Windows, not from WSL or Linux.

Usage:
    python inject.py UmamusumePrettyDerby.exe C:\\path\\to\\uma_hook.dll

Finds the named process, opens it, allocates memory for the DLL path,
writes the path, then calls kernel32.LoadLibraryA via CreateRemoteThread.
Standard technique, has no anti detection.
"""

import ctypes
import ctypes.wintypes as wt
import os
import sys

if sys.platform != "win32":
    sys.exit("This script must be run from Windows.")

# Windows API setup
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)

PROCESS_ALL_ACCESS = 0x1F0FFF
MEM_COMMIT         = 0x1000
MEM_RESERVE        = 0x2000
PAGE_READWRITE     = 0x04

k32.OpenProcess.restype           = wt.HANDLE
k32.OpenProcess.argtypes          = [wt.DWORD, wt.BOOL, wt.DWORD]
k32.VirtualAllocEx.restype        = ctypes.c_void_p
k32.VirtualAllocEx.argtypes       = [wt.HANDLE, ctypes.c_void_p,
                                     ctypes.c_size_t, wt.DWORD, wt.DWORD]
k32.WriteProcessMemory.restype    = wt.BOOL
k32.WriteProcessMemory.argtypes   = [wt.HANDLE, ctypes.c_void_p,
                                     ctypes.c_void_p, ctypes.c_size_t,
                                     ctypes.POINTER(ctypes.c_size_t)]
k32.CreateRemoteThread.restype    = wt.HANDLE
k32.CreateRemoteThread.argtypes   = [wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t,
                                     ctypes.c_void_p, ctypes.c_void_p,
                                     wt.DWORD, ctypes.c_void_p]
k32.GetProcAddress.restype        = ctypes.c_void_p
k32.GetProcAddress.argtypes       = [wt.HMODULE, ctypes.c_char_p]
k32.GetModuleHandleA.restype      = wt.HMODULE
k32.GetModuleHandleA.argtypes     = [ctypes.c_char_p]
k32.WaitForSingleObject.restype   = wt.DWORD
k32.WaitForSingleObject.argtypes  = [wt.HANDLE, wt.DWORD]
k32.CloseHandle.restype           = wt.BOOL
k32.CloseHandle.argtypes          = [wt.HANDLE]

psapi.EnumProcesses.restype       = wt.BOOL
psapi.EnumProcesses.argtypes      = [ctypes.POINTER(wt.DWORD),
                                     wt.DWORD, ctypes.POINTER(wt.DWORD)]
psapi.GetModuleBaseNameA.restype  = wt.DWORD
psapi.GetModuleBaseNameA.argtypes = [wt.HANDLE, wt.HMODULE,
                                     ctypes.c_char_p, wt.DWORD]


def find_pid(name: str) -> int:
    pids = (wt.DWORD * 4096)()
    needed = wt.DWORD()
    psapi.EnumProcesses(pids, ctypes.sizeof(pids), ctypes.byref(needed))
    count = needed.value // ctypes.sizeof(wt.DWORD)
    target = name.lower().encode()
    for i in range(count):
        pid = pids[i]
        if pid == 0:
            continue
        h = k32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
        if not h:
            continue
        try:
            buf = ctypes.create_string_buffer(260)
            psapi.GetModuleBaseNameA(h, None, buf, 260)
            if buf.value.lower() == target:
                return pid
        finally:
            k32.CloseHandle(h)
    raise SystemExit(f"Process not found: {name}")


def inject(pid: int, dll_path: str) -> None:
    dll_path_b = (dll_path + "\x00").encode()
    h = k32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
    if not h:
        raise SystemExit(f"OpenProcess failed: {ctypes.get_last_error()}")

    addr = k32.VirtualAllocEx(h, None, len(dll_path_b),
                              MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE)
    if not addr:
        raise SystemExit(f"VirtualAllocEx failed: {ctypes.get_last_error()}")

    written = ctypes.c_size_t(0)
    if not k32.WriteProcessMemory(h, addr, dll_path_b,
                                  len(dll_path_b), ctypes.byref(written)):
        raise SystemExit(f"WriteProcessMemory failed: {ctypes.get_last_error()}")

    load_lib = k32.GetProcAddress(k32.GetModuleHandleA(b"kernel32.dll"),
                                  b"LoadLibraryA")
    if not load_lib:
        raise SystemExit("Could not resolve LoadLibraryA")

    thread = k32.CreateRemoteThread(h, None, 0, load_lib, addr, 0, None)
    if not thread:
        raise SystemExit(f"CreateRemoteThread failed: {ctypes.get_last_error()}")

    k32.WaitForSingleObject(thread, 5000)
    k32.CloseHandle(thread)
    k32.CloseHandle(h)
    print(f"Injected {dll_path} into pid {pid}")


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__.strip())
    proc_name = sys.argv[1]
    dll_path  = os.path.abspath(sys.argv[2])
    if not os.path.exists(dll_path):
        sys.exit(f"DLL not found: {dll_path}")
    pid = find_pid(proc_name)
    inject(pid, dll_path)


if __name__ == "__main__":
    main()
