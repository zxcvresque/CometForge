# Verification guide — CometForge 1.2.0

The desktop edition uses its own system WebView window and a localhost PDF service. The optional browser edition is launched explicitly with `--browser`.

## Automated regression checks

Run from a Python environment with `requirements-dev.txt` installed and Ghostscript available:

```sh
python scripts/test_windows_desktop.py
python scripts/test_page_layout.py
python scripts/verify_v1_1.py
python scripts/test_hd_render.py
node --test scripts/test_guided_ui.cjs scripts/test_comparison_ui.cjs scripts/test_layout_ui.cjs
```

Platform smoke tests additionally launch the installed application window. Local test fixtures and generated work folders are excluded from releases.

## Native installation and startup

1. **macOS:** mount the DMG, drag CometForge to Applications and open it. Expect the comet app icon, standard macOS window controls, a dedicated app window. No system Python or Homebrew is required. Supported installer: Apple silicon, macOS 14+.
2. **Windows:** run Setup on Windows 10/11 x64 with Ghostscript enabled. The bundled Visual C++ runtime may need administrator approval if absent. Launch from Start or the desktop shortcut. Expect the comet window/taskbar icon and the desktop interface, with no terminal window. Setup installs WebView2 if it is missing.
3. **Shutdown:** close the main window after completing an export. The app and bundled launcher must exit. The localhost service must stop when the desktop window closes.
4. **Optional browser:** launch `python launcher.py --browser`. Expect the default browser and localhost service; closing the browser tab does not stop that explicitly hosted service. Ctrl+C stops the launcher. `--no-browser` starts only the service.

## Import and queue

5. Add PDFs, JPEGs, PNGs and multipage TIFFs, plus a ZIP and nested folder. Supported entries should appear once; unsupported entries should be ignored. A malformed ZIP must give a readable error. Originals remain unchanged.
6. Try natural sorting with `1.jpg`, `2.jpg`, `10.jpg`; compare modification-date sorting with actual source timestamps. Select multiple files, move them together, and drag rows to change order.
7. Rotate a source clockwise. Reorder the source and verify its rotation follows it. Remove a file and add another; the remaining queue must stay usable.

## Layout

8. Follow Sources → Layout → Export → Review. Choose A4 portrait, US Letter landscape, then A3, A5, A6, B5, Legal, Tabloid and Executive. Export and inspect PDF dimensions. Original size should preserve mixed page sizes by default.
9. With a wide image on portrait paper, **Fit** must keep all content visible with white spare space; **Fill** must crop centrally; **Actual size** must preserve scale and crop content outside the printable area. Transparent PNG areas and unused space must render white.
10. Try none, small (5 mm), medium (10 mm), large (20 mm), and custom margins. Margins must stay white even with Fill. Excessive margins on small paper must produce a useful error.
11. Combine a source rotation, global rotation, and a page-range rotation such as `1, 3–5`. Check the resulting clockwise turns. Invalid/out-of-range page selections must not silently export the wrong document. Page numbers refer to the assembled queue; reset page turns when changing its order.
12. Rotate a PDF with a CropBox, existing rotation, non-default UserUnit, and visible annotations. Rotation-only exports retain annotations; changing paper size produces print-ready page appearance with visible annotations flattened.

## Export and save

13. Use a name containing spaces and non-ASCII characters. Save one output PDF and a ZIP of split outputs using Download actions; open the saved files and verify names and page order.
14. Export with Off, Lossless, and Target-fit, with and without fast web view. Split an 11-page document into five parts: expect 3/2/2/2/2 pages. All pages must be preserved. A split count larger than the page count must fail clearly.
15. Target-fit must stay below its per-PDF decimal MB cap after linearization or report that the supported quality floor cannot meet it. Already-small files must not be padded. Lossless does not promise a size cap. Estimates are approximate; completed sizes are actual bytes.
16. Export again after changing rotation, margins, size, or fitting. The new layout must be reflected in the output and cache behavior. Busy progress should identify the current stage and part, and controls should recover after errors.

## PDF preview, themes, and accessibility

17. Select each completed part. Before/after must show matching pages at matching resolution. Move the divider with mouse and keyboard, change pages, zoom, fit, and switch to output-only. Rapid changes must discard stale render results.
18. Without Ghostscript, preview and Target-fit must explain the missing dependency; Off and Lossless exports must still be saveable.
19. Check all steps at 1380×900 and 800×600, with long filenames and keyboard-only navigation. Controls must remain reachable, labels readable, and focus visible.
20. Switch between Prism, Comet mint, Light, and System appearance, then reload to confirm the choice is remembered. Document pages remain solid white. Reduced transparency/high contrast must use opaque surfaces; Test both macOS and Windows glass treatment. Motion must never be required to understand the interface.

The Windows release workflow installs the built Setup EXE, runs regressions, then samples visible windows and descendants while the app imports, exports, and renders a PDF. It checks for console windows , validates export and preview results, and closes the window to verify clean shutdown.
