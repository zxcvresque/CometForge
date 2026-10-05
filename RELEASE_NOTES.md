# CometForge 1.1.0

A local-first PDF toolkit with a native desktop window on macOS and Windows.

## Highlights

- Focused Sources, Export and Review workflow with macOS-inspired controls.
- Quality-first compression with per-PDF size caps and final size validation after linearization.
- Ordered, page-based splitting into the requested number of complete PDFs.
- HD before/after comparison with a draggable divider, page navigation and adaptive rendering up to 576 DPI.
- ZIP and folder import, natural name sorting, modified-date sorting and multi-file rearranging.
- Per-part progress, actual output names and sizes, individual downloads and ZIP export.
- Welcome tour, custom app icon/favicon and a comet flyby after a successful Forge.

## Downloads

- **macOS:** `CometForge-1.1.0-macOS-arm64.dmg` — macOS 14 or newer, Apple silicon.
- **Windows:** `CometForge-1.1.0-Windows-x64-Setup.exe` — Windows 10/11, x64.
- **Integrity:** `SHA256SUMS.txt` contains the installer checksums.

Python and PDF dependencies are included. Ghostscript is offered enabled by default. Windows setup includes the Visual C++ runtime and installs WebView2 if missing; WebView2 installation can require internet access and Visual C++ installation can require administrator approval.

## Important notes

- Target-fit image recompression can be lossy. If a size cap cannot be met at the supported quality floor, the job fails instead of accepting an oversized output.
- Estimates are approximate. Actual sizes appear after Forge; already-small files are not enlarged to fill a cap.
- HD cannot restore detail removed during compression. Extremely large pages use a shared lower rendering resolution to limit memory usage.
- Save your outputs before restarting: job history is not persistent.
- There are no automatic update checks or update services.

Bundled dependency licenses and source references are included with each installer.
