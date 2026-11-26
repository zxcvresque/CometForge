# CometForge interface

CometForge is a local PDF workspace. The interface helps people assemble sources, correct page geometry, choose export quality, and inspect the result.

The desktop editions share the same HTML/CSS/JavaScript in WKWebView on macOS and WebView2 on Windows. The operating system owns the window frame. The browser edition uses the same controls and behavior.

## Structure

Use Prism Download Manager's compact, floating glass navigation rail as the reference: a 228 px sidebar, small brand row, vertical icon-and-label navigation, source count, and restrained footer controls. Detailed Sources, Layout, Export, and Review forms belong in the workspace, not in the navigation rail. Keep the queue and finished documents visible as working content.

## Materials and themes

Prism glass uses obsidian surfaces, violet actions, cool blue and rose ambient color. Comet uses the established mint accent. Light uses porcelain surfaces. System follows the OS appearance. Remember the user's choice before first paint.

Glass belongs on navigation, toolbars, and transient menus. Content lists and PDF pages stay opaque; unused export space is white in every theme. Use the shared theme tokens. Essential labels meet 4.5:1 contrast; focus is visible and controls have names.

Reference: https://github.com/FortoGraphy/prism-download-manager. CometForge's styling and icons are adapted to its own PDF workflow.

## Motion

Mode: Operate. Motion acknowledges an action and explains continuity. Never delay navigation or move a hovered pointer target.

- Step changes: 180 ms decelerating directional continuity, at most 8 px travel and a mild opacity change. Reduced motion uses a short opacity transition.
- Buttons: 100–150 ms material, color, and press feedback. Keep hit regions still.
- Menus: about 150 ms entrance and 110 ms exit. Closing must restore keyboard focus immediately; an exit visual must be inert.
- Repeated navigation cancels previous transitions. Hidden windows stop nonessential motion.
- The existing export completion gesture is the only authored focal moment. No background loops or page-load choreography.

Verify normal and reduced motion with recorded frames. Keep document rendering and layout independent of animation state.
