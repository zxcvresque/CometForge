"""Cross-build a genuine offline Windows x64 NSIS installer on macOS/Linux.

Downloads are explicit build-time dependencies, never startup update checks.
Python/PDF/Ghostscript runtimes are bundled. WebView2's official bootstrapper
can need Internet only when that system runtime is absent on the target PC.
"""
from __future__ import annotations

import email
import hashlib
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name, parse_wheel_filename

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from version import __version__

DOWNLOADS = ROOT / "packaging" / "downloads"
WHEELS = DOWNLOADS / "windows-wheels"
BUILD = ROOT / "packaging" / "build" / "windows"
PYTHON_VERSION = "3.13.16"
PYTHON_SHA256 = "97dae5274cc54867065e8d5a3226e48c35017ed332a0fdb0e27d5b5821961297"


def download(url: str, target: Path, sha256: str | None = None):
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        print(f"Download {url}", flush=True)
        urllib.request.urlretrieve(url, target)
    if sha256 and hashlib.sha256(target.read_bytes()).hexdigest() != sha256:
        raise RuntimeError(f"Checksum mismatch: {target}")


def target_wheels():
    WHEELS.mkdir(parents=True, exist_ok=True)
    environment = default_environment()
    environment.update(sys_platform="win32", platform_system="Windows", os_name="nt",
                       platform_machine="AMD64", python_version="3.13", python_full_version=PYTHON_VERSION)
    pending = [Requirement(line.strip().replace("uvicorn[standard]", "uvicorn"))
               for line in (ROOT / "requirements.txt").read_text().splitlines()
               if line.strip() and not line.startswith("#")]
    pending.append(Requirement("pywebview==6.1"))
    resolved = {}
    while pending:
        requirement = pending.pop(0)
        if requirement.marker and not requirement.marker.evaluate(environment):
            continue
        name = canonicalize_name(requirement.name)
        if name in resolved:
            if resolved[name][0] not in requirement.specifier:
                raise RuntimeError(f"Incompatible wheel constraints: {requirement}")
            continue
        # Evaluate markers against the target above; pip itself runs on the
        # build host and would incorrectly skip Windows-only dependencies.
        requirement.marker = None
        subprocess.run([sys.executable, "-m", "pip", "download", "--no-deps", "--only-binary=:all:",
                        "--platform", "win_amd64", "--python-version", "313", "--implementation", "cp",
                        "--abi", "cp313", "--find-links", str(WHEELS), "--dest", str(WHEELS),
                        "--disable-pip-version-check", str(requirement)], check=True)
        matches = []
        for wheel in WHEELS.glob("*.whl"):
            wheel_name, version, _, tags = parse_wheel_filename(wheel.name)
            if wheel_name == name and version in requirement.specifier and any(
                    t.platform in ("win_amd64", "any") for t in tags):
                matches.append((version, wheel))
        if not matches:
            raise RuntimeError(f"No compatible wheel for {requirement}")
        version, wheel = sorted(matches)[-1]
        resolved[name] = (version, wheel)
        with zipfile.ZipFile(wheel) as archive:
            metadata_file = next(x for x in archive.namelist() if x.endswith(".dist-info/METADATA"))
            metadata = email.message_from_bytes(archive.read(metadata_file))
        for dependency in metadata.get_all("Requires-Dist", []):
            parsed = Requirement(dependency)
            if not parsed.marker or parsed.marker.evaluate(dict(environment, extra="")):
                pending.append(parsed)
    return [item[1] for item in resolved.values()]


def build_native_launcher(destination: Path):
    try:
        import ziglang
    except ImportError:
        raise SystemExit("Install the Windows build compiler in your venv: pip install ziglang==0.15.1")
    compiler = Path(ziglang.__file__).parent / ("zig.exe" if sys.platform == "win32" else "zig")
    version_parts = [int(part) for part in __version__.split(".")]
    file_version = ",".join(str(part) for part in (version_parts + [0])[:4])
    environment = dict(os.environ, ZIG_GLOBAL_CACHE_DIR=str(BUILD / "zig-cache"),
                       ZIG_LOCAL_CACHE_DIR=str(BUILD / "zig-local-cache"))
    resource = "windows_launcher.rc"
    if sys.platform == "darwin":
        # Zig 0.15's automatic RC-tool bootstrap uses the host OS version.
        # Building its official resource compiler for macOS 14 avoids newer
        # macOS SDK linker incompatibilities; the emitted resource is Windows
        # x64 COFF, compiled from the same .rc as on Windows/Linux.
        zig_lib = compiler.parent / "lib"
        resource_compiler = BUILD / "cometforge-resinator"
        if not resource_compiler.is_file():
            architecture = "aarch64" if platform.machine() == "arm64" else "x86_64"
            subprocess.run([str(compiler), "build-exe", "-target", f"{architecture}-macos.14.0.0",
                            "-O", "ReleaseFast", "-lc", "--dep", "aro",
                            f"-Mroot={zig_lib / 'compiler' / 'resinator' / 'main.zig'}",
                            f"-Maro={zig_lib / 'compiler' / 'aro' / 'aro.zig'}",
                            f"-femit-bin={resource_compiler}"], cwd=ROOT, env=environment, check=True)
        resource = str(BUILD / "native-launcher-resources.obj")
        subprocess.run([str(resource_compiler), str(zig_lib), "/:auto-includes", "none",
                        "/i", str(zig_lib / "libc" / "include" / "any-windows-any"),
                        "/i", str(zig_lib / "libc" / "include" / "generic-mingw"),
                        "/:target", "X64", "/:output-format", "coff",
                        "/d", f'COMETFORGE_VERSION="{__version__}"',
                        "/d", f"COMETFORGE_FILE_VERSION={file_version}",
                        "/fo", resource, "windows_launcher.rc"],
                       cwd=ROOT / "packaging", env=environment, check=True)
    subprocess.run([str(compiler), "cc", "-target", "x86_64-windows-gnu", "-Os", "-s",
                    "-municode", "-Wl,--subsystem,windows", "-Wall", "-Wextra", "-Werror",
                    f'-DCOMETFORGE_VERSION="{__version__}"',
                    f"-DCOMETFORGE_FILE_VERSION={file_version}",
                    "windows_launcher.c", resource, "-lshell32", "-luser32",
                    "-o", str(destination)], cwd=ROOT / "packaging", env=environment, check=True)


def main():
    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    (ROOT / "packaging" / "dist").mkdir(exist_ok=True)
    subprocess.run([sys.executable, str(ROOT / "packaging" / "generate_icons.py")], check=True)
    embedded = DOWNLOADS / f"python-{PYTHON_VERSION}-embed-amd64.zip"
    download(f"https://www.python.org/ftp/python/{PYTHON_VERSION}/{embedded.name}", embedded, PYTHON_SHA256)
    # img2pdf's pinned release is pure Python but not advertised as a binary
    # wheel on every package index; build its universal wheel once on the host.
    subprocess.run([sys.executable, "-m", "pip", "wheel", "img2pdf==0.5.1", "proxy_tools==0.1.0", "--no-deps",
                    "--wheel-dir", str(WHEELS), "--disable-pip-version-check"], check=True)
    wheels = target_wheels()
    runtime = BUILD / "runtime"
    runtime.mkdir(exist_ok=True)
    with zipfile.ZipFile(embedded) as archive:
        archive.extractall(runtime)
    site = runtime / "Lib" / "site-packages"
    site.mkdir(parents=True, exist_ok=True)
    for wheel in wheels:
        with zipfile.ZipFile(wheel) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                segments = Path(info.filename).parts
                if segments[0].endswith(".data"):
                    if segments[1] not in ("purelib", "platlib"):
                        continue
                    destination = site.joinpath(*segments[2:])
                else:
                    destination = site.joinpath(*segments)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(archive.read(info))
    (runtime / "python313._pth").write_text("python313.zip\n.\nLib/site-packages\n..\nimport site\n", encoding="utf-8")
    app = BUILD / "app"
    app.mkdir(exist_ok=True)
    for name in ("launcher.py", "windows_app.py", "version.py", "server.py", "README.md", "requirements.txt", "TEST_CASES.md"):
        shutil.copy(ROOT / name, app / name)
    shutil.copytree(ROOT / "static", app / "static", dirs_exist_ok=True)
    shutil.copy(ROOT / "packaging" / "assets" / "CometForge.ico", app / "CometForge.ico")
    shutil.copy(ROOT / "packaging" / "LOGO.md", app / "LOGO.md")
    build_native_launcher(app / "CometForge.exe")
    (app / "installed.json").write_text('{"version":"' + __version__ + '"}', encoding="utf-8")
    gs_installer = DOWNLOADS / "gs10080w64.exe"
    download("https://github.com/ArtifexSoftware/ghostpdl-downloads/releases/download/gs10080/gs10080w64.exe", gs_installer)
    gs = BUILD / "ghostscript"
    subprocess.run([shutil.which("7zz") or "7z", "x", "-y", f"-o{gs}", str(gs_installer)], check=True)
    # NSIS packages place their payload under $INSTDIR or $_OUTDIR. Flatten
    # the directory containing bin/gswin64c.exe to the installed gs root.
    executable = next(gs.rglob("gswin64c.exe"))
    payload_root = executable.parent.parent
    if payload_root != gs:
        for item in list(payload_root.iterdir()):
            destination = gs / item.name
            if destination.exists():
                continue
            shutil.move(str(item), str(destination))
    if not (gs / "bin" / "gswin64c.exe").is_file():
        raise RuntimeError("Ghostscript payload layout not recognized")
    download("https://go.microsoft.com/fwlink/p/?LinkId=2124703", BUILD / "MicrosoftEdgeWebview2Setup.exe")
    subprocess.run([shutil.which("makensis") or "makensis", f"-DVERSION={__version__}",
                    f"-DPAYLOAD={BUILD}", "windows.nsi"], cwd=ROOT / "packaging", check=True)


if __name__ == "__main__":
    main()
