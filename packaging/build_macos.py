"""Run with .venv/bin/python packaging/build_macos.py; produces an ARM64 DMG."""
from pathlib import Path
import importlib.metadata
import os
import platform
import shutil
import subprocess
import sys
import sysconfig

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from version import __version__


def collect_licenses(destination, gs_prefix):
    destination.mkdir(parents=True, exist_ok=True)
    # PyInstaller keeps only metadata required by hooks; retain license texts
    # explicitly for the redistributed Python dependencies.
    for distribution in importlib.metadata.distributions():
        for entry in distribution.files or []:
            if entry.is_absolute() or ".." in entry.parts:
                continue
            if not any(part.lower().startswith(("license", "copying", "notice")) for part in entry.parts):
                continue
            source = Path(distribution.locate_file(entry))
            if source.is_file():
                relative = destination / "packages" / str(entry)
                relative.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(source, relative)
    python_license = Path(sysconfig.get_path("stdlib")) / "LICENSE.txt"
    if python_license.is_file():
        shutil.copy(python_license, destination / "Python-LICENSE.txt")
    recipe = gs_prefix / ".brew" / "ghostscript.rb"
    if recipe.is_file():
        shutil.copy(recipe, destination / "ghostscript-homebrew-build.rb")
    source_dir = destination / "source"
    source_dir.mkdir(exist_ok=True)
    for name in ("server.py", "launcher.py", "version.py", "requirements.txt", "TEST_CASES.md"):
        shutil.copy(ROOT / name, source_dir / name)
    import img2pdf
    shutil.copy(img2pdf.__file__, source_dir / "img2pdf.py")


def main():
    if sys.platform != "darwin":
        raise SystemExit("Build the macOS installer on macOS.")
    out = ROOT / "packaging" / "dist"
    build = ROOT / "packaging" / "build" / "macos"
    out.mkdir(parents=True, exist_ok=True)
    build.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, str(ROOT / "packaging" / "generate_icons.py")], check=True)
    gs = Path(shutil.which("gs") or "/opt/homebrew/bin/gs").resolve()
    if not gs.is_file():
        raise SystemExit("Install Ghostscript before building: brew install ghostscript")
    gs_prefix = gs.parent.parent
    license_payload = build / "dependency-licenses"
    collect_licenses(license_payload, gs_prefix)
    args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--onedir",
            "--name", "CometForge", "--osx-bundle-identifier", "com.cometforge.desktop",
            "--icon", str(ROOT / "packaging" / "assets" / "CometForge.icns"),
            "--distpath", str(out), "--workpath", str(build), "--specpath", str(build),
            "--add-data", f"{ROOT / 'static'}:static",
            "--add-data", f"{ROOT / 'packaging' / 'THIRD_PARTY_NOTICES.txt'}:licenses",
            "--add-data", f"{ROOT / 'packaging' / 'LOGO.md'}:licenses",
            "--add-data", f"{ROOT / 'README.md'}:licenses",
            "--add-data", f"{ROOT / 'TEST_CASES.md'}:licenses",
            "--add-data", f"{license_payload}:licenses/dependencies",
            "--add-data", f"{gs_prefix / 'LICENSE'}:ghostscript",
            "--add-data", f"{gs_prefix / 'share' / 'ghostscript'}:ghostscript/share/ghostscript",
            "--add-binary", f"{gs}:ghostscript/bin",
            "--collect-all", "webview", "--hidden-import", "webview.platforms.cocoa",
            "--hidden-import", "uvicorn.logging", "--hidden-import", "uvicorn.loops.asyncio",
            "--hidden-import", "uvicorn.protocols.http.h11_impl", "--hidden-import", "uvicorn.lifespan.on",
            "--exclude-module", "tkinter", "--exclude-module", "pytest", str(ROOT / "launcher.py")]
    subprocess.run(args, cwd=ROOT, check=True)
    import plistlib
    info = out / "CometForge.app" / "Contents" / "Info.plist"
    metadata = plistlib.loads(info.read_bytes())
    metadata.update(CFBundleShortVersionString=__version__, CFBundleVersion=__version__,
                    NSHighResolutionCapable=True, LSMinimumSystemVersion="14.0",
                    NSRequiresAquaSystemAppearance=False)
    info.write_bytes(plistlib.dumps(metadata))
    # Sign locally for a consistent runnable bundle. Distribution signing and
    # notarization require the owner's Apple Developer identity.
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(out / "CometForge.app")], check=True)
    stage = build / "dmg-root"
    stage.mkdir(exist_ok=True)
    app_target = stage / "CometForge.app"
    if app_target.exists():
        shutil.rmtree(app_target)
    shutil.copytree(out / "CometForge.app", app_target, symlinks=True)
    applications = stage / "Applications"
    if not applications.exists():
        applications.symlink_to("/Applications")
    shutil.copy(ROOT / "packaging" / "THIRD_PARTY_NOTICES.txt", stage)
    shutil.copy(ROOT / "TEST_CASES.md", stage)
    filename = out / f"CometForge-{__version__}-macOS-{platform.machine()}.dmg"
    subprocess.run(["hdiutil", "create", "-volname", f"CometForge {__version__}", "-srcfolder", str(stage),
                    "-ov", "-format", "UDZO", str(filename)], check=True)
    subprocess.run(["hdiutil", "verify", str(filename)], check=True)
    print(filename)


if __name__ == "__main__":
    main()
