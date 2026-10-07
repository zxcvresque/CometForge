"""Windows desktop regression checks runnable without GUI automation."""
import ctypes
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import launcher
import server
import windows_app


class DesktopTests(unittest.TestCase):
    def test_windows_pdf_tools_never_request_a_console(self):
        startup = SimpleNamespace(dwFlags=0, wShowWindow=1)
        with patch.object(server.sys, "platform", "win32"), \
             patch.object(server.subprocess, "STARTUPINFO", return_value=startup, create=True), \
             patch.object(server.subprocess, "STARTF_USESHOWWINDOW", 1, create=True), \
             patch.object(server.subprocess, "SW_HIDE", 0, create=True), \
             patch.object(server.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True), \
             patch.object(server.subprocess, "run") as run:
            server._run_pdf_tool(["gswin64c.exe", "-q"], timeout=60)
        kwargs = run.call_args.kwargs
        self.assertEqual(kwargs["creationflags"], 0x08000000)
        self.assertEqual(kwargs["startupinfo"].wShowWindow, 0)
        self.assertTrue(kwargs["startupinfo"].dwFlags & 1)
        self.assertEqual(kwargs["timeout"], 60)
        self.assertTrue(kwargs["capture_output"])
        self.assertNotIn("shell", kwargs)

    def test_non_windows_subprocess_behavior_unchanged(self):
        with patch.object(server.sys, "platform", "darwin"), patch.object(server.subprocess, "run") as run:
            server._run_pdf_tool(["gs", "-q"])
        self.assertEqual(run.call_args.kwargs, {"capture_output": True, "text": True})

    def test_install_upgrade_keeps_user_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = root / "settings.json"
            settings.write_text(json.dumps({"port": 5191, "ghostscript": False, "custom": "keep"}))
            launcher.configure_install(root, True)
            self.assertEqual(json.loads(settings.read_text()), {"port": 5191, "ghostscript": True, "custom": "keep"})

    def test_windows_x64_com_abi_layout(self):
        self.assertEqual(ctypes.sizeof(windows_app.GUID), 16)
        self.assertEqual(ctypes.sizeof(windows_app.PROPERTYKEY), 20)
        self.assertEqual(ctypes.sizeof(windows_app.PROPVARIANT), 24)
        self.assertEqual(windows_app.PROPVARIANT.data.offset, 8)

    def test_property_strings_order_and_commit(self):
        received = []
        def setter(store, key_ptr, value_ptr):
            key = ctypes.cast(key_ptr, ctypes.POINTER(windows_app.PROPERTYKEY)).contents
            value = ctypes.cast(value_ptr, ctypes.POINTER(windows_app.PROPVARIANT)).contents
            self.assertEqual(value.vt, 31)
            fmtid = UUID(bytes_le=bytes(key.fmtid))
            self.assertEqual(str(fmtid), windows_app.PROPERTY_FORMAT)
            received.append((key.pid, ctypes.wstring_at(value.data.pointer)))
            return 0
        committed = []
        def method(store, index, *args):
            if index == 6:
                return setter
            self.assertEqual(index, 7)
            return lambda _store: committed.append(True) or 0
        with tempfile.TemporaryDirectory(prefix="Comet Forge Unicode-") as directory:
            root = Path(directory)
            (root / "CometForge.exe").touch()
            values = windows_app.window_properties(root)
            self.assertEqual([key for key, _ in values], [2, 3, 4, 5])
            self.assertIn("CometForge.exe", values[0][1])
            self.assertNotIn("pythonw", values[0][1])
            self.assertEqual(values[-1], (5, windows_app.APP_ID))
            self.assertTrue(values[1][1].endswith("CometForge.exe,-1"))
            self.assertTrue(values[2][1].endswith("CometForge.exe,-101"))
            with patch.object(windows_app, "_method", side_effect=method):
                windows_app._set_properties(123, values, commit=True)
            self.assertEqual(received, values)
            self.assertEqual(committed, [True])

    def test_both_pdf_subprocess_routes_use_silent_helper(self):
        text = (Path(server.__file__)).read_text()
        self.assertEqual(text.count("subprocess.run("), 1)
        self.assertIn("_run_pdf_tool(command, timeout=60)", text)
        self.assertIn("_run_pdf_tool(cmd)", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
