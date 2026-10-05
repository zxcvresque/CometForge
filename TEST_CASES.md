# Manual test cases — CometForge 1.1.0

No further visual/computer testing is being performed by the assistant. These cases are for manual testing on your machines.

Use the supplied `Test Case/Preschool Curriculum Final.pdf` (224 pages, approximately 198 decimal MB) and the images in the test ZIP. Test fixtures are local and intentionally excluded from GitHub and the installers.

## Installation

1. **macOS:** open the DMG, drag CometForge to Applications, and launch it. Expect the custom mint comet icon, a standalone app window, and first-run setup with Ghostscript checked. Continue setup: the main interface should open without a browser tab or a setup error. No system Python/Homebrew is needed by the packaged app. Supported build: Apple silicon, macOS 14+.
2. **Windows:** run Setup on Windows 10/11 x64. Expect required app/Python dependencies installed and Ghostscript checked by default. Allow the Visual C++ runtime install if it is missing. WebView2 may need Internet if absent. Launch from the desktop/Start menu: expect the custom icon and a standalone app window. Windows execution requires testing on a Windows machine.
3. **Optional engine:** on a separate test installation, disable Ghostscript. Lossless/Off should work; an export needing Target-fit should explain that Ghostscript is unavailable. Slider comparison should explain its rendering dependency and offer PDF preview fallback.
4. **Self-host:** run `.venv/bin/python launcher.py --browser`. Expect the default browser to open after the local service starts. No release/update checks should appear.

## Queue and controls

5. **Natural sorting:** import images named `Guide1.jpg`, `10.jpg`, `2.jpg`, and `1.jpg` in that order. Expect `1.jpg`, `2.jpg`, `10.jpg`, `Guide1.jpg`. Add another numeric file and confirm natural ordering persists.
6. **Modified dates:** select newest-first and oldest-first. Compare the order with the files' actual modification timestamps. Equal dates should fall back to natural name order.
7. **Group moves:** select two separated rows and choose To top/Up/Down/To bottom. Both selected rows should move with their internal order preserved; sort should switch to Manual. Drag a single last row above the first, then drag a selected group to the top. The queue should remain usable after each move.
8. **Menus and settings:** open compression/sort/view-layout selectors. Expect one blue selected row with a checkmark, a quiet gray hover/focus row, and visible spacing between rows. Test arrows, Enter, Escape, typing and outside-click dismissal. Collapse the left panel, then reopen it; reload should remember the panel state.

## Estimates and compression

9. **Quick size estimate:** import the test PDF, enable five parts, and drag the cap to 20.0, 19.9 and 14.0 MB. The slider, number and displayed target should agree. Expect a supposed size and approximate range for all five parts. There must be no Measure exactly action or full compression triggered by changing the slider. Estimates are approximate; actual measurements appear after Forge.
10. **20 MB export:** choose Target-fit, five parts, 20 MB, and Fast web view. Forge. Expect current part/total, operation and fitting pass details. Progress should not jump backward. On the supplied fixture, the calibrated run produced approximately 19.96, 18.31, 17.97, 19.29 and 19.34 MB. All parts must stay below 20,000,000 bytes. Page counts must be 45/45/45/45/44, totaling 224, in original order.
11. **Tighter cap and limits:** try 14 MB per part. A successful Target-fit export must remain below 14,000,000 bytes after linearization. If the quality floor prevents fitting, expect a clear failure recommending a larger cap or more parts. Lossless mode may exceed the cap; it must say so rather than imply a successful size fit. Documents already below the cap should not be padded or needlessly degraded.
12. **Names and downloads:** use `Curriculum` without an extension and a name containing spaces/non-ASCII characters. Single output must end in `.pdf`; split exports must contain five correctly named `.pdf` files in a `.zip`. Each output row should show its actual size. Download individual PDFs and the ZIP; both should open correctly.

## Before/after and result navigation

13. **Vertical comparison slider:** after exporting, choose Before / after. Expect the original and compressed version of the same page under one draggable vertical divider. Drag to both extremes and halfway, then use the keyboard to move the divider. The two pages must stay aligned, with no resizing as the divider moves.
14. **Pages and parts:** change the comparison page, then select another output part. Expect both layers to show the same page within that part; selecting a new part should reset to its first page. Last-page/next controls must respect the part's page count. Use the supplied detailed curriculum pages to judge legibility and image artifacts.
15. **Output-only and return:** switch to Output only to use the PDF viewer. Back to queue should restore the original queue and ordering. Forge again with different settings and confirm all output rows/comparison pages correspond to the new job.

## ZIPs, folders and first launch

16. **Drop anywhere:** drop a PDF/image over the queue, header, preview or settings—not just the Add files box. Each drop should add files once without navigating away. Internal queue dragging should still reorder rather than re-import files.
17. **ZIP import:** drop the supplied image ZIP. Expect its supported files expanded into the queue with individual names, sizes and dates, naturally sorted. A broken ZIP should produce a readable import error. Unsupported archive contents should not become PDF pages.
18. **Folder import:** drop a folder with nested subfolders, or choose it using Folder. Expect all supported descendants, including directories with more than 100 entries. Compare natural/date sorting with the original files.
19. **Compact settings:** select each compression mode. Only its relevant help should appear below the selector. Expand/collapse Split & fast web view and Output size estimates; Forge and the primary controls should remain easy to reach.
20. **Welcome tour:** on a fresh installation, expect the CometForge logo, Made by Zxcvresque, and the correct GitHub link. Try Next, Previous, Skip and the don't-show-again option. Reopen the tour from Quick tour. Keyboard focus should stay in the open tour; Escape should dismiss it without losing queue files.

Report failures with the platform, installer version, input file, selected settings, and the step above. A screenshot is optional; exact error text and sizes help diagnose issues.
