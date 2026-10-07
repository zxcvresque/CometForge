# CometForge 1.1.1

A Windows desktop fix for CometForge's local-first PDF toolkit.

## What's changed

- Dedicated native `CometForge.exe` with embedded icons and a matching app, window and shortcut identity for taskbar pinning.
- Ghostscript compression and comparison rendering run without command windows.
- Updated Start-menu and desktop shortcuts launch the app directly.
- Upgrades preserve existing application preferences.

After upgrading from 1.1.0, unpin the old taskbar item and pin the new CometForge Start-menu shortcut once.

## Downloads

- **Windows:** `CometForge-1.1.1-Windows-x64-Setup.exe` — Windows 10/11, x64.
- **Integrity:** `SHA256SUMS-1.1.1-Windows.txt` contains the installer checksum.
- **macOS:** unchanged; download the DMG from [v1.1.0](https://github.com/zxcvresque/CometForge/releases/tag/v1.1.0).

Python and PDF dependencies are included. Ghostscript is offered enabled by default. Windows setup includes the Visual C++ runtime and installs WebView2 if missing; WebView2 installation can require internet access and Visual C++ installation can require administrator approval.

## Important notes

- Target-fit image recompression can be lossy. If a size cap cannot be met at the supported quality floor, the job fails instead of accepting an oversized output.
- Estimates are approximate. Actual sizes appear after Forge; already-small files are not enlarged to fill a cap.
- HD cannot restore detail removed during compression. Extremely large pages use a shared lower rendering resolution to limit memory usage.
- Save your outputs before restarting: job history is not persistent.
- There are no automatic update checks or update services.

Bundled dependency licenses and source references are included with each installer.
