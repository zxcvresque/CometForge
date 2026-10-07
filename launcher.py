"""CometForge: browser by default for source, native window for installers."""
from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import socket
import sys
import threading
import time
import urllib.request
import webbrowser

from version import __version__


def support_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "CometForge"
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "CometForge" / "data"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "CometForge"


def resource_dir() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def configure_dependencies(data: Path, install_gs: bool = True) -> None:
    os.environ.setdefault("COMETFORGE_DATA_DIR", str(data / "work"))
    bundled = resource_dir() / "ghostscript"
    candidates = [bundled / "bin" / "gs", bundled / "bin" / "gswin64c.exe"]
    if not getattr(sys, "frozen", False):
        candidates.append(Path(__file__).resolve().parent / "ghostscript" / "bin" / "gswin64c.exe")
    if install_gs:
        os.environ.pop("COMETFORGE_DISABLE_GHOSTSCRIPT", None)
        for candidate in candidates:
            if candidate.is_file():
                os.environ["COMETFORGE_GHOSTSCRIPT"] = str(candidate)
                if candidate.name == "gs":
                    os.environ["GS_LIB"] = os.pathsep.join(str(bundled / p) for p in (
                        "share/ghostscript/Resource/Init", "share/ghostscript/Resource/Font",
                        "share/ghostscript/lib", "share/ghostscript/fonts"))
                break
    else:
        os.environ["COMETFORGE_DISABLE_GHOSTSCRIPT"] = "1"


def free_port(preferred: int) -> int:
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", preferred))
        except OSError:
            sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_server(server, url: str) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if server.started:
            return
        try:
            with urllib.request.urlopen(url, timeout=0.5) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(0.1)
    raise RuntimeError("CometForge could not start. See the launcher log in the application data folder.")


SETUP_HTML = """<!doctype html><html><meta charset="utf-8"><style>
body{font:16px -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#151515;color:#eee;padding:32px;line-height:1.5}
h1{font-size:25px}label{display:block;margin:22px 0}input{accent-color:#65d9b4;width:18px;height:18px;vertical-align:middle}
button{background:#65d9b4;color:#101010;border:0;border-radius:10px;padding:12px 24px;font-weight:650;font-size:16px;cursor:pointer}
a{color:#65d9b4}.muted{color:#aaa;font-size:13px}</style>
<h1>Set up CometForge</h1><p>The PDF engine and required dependencies are included.</p>
<label><input type="checkbox" id="gs" checked> Enable bundled Ghostscript for target-fit compression</label>
<p class="muted">Ghostscript is optional and distributed under the GNU AGPL v3. See the included third-party notices and source references.</p>
<button onclick="pywebview.api.finish(document.getElementById('gs').checked).then(url => { window.location.href = url; })">Open CometForge</button>
</html>"""


def configure_install(data: Path, ghostscript: bool) -> None:
    """Upgrade dependency selection without losing the user's port/preferences."""
    data.mkdir(parents=True, exist_ok=True)
    settings_path = data / "settings.json"
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        if not isinstance(settings, dict):
            settings = {}
    except (OSError, ValueError):
        settings = {}
    settings["ghostscript"] = ghostscript
    settings_path.write_text(json.dumps(settings), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", action="store_true", help="Open in the default browser")
    parser.add_argument("--desktop", action="store_true", help="Open in a native app window")
    parser.add_argument("--no-browser", action="store_true", help="Run the server without opening a window")
    parser.add_argument("--skip-setup", action="store_true", help="Use bundled Ghostscript without the first-run screen")
    parser.add_argument("--setup", action="store_true", help="Show dependency preferences again")
    parser.add_argument("--port", type=int, default=None,
                        help="Listen port (default: 5173, or the remembered desktop port)")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--register-shortcuts", nargs="+", metavar="LINK", help=argparse.SUPPRESS)
    parser.add_argument("--configure-install", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--ghostscript", choices=("enabled", "disabled"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.register_shortcuts:
        from windows_app import register_shortcuts
        register_shortcuts(args.register_shortcuts)
        return 0
    if args.configure_install:
        if args.ghostscript is None:
            parser.error("--configure-install requires --ghostscript enabled or disabled")
        configure_install(support_dir(), args.ghostscript == "enabled")
        return 0
    installed = bool(getattr(sys, "frozen", False) or (Path(__file__).parent / "installed.json").is_file())
    desktop = (installed or args.desktop) and not args.browser and not args.no_browser
    data = support_dir() if installed else Path(__file__).resolve().parent
    data.mkdir(parents=True, exist_ok=True)
    settings_path = data / "settings.json"
    settings = {}
    if installed and settings_path.is_file():
        try:
            loaded = json.loads(settings_path.read_text(encoding="utf-8"))
            settings = loaded if isinstance(loaded, dict) else {}
        except (OSError, ValueError):
            pass
    configure_dependencies(data, settings.get("ghostscript", True))
    # Windowed executables have no stdout/stderr; keep useful diagnostics on disk.
    if installed:
        log = open(data / "launcher.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = log
        sys.stderr = log
    import uvicorn
    from server import app
    remembered_port = settings.get("port", 5173) if installed and desktop else 5173
    if not isinstance(remembered_port, int) or not 1 <= remembered_port <= 65535:
        remembered_port = 5173
    preferred_port = args.port if args.port is not None else remembered_port
    if not 0 <= preferred_port <= 65535:
        parser.error("--port must be between 0 and 65535")
    port = free_port(preferred_port)
    if installed and desktop:
        settings["port"] = port
        settings_path.write_text(json.dumps(settings), encoding="utf-8")
    url = f"http://127.0.0.1:{port}/"
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="info", loop="asyncio", http="h11")
    server = uvicorn.Server(config)
    if args.no_browser:
        server.run()
        return 0
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    wait_for_server(server, url)
    if desktop:
        if os.name == "nt":
            from windows_app import set_process_identity
            set_process_identity()
        import webview
        webview.settings["ALLOW_DOWNLOADS"] = True
        needs_setup = ("ghostscript" not in settings or args.setup) and not args.skip_setup
        class SetupAPI:
            def finish(self, ghostscript: bool) -> str:
                settings["ghostscript"] = bool(ghostscript)
                settings_path.write_text(json.dumps(settings), encoding="utf-8")
                configure_dependencies(data, bool(ghostscript))
                window.set_title(f"CometForge {__version__}")
                window.resize(1380, 900)
                # Navigate in JavaScript only after the bridge has returned.
                # Loading a new document here destroys its pending callback.
                return url
        window = webview.create_window(
            "CometForge Setup" if needs_setup else f"CometForge {__version__}",
            None if needs_setup else url, html=SETUP_HTML if needs_setup else None,
            js_api=SetupAPI() if needs_setup else None,
            width=560 if needs_setup else 1380, height=410 if needs_setup else 900,
            min_size=(500, 350) if needs_setup else (800, 600))
        if os.name == "nt":
            def set_native_identity():
                from windows_app import set_window_identity
                from System.Drawing import Icon
                icon_file = resource_dir() / "CometForge.ico"
                if icon_file.is_file():
                    window._cometforge_icon = Icon(str(icon_file))
                    window.native.Icon = window._cometforge_icon
                set_window_identity(window.native.Handle.ToInt64(), resource_dir())
            # WinForms fires this synchronously on the UI thread before Show().
            # Both the live icon and pin/relaunch identity are ready immediately.
            window.events.before_show += set_native_identity
        try:
            webview_data = data / "webview"
            webview_data.mkdir(parents=True, exist_ok=True)
            webview.start(gui="cocoa" if sys.platform == "darwin" else "edgechromium",
                          private_mode=False, storage_path=str(webview_data))
        finally:
            server.should_exit = True
            thread.join(timeout=10)
    else:
        webbrowser.open(url)
        print(f"CometForge {__version__}: {url} — press Ctrl+C to stop.")
        try:
            while thread.is_alive():
                thread.join(timeout=0.5)
        except KeyboardInterrupt:
            server.should_exit = True
            thread.join(timeout=10)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
