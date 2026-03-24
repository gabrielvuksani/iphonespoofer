# iPhone Spoofer — Neon Cyberpunk UI Upgrade

**Date:** 2026-03-24
**Approach:** Incremental refactor of existing files

---

## Summary

Full UI overhaul + 12 functionality upgrades for the iPhone Location Spoofer app. Transforms the current sidebar-based dark theme into a neon cyberpunk floating-panel HUD with full-screen map, sci-fi terminal aesthetics, and significant UX improvements.

## Design Decisions

| Decision | Choice |
|----------|--------|
| Theme | Neon Cyberpunk — purple/green glow, sci-fi terminal |
| Layout | Floating panels over full-screen map (no sidebar) |
| Panel arrangement | Symmetric HUD — Location left, Movement right, status pills bottom center |
| Dialogs | Inline panel expansion (no overlays, except keyboard shortcuts reference) |
| Implementation | Incremental refactor of existing `index.html`, `style.css`, `app.js` |

---

## 1. Visual System

### Color Palette

| Token | Current | New | Usage |
|-------|---------|-----|-------|
| `--accent` | `#00D4FF` | `#8B5CF6` (purple) | Primary actions, active states |
| `--accent-glow` | cyan glow | `rgba(139,92,246,0.15)` | Box shadows, glows |
| `--green` | `#00E5A0` | `#39FF14` (neon green) | Connected, SAFE, success |
| `--red` | `#FF5C5C` | `#FF3366` (hot pink-red) | Errors, stop, WAIT |
| `--amber` | `#FFB800` | `#FFE031` (electric yellow) | Warnings, cooldown mid |
| `--bg` | `#0B0E14` | `#0A0A0F` | Deeper black |
| `--surface` | `rgba(20,26,36,0.75)` | `rgba(15,15,22,0.88)` | Panel backgrounds |
| `--border` | `rgba(255,255,255,0.05)` | `rgba(139,92,246,0.12)` | Purple-tinted borders |

### Typography

- **Panel titles:** JetBrains Mono, 9px, weight 700, `letter-spacing: 0.08em`, uppercase, `color: var(--accent)`
- **Body text:** Outfit, 11-12px
- **Coordinates:** JetBrains Mono, 13px, `text-shadow: 0 0 10px var(--accent-glow)`

### Glow Effects

- Active buttons: `box-shadow: 0 0 12px rgba(139,92,246,0.3)`
- Connected dot: pulsing `box-shadow: 0 0 8px rgba(57,255,20,0.5)`
- Map marker: `box-shadow: 0 0 20px rgba(139,92,246,0.6), 0 0 40px rgba(139,92,246,0.2)`

### Light Theme

Light theme gets matching treatment: lighter purples (`#7C3AED` accent), adjusted glows with lower opacity, white/gray surfaces. Same layout, inverted tokens.

---

## 2. Layout Architecture

### Removed

- Fixed 310px sidebar with accordion sections
- `#sidebar` element and all `.sidebar-section` CSS

### New Layout

Full-screen map (`#map` fills viewport below topbar) with floating elements:

### Top Bar (restyled, stays fixed)

- **Left:** Device status dot + device name, search bar (centered, wider)
- **Right:** Teleport toggle pill, coordinate format toggle, theme toggle, keyboard shortcuts button (`?`)

### Left Panel — Location (~180px wide, fixed top-left below topbar)

- Panel title bar: "LOCATION" + collapse (X) button
- Coordinate display (monospace, glowing purple text-shadow)
- Lat/Lon inputs (click to expand/edit)
- Action buttons: Warp / Reset / Undo / Save
- Save form: expands inline with name input + category selector (Favorite/Work/Gaming)
- Cooldown timer at bottom of panel (time display + progress bar + SAFE/WAIT badge)

### Left Panel — Places (~180px wide, below Location panel, collapsible)

- Tab bar: Recent / Saved / Popular
- Scrollable list of locations
- Click to fly + set marker (or teleport if mode active)
- Delete button on hover
- "Clear History" at bottom of Recent tab

### Right Panel — Movement (~160px wide, fixed top-right below topbar)

- Panel title bar: "MOVEMENT" + collapse (X) button
- Speed segment control: Walk (5) / Bike (15) / Drive (40) + custom km/h input
- Route controls: Start / Pause / Resume / Stop / Clear
- Route mode: Once / Loop / Ping-pong dropdown + Randomize checkbox
- Route hint text ("Shift+click to add points")
- Joystick 3x3 grid (directional arrows + stop)
- Section divider
- Wander controls: radius input + Wander / Stop / Circular buttons
- GPX: Import / Export buttons
- Route history: expandable list of saved routes

### Bottom Center — Status Pills (fixed, centered)

- Cooldown badge: green "SAFE" or red pulsing "WAIT" with timer
- Current speed indicator
- Route progress (when active): `2.3 km | ETA 8m | 67%`
- Connection type pill (USB/WiFi)

### Panels on Demand

- **Multi-device picker:** Dropdown from device badge in topbar. Shows all devices from `/api/devices` with UDID + connection type badges. Click to switch.
- **Keyboard shortcuts:** `?` key opens centered overlay (only overlay exception). Reference card for all shortcuts.

### Panel Behavior

- Each panel remembers collapsed/expanded state in `localStorage`
- Fixed positions (not freely draggable) — keeps layout predictable
- All panels use `backdrop-filter: blur(20px)` glassmorphism
- Collapse/expand with smooth `max-height` CSS transitions
- When collapsed: only title bar visible (saves space)

---

## 3. Feature Implementations

### 3.1 Replace `prompt()` with Inline Forms

**Current:** `saveLocation()`, `saveProfile()`, `addSchedule()` all use `prompt()`.

**New:** Each triggers inline expansion within its parent panel:
- Save Location: Location panel grows, shows name input + category pills + Save/Cancel
- Save Profile: Movement panel grows with name input
- Add Schedule: Location panel shows name + time (HH:MM input) + day checkboxes

Pattern: panel height transitions smoothly via `max-height`. Escape or Cancel collapses. Focus traps within the expanded form.

### 3.2 Custom Animated Map Marker

**Current:** `L.circleMarker` with static blue fill.

**New:** `L.divIcon` with custom HTML:
- Inner dot: 12px, `background: #8B5CF6`, 2px white border
- Pulse ring: CSS `@keyframes` breathing animation (scale 1→1.8→1 over 2s)
- Glow: `box-shadow: 0 0 20px rgba(139,92,246,0.6), 0 0 40px rgba(139,92,246,0.2)`
- During movement: faint trail polyline (last 20 positions) with decreasing opacity

### 3.3 Live Position Tracking

**Current:** Route polling at 1s, no tracking during joystick/wander.

**New:**
- Poll `/api/location/current` every 500ms when any movement is active
- Marker position updates with CSS `transition: transform 0.4s ease` for smoothness
- "Follow mode" toggle in Movement panel — map auto-pans to keep marker centered
- Works for routes, joystick, and wander

### 3.4 Floating Panel System (CSS)

Complete CSS rewrite of layout:
- Remove `#sidebar` and all `.sidebar-section` styles
- New `.hud-panel` base class with glassmorphism
- `.hud-panel-left`, `.hud-panel-right` for positioning
- `.hud-panel.collapsed` shows only title bar
- `#map` becomes `position: fixed; top: var(--topbar-h); left: 0; right: 0; bottom: 0;`

### 3.5 Multi-Device Picker

**Backend:** `/api/devices` already exists and returns `[{udid, connection_types}]`.

**Frontend:**
- Click device badge in topbar → dropdown appears below
- Lists all devices with truncated UDID + connection badges (USB green, WiFi purple)
- Click device → calls `/api/device/connect` with selected preference
- Dropdown dismisses on selection or outside click

### 3.6 Distance/ETA Overlay

**No backend changes.** Client-side calculation:
- Route distance from `/api/route/start` response (`distance_km`)
- Current speed from speed selector
- ETA = remaining distance / speed
- Display in bottom status pill: `2.3 km | ETA 8m | 67%`
- Updates every route poll cycle (1s)

### 3.7 Keyboard Shortcuts Help Panel

**Trigger:** `?` key (when not in an input field)

**Content (centered overlay with purple border):**

| Key | Action |
|-----|--------|
| W/A/S/D or Arrows | Joystick movement |
| Shift + Click | Add route waypoint |
| T | Toggle teleport mode |
| Escape | Close active panel/form |
| ? | Show/hide this panel |
| +/- | Zoom in/out |

Dismiss: Escape, `?` again, or click outside.

### 3.8 Search Keyboard Navigation

**Current:** Click-only selection.

**New:**
- Arrow Up/Down moves highlight through results (`.search-item.highlighted` class with purple left border)
- Enter selects highlighted result (flies to location, teleports if mode active)
- Escape closes results dropdown
- Highlight follows mouse hover too (mouse and keyboard coexist)

### 3.9 Coordinate HUD on Map

- Fixed pill at bottom-right of map area
- Shows mouse cursor coordinates as you hover over map: `40.7580°N, 73.9855°W`
- Monospace, purple text, semi-transparent black background
- Updates via Leaflet `map.on('mousemove')` event
- Disappears when mouse leaves map

### 3.10 Animated Route Playback

**Current:** Route polyline drawn once, marker jumps between points.

**New:**
- Full route drawn as purple polyline (`#8B5CF6`, weight 3, opacity 0.6)
- Traveled portion redrawn on each poll: brighter purple (`#A78BFA`), weight 4, opacity 1.0, with glow shadow
- Marker slides smoothly along the path (CSS transition on position)
- Route waypoint markers are smaller neon dots (6px) with number labels

### 3.11 Route History

**New backend endpoints:**
- `GET /api/routes` — list saved routes
- `POST /api/routes` — save route `{name, waypoints, speed, mode, distance}`
- `DELETE /api/routes/<id>` — delete saved route

**Storage:** `routes.json` in `DATA_DIR` (same pattern as `saved_locations.json`).

**Frontend:**
- "Save Route" button appears in Movement panel after a route completes
- Route history list expandable in Movement panel
- Click to load waypoints onto map (same as GPX import flow)
- Delete on hover

### 3.12 Undo Last Teleport

**Client-side only.** No backend changes.
- Before each `/api/location/set` call, store `previousLocation = {lat, lon}`
- "Undo" button in Location panel (disabled when no previous location)
- Click calls `/api/location/set` with `previousLocation`
- Single-level undo (stores only the last position, not a stack)
- Undo button shows previous coords as tooltip on hover

---

## 4. Files Changed

### Frontend (primary changes)

| File | Changes |
|------|---------|
| `templates/index.html` | Remove sidebar HTML, add floating panel HTML, add multi-device dropdown, add keyboard shortcuts overlay, add coordinate HUD element |
| `static/css/style.css` | Full restyle — new color tokens, remove sidebar CSS, add `.hud-panel` system, new glow animations, updated light theme |
| `static/js/app.js` | Panel collapse/expand logic, inline form system, custom map marker, live tracking, search keyboard nav, keyboard shortcuts, route history UI, undo, coordinate HUD, multi-device picker |

### Backend (minimal changes)

| File | Changes |
|------|---------|
| `app.py` | Add 3 route history endpoints (`/api/routes`, `POST /api/routes`, `DELETE /api/routes/<id>`) |
| `location_service.py` | Add `get_routes()`, `save_route()`, `delete_route()` methods + `ROUTES_FILE` constant |

---

## 5. Migration Notes

- No database changes — all new data stored in JSON files (same pattern as existing)
- No new Python dependencies
- No breaking API changes — all existing endpoints remain identical
- `localStorage` keys for panel state won't conflict with existing keys
- Onboarding overlay is kept but restyled to match neon theme
- Light theme updated to match new color system
