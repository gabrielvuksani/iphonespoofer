# Neon Cyberpunk UI Upgrade — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the iPhone Spoofer from a sidebar-based dark theme into a neon cyberpunk floating-panel HUD with full-screen map and 12 functionality upgrades.

**Architecture:** Incremental refactor of the 5 existing files. Backend gets 3 new route-history endpoints + storage methods. Frontend gets a full CSS restyle, HTML restructure (sidebar to floating panels), and major JS additions for new features. No new dependencies.

**Tech Stack:** Python/Flask backend, Leaflet.js map, vanilla HTML/CSS/JS frontend, pymobiledevice3 device communication.

**Spec:** `docs/superpowers/specs/2026-03-24-neon-cyberpunk-ui-upgrade-design.md`

**Security note:** This app uses `esc()` and `escAttr()` helpers for HTML escaping. All user-supplied text rendered into the DOM via `.innerHTML` MUST be passed through these helpers. The existing codebase already follows this pattern — maintain it in all new code. For new inline forms, all inputs are read from `.value` properties (safe) and never injected as raw HTML.

---

## File Map

| File | Role | Changes |
|------|------|---------|
| `location_service.py` | GPS spoofing + data persistence | Add `ROUTES_FILE`, `get_routes()`, `save_route()`, `delete_route()` |
| `app.py` | Flask API server | Add 3 route history endpoints |
| `static/css/style.css` | All styles (864 lines) | Full restyle — new tokens, remove sidebar, add HUD panel system, animations, light theme |
| `templates/index.html` | HTML layout (412 lines) | Remove sidebar, add floating panels, multi-device dropdown, keyboard shortcuts overlay, coordinate HUD |
| `static/js/app.js` | All frontend logic (1025 lines) | Panel system, inline forms, custom marker, live tracking, search nav, shortcuts, route history, undo, HUD |

**Note:** This project has no test suite. Each task is verified by running the app (`python app.py`) and manually checking the UI. Verification steps describe what to look for.

---

## Task 1: Backend — Route History Endpoints

**Files:**
- Modify: `location_service.py:34-37` (add ROUTES_FILE constant)
- Modify: `location_service.py:630+` (add 3 new methods after `check_schedules`)
- Modify: `app.py:567+` (add 3 new endpoints after saved-locations section)

- [ ] **Step 1: Add ROUTES_FILE constant to location_service.py**

In `location_service.py`, after line 37 (`SCHEDULES_FILE = ...`), add:

```python
ROUTES_FILE = os.path.join(DATA_DIR, "routes.json")
```

- [ ] **Step 2: Add route storage methods to LocationService**

In `location_service.py`, after the `check_schedules` method (after line 629), add:

```python
    # ── Route history ─────────────────────────────────

    def get_routes(self):
        if not os.path.exists(ROUTES_FILE):
            return []
        try:
            with open(ROUTES_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []

    def save_route(self, name, waypoints, speed, mode, distance):
        route = {
            "id": str(int(time.time() * 1000)),
            "name": name,
            "waypoints": waypoints,
            "speed": speed,
            "mode": mode,
            "distance_km": distance,
            "created": datetime.now().isoformat(),
        }
        with self._file_lock:
            routes = self.get_routes()
            routes.insert(0, route)
            routes = routes[:50]  # Keep last 50
            with open(ROUTES_FILE, "w") as f:
                json.dump(routes, f, indent=2)
        return {"status": f"Route '{name}' saved", "route": route}

    def delete_route(self, route_id):
        with self._file_lock:
            routes = [r for r in self.get_routes() if r["id"] != route_id]
            with open(ROUTES_FILE, "w") as f:
                json.dump(routes, f, indent=2)
        return {"status": "Route deleted"}
```

- [ ] **Step 3: Add route history API endpoints to app.py**

In `app.py`, after the History API section (after line 576), add:

```python
# ── Route history API ─────────────────────────────────

@app.route("/api/routes")
def api_routes_list():
    if loc_svc is None:
        return jsonify([])
    return jsonify(loc_svc.get_routes())


@app.route("/api/routes", methods=["POST"])
def api_routes_save():
    if loc_svc is None:
        return jsonify({"error": "Not connected"}), 503
    data = request.json or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Name is required"}), 400
    waypoints = data.get("waypoints", [])
    if len(waypoints) < 2:
        return jsonify({"error": "Need at least 2 waypoints"}), 400
    speed = data.get("speed", 5)
    mode = data.get("mode", "once")
    distance = data.get("distance_km", 0)
    return jsonify(loc_svc.save_route(name, waypoints, speed, mode, distance))


@app.route("/api/routes/<route_id>", methods=["DELETE"])
def api_routes_delete(route_id):
    if loc_svc is None:
        return jsonify({"error": "Not connected"}), 503
    return jsonify(loc_svc.delete_route(route_id))
```

- [ ] **Step 4: Verify backend**

Run: `cd /Users/gabrielvuksani/Projects/iphonespoofer && python -c "from location_service import LocationService; print('OK')"`

Expected: `OK` (no import errors)

- [ ] **Step 5: Commit**

```bash
git add location_service.py app.py
git commit -m "feat: add route history API endpoints (save/list/delete)"
```

---

## Task 2: CSS — Neon Cyberpunk Color Tokens + Base Styles

**Files:**
- Modify: `static/css/style.css:1-50` (root variables and body)

This task ONLY updates the CSS custom properties and key style rules. Layout stays unchanged until Task 4.

- [ ] **Step 1: Update `:root` variables**

Replace the `:root` block (lines 7-33) with the new neon cyberpunk tokens:

```css
:root {
    --bg: #0A0A0F;
    --surface: rgba(15, 15, 22, 0.88);
    --surface-solid: #0F0F16;
    --surface-hover: rgba(139, 92, 246, 0.08);
    --surface-active: rgba(139, 92, 246, 0.06);
    --border: rgba(139, 92, 246, 0.12);
    --border-focus: rgba(139, 92, 246, 0.4);
    --text: #E2E8F0;
    --text-secondary: rgba(226, 232, 240, 0.5);
    --text-tertiary: rgba(226, 232, 240, 0.25);
    --accent: #8B5CF6;
    --accent-bg: rgba(139, 92, 246, 0.08);
    --accent-glow: rgba(139, 92, 246, 0.15);
    --green: #39FF14;
    --green-bg: rgba(57, 255, 20, 0.1);
    --red: #FF3366;
    --red-bg: rgba(255, 51, 102, 0.1);
    --amber: #FFE031;
    --amber-bg: rgba(255, 224, 49, 0.1);
    --radius: 10px;
    --radius-sm: 6px;
    --topbar-h: 48px;
    --font: 'Outfit', -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
    --mono: 'JetBrains Mono', 'SF Mono', 'Fira Code', monospace;
}
```

- [ ] **Step 2: Update button glow effects**

Replace `.btn-blue` styles (lines 333-341) with:

```css
.btn-blue {
    background: linear-gradient(135deg, #8B5CF6, #6366F1);
    color: #fff;
    box-shadow: 0 0 12px rgba(139, 92, 246, 0.3);
}
.btn-blue:hover:not(:disabled) {
    background: linear-gradient(135deg, #9B6FF6, #7C7CF1);
    box-shadow: 0 0 20px rgba(139, 92, 246, 0.4);
}
```

Replace `.btn-red` (lines 343-344) with:

```css
.btn-red { background: var(--red); color: #fff; box-shadow: 0 0 8px var(--red-bg); }
.btn-red:hover:not(:disabled) { background: #FF5580; box-shadow: 0 0 14px var(--red-bg); }
```

- [ ] **Step 3: Update connected dot and segment active states**

Replace `.dot.connected` (lines 96-99) with:

```css
.dot.connected {
    background: var(--green);
    box-shadow: 0 0 8px rgba(57, 255, 20, 0.5);
    animation: dotPulse 2s ease-in-out infinite;
}

@keyframes dotPulse {
    0%, 100% { box-shadow: 0 0 8px rgba(57, 255, 20, 0.5); }
    50% { box-shadow: 0 0 14px rgba(57, 255, 20, 0.8); }
}
```

Replace `.seg-btn.active` (lines 381-386) with:

```css
.seg-btn.active {
    background: linear-gradient(135deg, #8B5CF6, #6366F1);
    border-color: var(--accent);
    color: #fff;
    box-shadow: 0 0 8px var(--accent-glow);
}
```

- [ ] **Step 4: Update light theme tokens**

Replace the `body.light` block (lines 826-854) with:

```css
body.light {
    --bg: #F0F2F5;
    --surface: rgba(255, 255, 255, 0.85);
    --surface-solid: #FFFFFF;
    --surface-hover: rgba(124, 58, 237, 0.06);
    --surface-active: rgba(124, 58, 237, 0.04);
    --border: rgba(124, 58, 237, 0.1);
    --border-focus: rgba(124, 58, 237, 0.35);
    --text: #1A1D24;
    --text-secondary: rgba(26, 29, 36, 0.5);
    --text-tertiary: rgba(26, 29, 36, 0.3);
    --accent: #7C3AED;
    --accent-bg: rgba(124, 58, 237, 0.08);
    --accent-glow: rgba(124, 58, 237, 0.1);
    --green: #16A34A;
    --green-bg: rgba(22, 163, 74, 0.08);
    --red: #DC2626;
    --red-bg: rgba(220, 38, 38, 0.08);
    --amber: #D97706;
    --amber-bg: rgba(217, 119, 6, 0.08);
}

body.light #topbar { background: rgba(240, 242, 245, 0.92); }
body.light .hud-panel { background: rgba(255, 255, 255, 0.92); }
body.light .leaflet-container { background: var(--bg); }
body.light .btn-blue { color: #fff; }
body.light .seg-btn.active { color: #fff; }
body.light .leaflet-control-attribution { background: rgba(255, 255, 255, 0.8) !important; }
```

- [ ] **Step 5: Verify**

Run the app. Existing layout should still work but with purple/green neon colors instead of cyan. Light theme toggle should show lighter purples.

- [ ] **Step 6: Commit**

```bash
git add static/css/style.css
git commit -m "feat: neon cyberpunk color tokens and glow effects"
```

---

## Task 3: HTML — Restructure to Floating Panels

**Files:**
- Modify: `templates/index.html` (full restructure of body content)

This replaces the sidebar HTML with floating panel elements. The JS still references old IDs so we keep the same `id` attributes where possible for backward compatibility.

- [ ] **Step 1: Replace the sidebar with floating panel HTML**

Remove the entire sidebar block (lines 173-391, from `<!-- Sidebar -->` to closing `</div>`) and replace with the new floating panel structure. This includes:
- `#panel-location` — Location panel with coord display, inputs, action buttons, inline save/schedule forms, cooldown
- `#panel-places` — Places panel with tabs (Recent/Saved/Popular)
- `#panel-movement` — Movement panel with speed, route controls, joystick, wander, route history, profiles, schedules
- `#status-bar` — Bottom center status pills
- `#coord-hud` — Bottom-right coordinate display on map hover
- `#shortcuts-overlay` — Keyboard shortcuts reference (centered overlay)
- `#device-dropdown` — Multi-device picker dropdown
- `#setup-guide` — Connection setup guide (shown when no device)

Each panel uses the `.hud-panel` class with `.hud-panel-header` (clickable to collapse) and `.hud-panel-body` (content area).

Key new elements:
- `#btn-undo` — Undo teleport button (disabled by default)
- `#save-form`, `#profile-form`, `#schedule-form` — Inline forms replacing `prompt()`
- `.cat-pill`, `.day-pill` — Category and day selector pills
- `#follow-mode` — Checkbox for follow mode during movement
- `#btn-route-save` — Save current route button
- `#btn-shortcuts` — Shortcuts button in topbar
- `#coord-display` / `#coord-text` — Clickable coord display in Location panel

- [ ] **Step 2: Update topbar**

Add `?` shortcuts button and move connection badge with click handler for multi-device picker. Remove sidebar toggle hamburger button.

- [ ] **Step 3: Update onboarding SVGs**

Replace any `var(--blue)` stroke references in onboarding SVGs with `var(--accent)`.

- [ ] **Step 4: Verify**

Load the page. It will look partially broken (CSS for new panel classes not yet applied). Verify no HTML syntax errors by checking browser console.

- [ ] **Step 5: Commit**

```bash
git add templates/index.html
git commit -m "feat: restructure HTML from sidebar to floating HUD panels"
```

---

## Task 4: CSS — Floating Panel System + New Component Styles

**Files:**
- Modify: `static/css/style.css` (replace sidebar styles, add all new component styles)

- [ ] **Step 1: Remove sidebar CSS, add HUD panel system**

Remove all sidebar-related rules (`#sidebar`, `.sidebar-section`, `.section-header`, `.section-body`, `.section-content`, `.section-chevron`, `#sidebar.collapsed`) and replace with `.hud-panel` system:
- `.hud-panel` — fixed position, glassmorphism background, border, shadow
- `.hud-panel-left` / `.hud-panel-right` — positioning
- `.hud-panel.collapsed .hud-panel-body` — `max-height: 0; overflow: hidden`
- `.hud-panel-header` — mono font, accent color, clickable
- `.hud-panel-close` — X button, turns red on hover
- `.hud-panel-body` — content with max-height transition

- [ ] **Step 2: Update `#map` to fill screen**

Change `#map` left from `var(--sidebar-w)` to `0`. Remove the `#sidebar.collapsed ~ #map` rule.

- [ ] **Step 3: Add inline form styles**

- `.inline-form` — expand animation
- `.inline-form-title` — mono, accent colored
- `.form-input` — purple-tinted input
- `.category-pills` / `.cat-pill` — selectable category buttons
- `.day-pills` / `.day-pill` — selectable day buttons
- `.coord-display` / `.coord-glow` — glowing coordinate text

- [ ] **Step 4: Add status bar styles**

- `#status-bar` — fixed bottom center, flex row of pills
- `.status-pill` — glassmorphism pill with mono text
- `.status-dot` — small colored indicator

- [ ] **Step 5: Add keyboard shortcuts overlay styles**

- `#shortcuts-overlay` — full-screen backdrop
- `.shortcuts-card` — centered card with purple border glow
- `.shortcut-row` — key-action pair
- `kbd` — styled key cap

- [ ] **Step 6: Add multi-device dropdown and search highlight styles**

- `#device-dropdown` — positioned below device badge
- `.device-option` — clickable device row
- `.search-item.highlighted` — purple left border highlight

- [ ] **Step 7: Add coordinate HUD style**

- `#coord-hud` — fixed bottom-right, mono purple text, pointer-events none

- [ ] **Step 8: Verify**

Run the app. Floating panels should render correctly over the full-screen map with proper glassmorphism. All panel sections should be visible and collapsible.

- [ ] **Step 9: Commit**

```bash
git add static/css/style.css
git commit -m "feat: floating HUD panel CSS system replacing sidebar"
```

---

## Task 5: JS — Panel System + Inline Forms + Undo

**Files:**
- Modify: `static/js/app.js`

- [ ] **Step 1: Add new state variables**

At the top of app.js after existing state vars, add:

```javascript
let previousLocation = null;
let followMode = false;
let movementPolling = null;
let searchHighlightIndex = -1;
let routeDistanceKm = 0;
let routeTraveledLine = null;
let trailPoints = [];
```

- [ ] **Step 2: Add panel collapse/expand system**

Replace `toggleSidebar` with `togglePanel` and `restorePanelStates` functions. Panels store state in localStorage keyed by panel ID.

- [ ] **Step 3: Update DOMContentLoaded event listeners**

Wire up:
- Panel header clicks for collapse/expand
- Panel close buttons
- Inline form show/hide buttons (save, profile, schedule)
- Category pill and day pill toggles
- Undo button
- Shortcuts button and overlay close
- Device badge click for multi-device dropdown
- Follow mode checkbox
- Coordinate display click to toggle input visibility
- Position Places panel below Location panel using ResizeObserver
- Call `restorePanelStates()` on load

- [ ] **Step 4: Replace `saveLocation()` with inline form**

Old: calls `prompt()` for name.
New: `showSaveForm()` shows `#save-form` div, `confirmSaveLocation()` reads `#save-name` input value and selected category pill, then POSTs to `/api/saved`.

- [ ] **Step 5: Replace `saveProfile()` with inline form**

Old: calls `prompt()` for name.
New: `showProfileForm()` shows `#profile-form`, `confirmSaveProfile()` reads `#profile-name` input.

- [ ] **Step 6: Replace `addSchedule()` with inline form**

Old: calls `prompt()` for name and time.
New: `showScheduleForm()` shows `#schedule-form`, `confirmAddSchedule()` reads `#schedule-name`, `#schedule-time`, and active `.day-pill` elements.

- [ ] **Step 7: Add undo teleport**

`undoTeleport()` — if `previousLocation` exists, POST it to `/api/location/set`, update marker, clear previousLocation, disable undo button.

Update `setLocation()` and `teleportTo()` to save current location to `previousLocation` before each set call. Enable undo button and set tooltip.

- [ ] **Step 8: Update `pollDevice` for new HTML structure**

The device info elements moved into `#device-info-compact` inside the Location panel. Update selectors. The setup guide `#setup-guide` now needs to be shown inside the Location panel body when no device is connected.

- [ ] **Step 9: Remove dead sidebar code**

Remove `toggleSidebar`, old accordion section listeners, old `$("btn-profile-save")` / `$("btn-schedule-add")` handlers that used `prompt()`.

- [ ] **Step 10: Verify**

Run the app. Panels should collapse/expand and remember state. Save/Profile/Schedule use inline forms. Undo works after setting a location.

- [ ] **Step 11: Commit**

```bash
git add static/js/app.js
git commit -m "feat: panel system, inline forms, undo teleport"
```

---

## Task 6: JS + CSS — Custom Map Marker + Live Tracking + Coord HUD

**Files:**
- Modify: `static/js/app.js`
- Modify: `static/css/style.css`

- [ ] **Step 1: Add marker CSS**

Add `.neon-marker`, `.neon-marker-dot`, `.neon-marker-pulse` styles with the `@keyframes markerPulse` breathing animation. Light theme variant with adjusted colors.

- [ ] **Step 2: Replace `placeMarker` to use `L.divIcon`**

Old: `L.circleMarker` with blue fill.
New: `L.marker` with `L.divIcon` containing `.neon-marker` HTML. Update trail points array. Update `#coord-text` display.

- [ ] **Step 3: Add live position tracking**

`startMovementTracking()` — setInterval polling `/api/location/current` every 500ms.
`stopMovementTracking()` — clearInterval, reset trail.
`pollPosition()` — fetch current location, update marker, optionally pan map if follow mode is on.

Wire into: `joystickMove` starts tracking, `joystickStop` stops it. Same for `startWander`/`stopWander` and `startRoute`/`endRoute`.

- [ ] **Step 4: Add coordinate HUD**

In DOMContentLoaded, add `map.on("mousemove")` handler that updates `#coord-hud-text` with cursor lat/lon. `map.on("mouseout")` hides the HUD.

- [ ] **Step 5: Add status bar update function**

`updateStatusBar()` — updates speed display in status pill. Called from speed change handlers.

Update `pollCooldown` to also set `#status-cooldown-text` and `#status-dot` class.

- [ ] **Step 6: Verify**

Map marker is pulsing purple neon dot. During joystick/wander, marker updates every 500ms. Hovering over map shows coordinates at bottom-right.

- [ ] **Step 7: Commit**

```bash
git add static/js/app.js static/css/style.css
git commit -m "feat: custom neon map marker, live tracking, coordinate HUD"
```

---

## Task 7: JS — Search Keyboard Nav + Keyboard Shortcuts

**Files:**
- Modify: `static/js/app.js`

- [ ] **Step 1: Add search keyboard navigation**

Add `onSearchKeydown` handler on `#search-input` keydown. Arrow Down/Up moves `searchHighlightIndex` through results. Enter selects. Escape closes. `updateSearchHighlight` toggles `.highlighted` class and scrolls into view. Mouse enter on items also updates highlight. Reset index in `doSearch`.

- [ ] **Step 2: Add keyboard shortcuts**

Update `onKeyDown`: add `?` to toggle shortcuts overlay, `T` to toggle teleport, `Escape` to close forms/overlays, `+`/`-` for zoom. Guard against input/textarea/select focus.

Add `toggleShortcuts()` function. Add click handler on `#shortcuts-overlay` background to dismiss.

- [ ] **Step 3: Verify**

Search: type, arrow keys navigate, Enter selects, Escape closes. `?` shows shortcuts. `T` toggles teleport. Escape closes open forms.

- [ ] **Step 4: Commit**

```bash
git add static/js/app.js
git commit -m "feat: search keyboard navigation and keyboard shortcuts panel"
```

---

## Task 8: JS — Multi-Device Picker + Route History + Animated Routes

**Files:**
- Modify: `static/js/app.js`

- [ ] **Step 1: Add multi-device picker**

`toggleDeviceDropdown()` — fetches `/api/devices`, renders dropdown below device badge with UDID + connection type badges. Click device calls `connectDevice()` with wifi preference based on available types. Uses `/api/device/connect` for new devices, `/api/device/switch` for toggling connection type. Close on outside click.

All device UDIDs rendered via `esc()` helper. Connection type badges rendered with `escAttr()` for data attributes.

- [ ] **Step 2: Add route history functions**

`loadRouteHistory()` — fetches `/api/routes`, renders list in `#route-history-list`. Click loads waypoints onto map. Delete button removes route.

`saveCurrentRoute()` — POSTs current `routePoints` to `/api/routes`.

All route names rendered via `esc()` helper. Route IDs use `escAttr()` in data attributes.

Call `loadRouteHistory()` in DOMContentLoaded.

- [ ] **Step 3: Add distance/ETA to route status**

Update `startRoute` to store `routeDistanceKm`. Update `pollRoute` to calculate remaining distance and ETA, display in `#status-route-text`. Show `#status-route` pill when route active, hide in `endRoute`.

After route completes, show `#btn-route-save`.

- [ ] **Step 4: Update route polyline colors**

Route markers and polylines use `#8B5CF6` purple instead of old `#a78bfa`. Route display line uses weight 3, opacity 0.6.

- [ ] **Step 5: Verify**

Device badge click shows dropdown. Route history loads. Route shows distance/ETA in status bar. Save route after completion works.

- [ ] **Step 6: Commit**

```bash
git add static/js/app.js
git commit -m "feat: multi-device picker, route history, animated route display"
```

---

## Task 9: Final Polish + Onboarding Restyle

**Files:**
- Modify: `static/css/style.css`
- Modify: `templates/index.html`

- [ ] **Step 1: Update onboarding SVG colors**

Replace any `var(--blue)` stroke references in onboarding HTML with `var(--accent)`.

- [ ] **Step 2: Remove dead CSS**

Remove any remaining sidebar-era rules not already cleaned up: `--sidebar-w`, `#sidebar`, `.sidebar-section`, `.section-header`, `.section-chevron`, `#sidebar.collapsed ~ #map`.

- [ ] **Step 3: Polish pass**

- `.joy-btn:active` / `.joy-btn.active` use new purple glow
- `.cooldown-bar-fill` gradient uses new red/amber/green
- `.conn-badge.usb` uses `var(--accent-bg)` / `var(--accent)`
- `.conn-badge.wifi` uses `var(--green-bg)` / `var(--green)`
- Toast colors use new tokens
- Verify all `var(--blue)` references are gone (replaced with `var(--accent)`)

- [ ] **Step 4: Full end-to-end verification**

1. Load app — full-screen map with floating panels, neon theme
2. Click map — pulsing purple marker
3. Warp — location sets, cooldown starts
4. Undo — goes back
5. Save — inline form in Location panel
6. Teleport mode — click map to instant-move
7. Search — type, arrow keys, Enter
8. Shift+click — route points, start, see status bar ETA
9. WASD — joystick with live tracking
10. `?` key — shortcuts overlay
11. Device badge — multi-device dropdown
12. Light theme — purple light theme
13. Onboarding — neon styled
14. Map hover — coord HUD at bottom-right
15. Panels — collapse/expand, remember state

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: onboarding restyle, final polish, neon cyberpunk UI complete"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Backend route history endpoints | `location_service.py`, `app.py` |
| 2 | CSS neon cyberpunk color tokens | `style.css` |
| 3 | HTML floating panel restructure | `index.html` |
| 4 | CSS floating panel system | `style.css` |
| 5 | JS panel system + inline forms + undo | `app.js` |
| 6 | Custom marker + live tracking + coord HUD | `app.js`, `style.css` |
| 7 | Search keyboard nav + shortcuts panel | `app.js` |
| 8 | Multi-device picker + route history + animated routes | `app.js` |
| 9 | Onboarding restyle + final polish | `style.css`, `index.html` |

9 tasks, 9 commits. Each task is independently verifiable by running the app.
