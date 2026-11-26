"""Windows desktop regression checks runnable without GUI automation."""
import ctypes
import json
import importlib.util
from pathlib import Path
import sys
import tempfile
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import launcher
import server
import windows_app
import desktop_smoke


class DesktopTests(unittest.TestCase):
    def test_setup_smoke_clicks_real_button_once_and_survives_navigation(self):
        window = MagicMock()
        window.evaluate_js.side_effect = [
            {'ready': True, 'setup': True, 'bridge': True}, None,
            RuntimeError('document navigation'),
            {'ready': True, 'app': True, 'layout': True, 'paper': 16},
        ]
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'report.json'
            with patch.object(desktop_smoke, 'exercise_pdf_engine', return_value={'export_success': True}), \
                 patch.object(desktop_smoke.time, 'sleep'):
                desktop_smoke.run(window, 'http://127.0.0.1:5000/', report, True)
            result = json.loads(report.read_text())
        self.assertTrue(result['success'])
        self.assertTrue(result['setup_success'])
        clicks = [call for call in window.evaluate_js.call_args_list if "querySelector('button').click()" in call.args[0]]
        self.assertEqual(len(clicks), 1)
        window.destroy.assert_called_once()

    def test_desktop_smoke_records_engine_failure_and_still_closes(self):
        window = MagicMock()
        window.evaluate_js.return_value = {'ready': True, 'app': True, 'layout': True, 'paper': 16}
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'report.json'
            with patch.object(desktop_smoke, 'exercise_pdf_engine', side_effect=RuntimeError('render failed')):
                desktop_smoke.run(window, 'http://127.0.0.1:5000/', report, True)
            result = json.loads(report.read_text())
        self.assertFalse(result['success'])
        self.assertEqual(result['error'], 'render failed')
        window.destroy.assert_called_once()

    def test_source_launch_defaults_to_desktop_and_remembers_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "settings.json").write_text(json.dumps({"port": 5191, "ghostscript": False}))
            webview = MagicMock(settings={})
            uvicorn = MagicMock()
            with patch.object(sys, "argv", ["launcher.py"]), \
                 patch.dict(sys.modules, {"webview": webview, "uvicorn": uvicorn}), \
                 patch.object(launcher, "support_dir", return_value=root), \
                 patch.object(launcher, "configure_dependencies") as dependencies, \
                 patch.object(launcher, "free_port", return_value=5191) as port, \
                 patch.object(launcher, "wait_for_server"), \
                 patch.object(launcher.threading, "Thread") as thread, \
                 patch.object(launcher.webbrowser, "open") as browser:
                self.assertEqual(launcher.main(), 0)
            port.assert_called_once_with(5191)
            dependencies.assert_called_once_with(root, False)
            browser.assert_not_called()
            webview.create_window.assert_called_once()
            self.assertEqual(webview.create_window.call_args.args[1], "http://127.0.0.1:5191/")
            self.assertIsNone(webview.create_window.call_args.kwargs["html"])
            self.assertTrue(webview.settings["ALLOW_DOWNLOADS"])
            webview.start.assert_called_once()
            self.assertTrue(uvicorn.Server.return_value.should_exit)
            thread.return_value.join.assert_called_once_with(timeout=10)

    def test_launch_modes_cannot_conflict(self):
        with patch.object(sys, "argv", ["launcher.py", "--desktop", "--browser"]), \
             patch.object(sys, "stderr"):
            with self.assertRaises(SystemExit) as result:
                launcher.main()
        self.assertEqual(result.exception.code, 2)

    def test_browser_remains_an_explicit_option(self):
        uvicorn = MagicMock()
        thread = MagicMock()
        thread.is_alive.return_value = False
        with patch.object(sys, "argv", ["launcher.py", "--browser"]), \
             patch.dict(sys.modules, {"webview": None, "uvicorn": uvicorn}), \
             patch.object(launcher, "configure_dependencies"), \
             patch.object(launcher, "free_port", return_value=5192), \
             patch.object(launcher, "wait_for_server"), \
             patch.object(launcher.threading, "Thread", return_value=thread), \
             patch.object(launcher.webbrowser, "open") as browser, \
             patch("builtins.print"):
            self.assertEqual(launcher.main(), 0)
        browser.assert_called_once_with("http://127.0.0.1:5192/")

    def test_headless_mode_does_not_need_a_desktop_runtime(self):
        uvicorn = MagicMock()
        with patch.object(sys, "argv", ["launcher.py", "--no-browser"]), \
             patch.dict(sys.modules, {"webview": None, "uvicorn": uvicorn}), \
             patch.object(launcher, "configure_dependencies"), \
             patch.object(launcher, "free_port", return_value=5193), \
             patch.object(launcher.threading, "Thread") as thread, \
             patch.object(launcher.webbrowser, "open") as browser:
            self.assertEqual(launcher.main(), 0)
        uvicorn.Server.return_value.run.assert_called_once()
        browser.assert_not_called()
        thread.assert_not_called()

    def test_missing_desktop_runtime_fails_before_server_start(self):
        with tempfile.TemporaryDirectory() as directory:
            uvicorn = MagicMock()
            with patch.object(sys, "argv", ["launcher.py"]), \
                 patch.dict(sys.modules, {"webview": None, "uvicorn": uvicorn}), \
                 patch.object(launcher, "support_dir", return_value=Path(directory)), \
                 patch.object(launcher, "configure_dependencies"), \
                 patch.object(launcher.webbrowser, "open") as browser:
                with self.assertRaisesRegex(RuntimeError, "desktop runtime is missing"):
                    launcher.main()
            uvicorn.Server.assert_not_called()
            browser.assert_not_called()

    def test_console_launcher_cannot_be_packaged(self):
        source = Path(__file__).resolve().parents[1] / "packaging" / "build_windows.py"
        spec = importlib.util.spec_from_file_location("cometforge_windows_build", source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        payload = bytearray(256)
        payload[:2] = b"MZ"
        struct.pack_into("<I", payload, 60, 128)
        payload[128:132] = b"PE\0\0"
        struct.pack_into("<H", payload, 132, 0x8664)
        struct.pack_into("<H", payload, 152, 0x20B)
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "CometForge.exe"
            # IMAGE_SUBSYSTEM_WINDOWS_CUI would flash a command window.
            struct.pack_into("<H", payload, 220, 3)
            executable.write_bytes(payload)
            with self.assertRaisesRegex(RuntimeError, "never a console"):
                module.verify_gui_launcher(executable)
            struct.pack_into("<H", payload, 220, 2)
            executable.write_bytes(payload)
            module.verify_gui_launcher(executable)
            executable.write_bytes(b"not an executable")
            with self.assertRaisesRegex(RuntimeError, "not a Windows"):
                module.verify_gui_launcher(executable)

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

    def test_source_taskbar_relaunch_prefers_windowed_python(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "python.exe").touch()
            (root / "pythonw.exe").touch()
            with patch.object(sys, 'executable', str(root / 'python.exe')):
                values = windows_app.window_properties(root)
        self.assertIn('pythonw.exe', values[0][1])
        self.assertIn('--desktop', values[0][1])

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
