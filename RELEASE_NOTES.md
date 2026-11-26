# CometForge 1.2.0

CometForge now opens as a desktop application by default, with a dedicated page-layout step and a refreshed liquid glass interface.

## What's changed

- Keep the familiar standalone desktop window, using WKWebView on macOS and WebView2 on Windows. Source launches now open desktop mode by default; browser mode remains explicit with `--browser`.
- Windows uses a GUI launcher and bundled `pythonw`; PDF engine processes run without command windows. Startup failures produce a useful error and on-disk diagnostics.
- Four-step workflow: Sources → Layout → Export → Review.
- Compact Prism-style navigation rail with detailed settings in the workspace.
- Rotate every page, individual source files, or selected page ranges in 90° increments.
- Preserve original dimensions or choose A0–A6, B4/B5, US Letter, Legal, Tabloid, Executive, or 4×6 / 5×7 photo paper, with automatic, portrait, or landscape orientation.
- Fit all content, fill the printable area with centered cropping, or retain actual size.
- No, small, medium, large, and custom millimeter margins. Unused page space is white.
- Prism-inspired liquid glass styling with selectable Prism, Comet mint, Light, and System themes; remembered choices, clear focus states, and reduced-motion/transparency fallbacks.
- Shared button feedback and brief navigation/menu transitions across Windows and macOS, with reduced-motion alternatives.
- Layout is applied before compression/splitting and included in estimates, cached exports, and aligned before/after comparison.

## Downloads

- **Windows:** `CometForge-1.2.0-Windows-x64-Setup.exe` — Windows 10/11, x64.
- **macOS:** `CometForge-1.2.0-macOS-arm64.dmg` — macOS 14+, Apple silicon.
- **Integrity:** `SHA256SUMS-1.2.0.txt` contains both installer checksums.

Python and PDF dependencies are included. Ghostscript is offered enabled by default. Windows setup includes the Visual C++ runtime and installs WebView2 if absent; WebView2 can require internet and Visual C++ installation can require administrator approval.

## Notes

- Fit keeps the whole page visible; Fill and Actual size can crop content. Original files stay untouched.
- Target-fit image recompression can be lossy. If a size cap cannot be met at the supported quality floor, the job fails instead of accepting an oversized output.
- Estimates are approximate. Actual sizes appear after Forge; already-small files are not enlarged to fill a cap.
- Save outputs before restarting; job history is not persistent.
- macOS builds are locally signed, not notarized; Windows builds are unsigned. Platform security prompts may appear.
- There are no automatic update checks or update services.

Bundled dependency licenses and source references are included with each installer.
