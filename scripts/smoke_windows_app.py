"""Exercise an installed Windows app window without requiring a browser driver.

Run on Windows: python scripts/smoke_windows_app.py --version 1.2.0
The app is started through its installed GUI executable, not Python.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time



def main():
    if sys.platform != "win32":
        raise SystemExit("The installed-app smoke test requires a Windows desktop session.")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--executable", type=Path,
                        default=Path(os.environ["LOCALAPPDATA"]) / "Programs" / "CometForge" / "CometForge.exe")
    args = parser.parse_args()
    assert args.executable.is_file(), f"Installed executable missing: {args.executable}"

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]

    class ProcessEntry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]

    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    def visible_windows():
        result = []

        @callback_type
        def collect(hwnd, _):
            if user32.IsWindowVisible(hwnd):
                pid = wintypes.DWORD()
                title, kind = ctypes.create_unicode_buffer(2048), ctypes.create_unicode_buffer(256)
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                user32.GetWindowTextW(hwnd, title, len(title))
                user32.GetClassNameW(hwnd, kind, len(kind))
                result.append({"hwnd": hwnd, "pid": pid.value, "title": title.value, "class": kind.value})
            return True

        if not user32.EnumWindows(collect, 0):
            raise ctypes.WinError(ctypes.get_last_error())
        return result

    def descendants(known):
        snapshot = kernel32.CreateToolhelp32Snapshot(2, 0)  # TH32CS_SNAPPROCESS
        if snapshot == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        parents = {}
        try:
            entry = ProcessEntry()
            entry.dwSize = ctypes.sizeof(entry)
            more = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
            while more:
                parents[entry.th32ProcessID] = entry.th32ParentProcessID
                more = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
        finally:
            kernel32.CloseHandle(snapshot)
        while True:
            added = {pid for pid, parent in parents.items() if parent in known} - known
            if not added:
                return known
            known.update(added)

    baseline = {window["hwnd"] for window in visible_windows()}
    data = Path(os.environ["LOCALAPPDATA"]) / "CometForge" / "data"
    data.mkdir(parents=True, exist_ok=True)
    result_path = data / "desktop-smoke-result.json"
    result_path.unlink(missing_ok=True)
    process = subprocess.Popen([str(args.executable), "--skip-setup", "--smoke-test", str(result_path)], cwd=args.executable.parent)
    known_pids = {process.pid}
    native = None
    ready = False
    ready_since = None
    try:
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            assert process.poll() is None, f"App exited during startup with {process.returncode}"
            descendants(known_pids)
            windows = visible_windows()
            consoles = [w for w in windows if w["class"] == "ConsoleWindowClass" and
                        (w["hwnd"] not in baseline or w["pid"] in known_pids)]
            assert not consoles, f"A command window appeared: {consoles}"
            matches = [w for w in windows if w["pid"] in known_pids and
                       w["title"] == f"CometForge {args.version}"]
            if matches:
                native = matches[0]
            try:
                result = json.loads(result_path.read_text(encoding="utf-8"))
                assert result.get("version") == args.version, result
                for requirement in ("success", "desktop_window", "export_success", "preview_success", "live_preview_success", "white_margins"):
                    assert result.get(requirement) is True, f"Native smoke failed {requirement}: {result}"
                ready = True
            except (OSError, ValueError, KeyError):
                ready = False
            if native and ready:
                ready_since = ready_since or time.monotonic()
                if time.monotonic() - ready_since >= 5:
                    break
            else:
                ready_since = None
            time.sleep(0.05)
        assert native and ready and ready_since, f"Native window/export did not become ready; windows={visible_windows()}"
        assert time.monotonic() - ready_since >= 5, "App did not remain ready for five seconds"
        print(f"PASS: dedicated app window {native['class']}, version {args.version}; no visible console")
        print("PASS: bundled PDF engine rotated, fitted, compressed and rendered A4 with white margins; no visible console")
        assert user32.PostMessageW(native["hwnd"], 0x0010, 0, 0), "Could not close the native window"  # WM_CLOSE
        assert process.wait(timeout=25) == 0, "Native launcher did not exit cleanly"
        port = json.loads((data / 'settings.json').read_text())['port']
        import urllib.request
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{port}/api/capabilities', timeout=1).close()
        except OSError:
            pass
        else:
            raise AssertionError('Local service remained running after closing the app')
        print("PASS: closing the window stopped the installed application cleanly")
    finally:
        if process.poll() is None:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        log = data / "launcher.log"
        if log.is_file():
            print("Launcher log:\n" + log.read_text(encoding="utf-8", errors="replace")[-12000:])


if __name__ == "__main__":
    main()
