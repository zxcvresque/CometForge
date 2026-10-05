<p align="center">
  <img src="static/cometforge-logo.png" alt="CometForge logo" width="128" height="128" />
</p>

<h1 align="center">CometForge</h1>

<p align="center">Build. Compress. Split. Compare.<br />A local-first PDF toolkit for your desktop.</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-1.1.0-6CD8B4?style=flat-square" alt="Version 1.1.0" />
  <img src="https://img.shields.io/badge/macOS-14%2B%20Apple%20silicon-ADD888?style=flat-square" alt="macOS 14+, Apple silicon" />
  <img src="https://img.shields.io/badge/Windows-10%2F11%20x64-768AD8?style=flat-square" alt="Windows 10/11 x64" />
  <img src="https://img.shields.io/badge/processing-local-CE79D9?style=flat-square" alt="Local processing" />
</p>

<p align="center">Made by <a href="https://github.com/zxcvresque">Zxcvresque</a> · <a href="https://github.com/zxcvresque/CometForge">GitHub</a></p>

## Features

- Drop PDFs, JPGs, PNGs, TIFFs, ZIPs, or folders anywhere to fill the queue.
- Sort naturally by name or modification date; rearrange individual files or selections.
- Compress with a quality-first size cap and split into a chosen number of complete, page-based PDFs.
- Combine compression with fast web view (linearization).
- Follow a focused Sources → Export → Review workflow with macOS-inspired controls.
- Inspect each output’s filename and actual size, then compare matching pages with a draggable before/after divider.
- Download individual PDFs or all parts as a ZIP. Files are processed on your machine.

## Desktop app

Download the DMG or EXE from [GitHub Releases](https://github.com/zxcvresque/CometForge/releases/latest).

On **macOS**, open the DMG, drag CometForge to Applications, and launch it. On **Windows**, run the Setup EXE. Installed editions open in their own app window, not a browser.

Python and PDF libraries are bundled. Keep **Ghostscript** enabled in setup for Target-fit compression and comparison rendering. Windows setup also handles desktop runtime dependencies; installing WebView2 requires internet access if it is missing.

The macOS build targets Apple silicon on macOS 14+. The Windows build targets Windows 10/11 x64. Builds are not notarized on macOS or signed on Windows, so platform security prompts may appear.

## Self-host

Requires **Python 3.9+**. Run from the project folder:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python launcher.py --browser
```

On Windows:

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe launcher.py --browser
```

Self-hosting opens your default browser and binds the service to localhost. Keep the launcher running while you work.

Install Ghostscript separately for Target-fit and comparison rendering: `brew install ghostscript` on macOS, or use the [Windows installer](https://ghostscript.com/releases/gsdnld.html). For a custom location, set `COMETFORGE_GHOSTSCRIPT` to the executable path. Ghostscript is a native dependency, not a Python package.

## Quality and size

- **Off:** assemble PDFs without compression.
- **Lossless optimize:** reduce structural overhead without degrading images; a size cap is not guaranteed.
- **Target-fit:** seek the highest supported image quality below each output’s cap, checked after linearization. Image recompression can be lossy; text and vectors are preserved where possible. If the cap cannot be met at the supported quality floor, the job reports failure.

The target is a ceiling, not a size to pad files to. Already-small files are not enlarged. Sizes use decimal megabytes: **1 MB = 1,000,000 bytes**.

Quick per-part estimates do not run compression and are approximate. **Forge** reports actual output sizes and per-part progress. Split parts preserve page order and divide pages as evenly as possible; they are not raw file fragments.

**HD comparison** re-renders matching pages as you zoom, up to 576 DPI with large-page safety limits. Both sides use the same resolution; the viewer shows the actual DPI. HD cannot restore detail already lost during compression.

Download needed outputs before restarting the service; job history is not persistent.

## Dependencies

Bundled components retain their own licenses. See [third-party notices](packaging/THIRD_PARTY_NOTICES.txt) and [Ghostscript licensing](https://ghostscript.com/licensing/).
