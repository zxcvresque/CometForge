"""Windows shell identity for the native CometForge launcher and app window.

No third-party COM package is needed. The property-store strings are borrowed
only during SetValue; IPropertyStore copies them into its own storage.
"""
from __future__ import annotations

import ctypes
from contextlib import contextmanager
from pathlib import Path
import subprocess
from uuid import UUID

APP_ID = "com.cometforge.desktop"
PROPERTY_FORMAT = "9f4c2855-9f79-4b39-a8d0-e1d42de1d5f3"
PROPERTY_STORE_IID = "886d8eeb-8cf2-4446-8d02-cdba1dbdcf99"


class GUID(ctypes.Structure):
    _fields_ = [("data1", ctypes.c_uint32), ("data2", ctypes.c_uint16),
                ("data3", ctypes.c_uint16), ("data4", ctypes.c_ubyte * 8)]

    @classmethod
    def parse(cls, value: str):
        return cls.from_buffer_copy(UUID(value).bytes_le)


class PROPERTYKEY(ctypes.Structure):
    _fields_ = [("fmtid", GUID), ("pid", ctypes.c_uint32)]


class VARIANT_DATA(ctypes.Union):
    _fields_ = [("pointer", ctypes.c_void_p), ("alignment", ctypes.c_uint64),
                ("storage", ctypes.c_ubyte * 16)]


class PROPVARIANT(ctypes.Structure):
    _fields_ = [("vt", ctypes.c_uint16), ("reserved1", ctypes.c_uint16),
                ("reserved2", ctypes.c_uint16), ("reserved3", ctypes.c_uint16),
                ("data", VARIANT_DATA)]


def _check(result: int, operation: str) -> None:
    if result < 0:
        raise OSError(f"{operation} failed (HRESULT 0x{result & 0xffffffff:08x})")


def _method(store, index, return_type, *arguments):
    table = ctypes.cast(store, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(return_type, ctypes.c_void_p, *arguments)(table[index])


def _set_properties(store, values, commit=False) -> None:
    setter = _method(store, 6, ctypes.c_int32,
                     ctypes.POINTER(PROPERTYKEY), ctypes.POINTER(PROPVARIANT))
    for pid, text in values:
        key = PROPERTYKEY(GUID.parse(PROPERTY_FORMAT), pid)
        buffer = ctypes.create_unicode_buffer(text)
        value = PROPVARIANT()
        value.vt = 31  # VT_LPWSTR; the buffer remains live until SetValue returns.
        value.data.pointer = ctypes.cast(buffer, ctypes.c_void_p).value
        _check(setter(store, ctypes.byref(key), ctypes.byref(value)), "Set shell property")
    if commit:
        _check(_method(store, 7, ctypes.c_int32)(store), "Save shortcut properties")


@contextmanager
def _property_store(*, hwnd=None, shortcut=None):
    ole = ctypes.WinDLL("ole32")
    shell = ctypes.WinDLL("shell32")
    ole.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    ole.CoInitializeEx.restype = ctypes.c_int32
    initialized = ole.CoInitializeEx(None, 2)
    # A .NET UI thread can already be in another COM apartment.
    if initialized not in (0, 1, -2147417850):
        _check(initialized, "Initialize shell COM")
    store = ctypes.c_void_p()
    iid = GUID.parse(PROPERTY_STORE_IID)
    try:
        if hwnd is not None:
            getter = shell.SHGetPropertyStoreForWindow
            getter.argtypes = [ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
            getter.restype = ctypes.c_int32
            _check(getter(hwnd, ctypes.byref(iid), ctypes.byref(store)), "Get window properties")
        else:
            getter = shell.SHGetPropertyStoreFromParsingName
            getter.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_uint32,
                              ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
            getter.restype = ctypes.c_int32
            _check(getter(str(shortcut), None, 2, ctypes.byref(iid), ctypes.byref(store)), "Get shortcut properties")
        yield store
    finally:
        if store.value:
            _method(store, 2, ctypes.c_uint32)(store)
        if initialized in (0, 1):
            ole.CoUninitialize()


def set_process_identity() -> None:
    function = ctypes.WinDLL("shell32").SetCurrentProcessExplicitAppUserModelID
    function.argtypes = [ctypes.c_wchar_p]
    function.restype = ctypes.c_int32
    _check(function(APP_ID), "Set application identity")


def window_properties(root: Path):
    executable = root / "CometForge.exe"
    if executable.is_file():
        command = subprocess.list2cmdline([str(executable)])
        icon = f"{executable},-1"
        name = f"@{executable},-101"
    else:
        # Also support a Windows source checkout launched in desktop mode.
        import sys
        command = subprocess.list2cmdline([sys.executable, str(root / "launcher.py"), "--desktop"])
        icon = f"{root / 'CometForge.ico'},0"
        name = "CometForge"
    # Relaunch properties must precede the explicit window AppUserModelID.
    return [(2, command), (3, icon), (4, name), (5, APP_ID)]


def set_window_identity(hwnd: int, root: Path) -> None:
    with _property_store(hwnd=hwnd) as store:
        _set_properties(store, window_properties(root))


def register_shortcuts(paths) -> None:
    shell = ctypes.WinDLL("shell32")
    notify = shell.SHChangeNotify
    notify.argtypes = [ctypes.c_int32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p]
    notify.restype = None
    for value in paths:
        shortcut = Path(value).resolve(strict=True)
        if shortcut.suffix.lower() != ".lnk":
            raise ValueError("Only CometForge shortcut files can be registered")
        with _property_store(shortcut=shortcut) as store:
            _set_properties(store, [(5, APP_ID)], commit=True)
        # Tell Explorer that the installed shortcut metadata changed.
        buffer = ctypes.create_unicode_buffer(str(shortcut))
        notify(0x2000, 5, ctypes.cast(buffer, ctypes.c_void_p), None)
