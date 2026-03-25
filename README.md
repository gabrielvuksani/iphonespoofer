<p align="center">
  <img src="icon.svg" width="128" height="128" alt="iPhone Spoofer icon" />
</p>

<h1 align="center">iPhone Location Spoofer</h1>

<p align="center">
  <strong>Change your iPhone's GPS location from your Mac or PC.</strong><br>
  Works with <em>all</em> apps — Find My, Life360, Pokemon Go, Maps, Uber, and everything else.<br>
  No jailbreak. No paid tools. No API keys.
</p>

<p align="center">
  <a href="../../releases/latest"><img src="https://img.shields.io/github/v/release/gabrielvuksani/iphonespoofer?style=flat-square&color=8B5CF6" alt="Release" /></a>
  <img src="https://img.shields.io/badge/platform-macOS%20%7C%20Windows-333?style=flat-square" alt="Platform" />
  <img src="https://img.shields.io/badge/cost-%240-39FF14?style=flat-square" alt="Free" />
  <img src="https://img.shields.io/badge/license-MIT-999?style=flat-square" alt="License" />
</p>

---

## How It Works

Your iPhone has a built-in developer feature that lets Xcode simulate GPS locations for app testing. This app uses [pymobiledevice3](https://github.com/doronz88/pymobiledevice3) — a proven open-source library — to access that same interface over USB or WiFi. When you set a simulated location, the **entire iOS system** believes it's at those coordinates. Every app reads from the same CoreLocation framework, so Find My, Life360, Pokemon Go, and all other apps see the spoofed position.

**No jailbreak, no sideloading, no modifications to your iPhone.** Just plug in, click, and go.

## Features

### Core

| Feature | Description |
|---------|-------------|
| **Click to spoof** | Click anywhere on the map to set your iPhone's GPS location |
| **Teleport mode** | Toggle to instantly move GPS with a single click — no confirm needed |
| **Search** | Find any address, city, or landmark worldwide with keyboard navigation |
| **Movement simulation** | Walk, bike, or drive along real roads at realistic speeds via OSRM routing |
| **Joystick** | WASD / arrow key controls for real-time directional movement |
| **Wander mode** | Random natural movement within a configurable radius |
| **Paste coordinates** | Paste lat/lon or Google Maps URLs directly from clipboard |
| **Undo teleport** | One-click undo to return to your previous location |
| **Keep-alive** | iOS 18+ location maintained automatically while phone stays connected |

### Organization

| Feature | Description |
|---------|-------------|
| **Saved locations** | Bookmark favorites with categories (Favorite, Work, Gaming) |
| **Recent history** | Auto-tracked history of your last 15 locations |
| **Popular spots** | Pre-loaded landmarks — Times Square, Eiffel Tower, Tokyo, and more |
| **Route history** | Save, name, and replay routes you've created |
| **Profiles** | Save and load full configuration presets (location, speed, route mode) |
| **Schedules** | Auto-teleport to locations at specific times and days of the week |
| **GPX import/export** | Import routes from GPX files or export your own |

### Interface

| Feature | Description |
|---------|-------------|
| **Neon cyberpunk HUD** | Floating glassmorphism panels over a full-screen map — no sidebar |
| **Animated map marker** | Pulsing neon purple marker with glow effects |
| **Live tracking** | Marker updates in real-time (500ms) during movement with optional follow mode |
| **Status bar** | Bottom-center pills showing cooldown, speed, route progress, and connection |
| **Coordinate HUD** | Hover over the map to see cursor coordinates in real-time |
| **Keyboard shortcuts** | Press `?` to see all shortcuts — `T` for teleport, WASD for joystick, and more |
| **Cooldown timer** | Pokemon Go-style cooldown based on teleport distance with SAFE/WAIT indicator |
| **Multi-device support** | Click the device badge to switch between multiple connected iPhones |
| **Dark + light theme** | Neon cyberpunk dark theme with a matching purple light mode |
| **Native window** | Runs as a native app window via pywebview — no browser tab |
| **Guided setup** | Step-by-step onboarding covers Developer Mode, USB trust, and usage |

## Download

| Platform | Download | Requirements |
|----------|----------|-------------|
| **macOS** | [Download .dmg](../../releases/latest) | macOS 10.15+ |
| **Windows** | [Download .zip](../../releases/latest) | Windows 10/11 + [iTunes](https://www.apple.com/itunes/) |

**iPhone requirements:** iOS 17 or later, connected via USB or WiFi, [Developer Mode](#enable-developer-mode) enabled.

## Quick Start

### 1. Install the app
- **macOS:** Open the `.dmg`, drag **iPhone Spoofer** to Applications
- **Windows:** Extract the `.zip`, run `iPhone Spoofer.exe`

### 2. Prepare your iPhone

<details>
<summary><strong>Enable Developer Mode</strong> (one-time setup)</summary>

1. Open **Settings** on your iPhone
2. Go to **Privacy & Security**
3. Scroll to the bottom and tap **Developer Mode**
4. Toggle it **ON**
5. Your iPhone will ask to restart — tap **Restart**
6. After reboot, confirm by tapping **Turn On**

> **Don't see Developer Mode?** It only appears on iOS 16+. Make sure your iPhone is updated.
</details>

<details>
<summary><strong>Trust your computer</strong></summary>

1. Connect your iPhone to your Mac/PC via **USB cable**
2. **Unlock** your iPhone
3. A dialog will appear: **"Trust This Computer?"** — tap **Trust**
4. Enter your iPhone **passcode** to confirm

> **No dialog?** Try unplugging and replugging the cable. If it still doesn't appear, go to Settings > General > Transfer or Reset > Reset Location & Privacy on your iPhone, then reconnect.
</details>

### 3. Use the app
1. Launch **iPhone Spoofer**
2. Accept the admin prompt (needed for the iOS tunnel)
3. Click the map to place a marker, then click **Warp**
4. Or enable **Teleport mode** in the top bar for instant one-click spoofing

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `W` `A` `S` `D` or Arrows | Joystick movement |
| `Shift` + Click | Add route waypoint |
| `T` | Toggle teleport mode |
| `Escape` | Close active panel or form |
| `?` | Show / hide shortcuts panel |
| `+` / `-` | Zoom in / out |

### Resetting
Click **Reset** in the Location panel to return to your real GPS. On iOS 18+, simply unplugging the cable also resets.

## Supported Devices

| iPhone | iOS | Notes |
|--------|-----|-------|
| iPhone 8 – iPhone 16 Pro Max | iOS 17+ | Full support via USB and WiFi |
| iOS 18+ | iOS 18+ | Location resets when USB is disconnected — keep phone plugged in |
| iOS 16 and below | — | Not supported (Developer Mode required) |

## Development

For contributors or those who prefer the terminal:

```bash
# macOS — run in dev mode
sudo ./start.sh

# Windows — run in dev mode (as Administrator)
start.bat
```

### Building from source

```bash
# macOS → .app + .dmg
./build.sh

# Windows → .exe folder
build_windows.bat
```

### Tech stack

| Layer | Technology |
|-------|-----------|
| Device communication | [pymobiledevice3](https://github.com/doronz88/pymobiledevice3) (pure Python, v4.0+) |
| Backend | Python 3 + [Flask](https://flask.palletsprojects.com/) (44 API endpoints) |
| Map | [Leaflet.js](https://leafletjs.com/) + [CartoDB](https://carto.com/basemaps/) tiles (dark + light) |
| Search | [Photon](https://photon.komoot.io/) + [Nominatim](https://nominatim.org/) (free, no API key) |
| Routing | [OSRM](http://project-osrm.org/) (free, no API key) |
| Native window | [pywebview](https://pywebview.flowrl.com/) |
| Packaging | [PyInstaller](https://pyinstaller.org/) |

### Project structure

```
├── app.py                 Flask API server (44 endpoints)
├── device_manager.py      iOS device connection via DVT/RSD + auto-reconnect
├── location_service.py    GPS spoofing, keep-alive, movement, routes, profiles, schedules
├── tunnel_service.py      Cross-platform tunnel management (macOS + Windows)
├── main_app.py            App entry point (WebView + Flask)
├── templates/index.html   Floating HUD panel layout
├── static/css/style.css   Neon cyberpunk theme + light mode
├── static/js/app.js       Map, panels, search, controls, inline forms, tracking
├── build.sh               macOS build → .app + .dmg
├── build_windows.bat      Windows build → .exe
├── start.sh               macOS dev mode launcher
└── start.bat              Windows dev mode launcher
```

### Data storage

All user data is stored as JSON files in:
- **macOS:** `~/Library/Application Support/iPhone Spoofer/`
- **Windows:** `%APPDATA%/iPhone Spoofer/`

Files: `saved_locations.json`, `profiles.json`, `schedules.json`, `routes.json`, `history.json`

## FAQ

<details>
<summary><strong>Is this safe? Will it damage my iPhone?</strong></summary>

No. This uses Apple's own built-in developer debugging interface — the same one Xcode uses. No modifications are made to your iPhone. To stop spoofing, just click Reset or unplug your phone.
</details>

<details>
<summary><strong>Will I get banned from Pokemon Go?</strong></summary>

Pokemon Go has anti-cheat detection. To minimize risk: use movement simulation at walking speed (5 km/h), don't teleport between distant locations quickly, and wait out the cooldown timer before taking in-game actions. The app includes a built-in Pokemon Go-style cooldown timer that shows you when it's safe.
</details>

<details>
<summary><strong>Why does the app need my Mac password?</strong></summary>

The iOS developer tunnel requires root/admin access to create a network interface for communicating with your iPhone. This is a one-time prompt per session — the app does not store your password.
</details>

<details>
<summary><strong>My location keeps resetting (iOS 18+)</strong></summary>

Apple changed iOS 18 so that simulated locations reset when USB is disconnected. Keep your phone plugged in while spoofing. The app's keep-alive feature re-sends coordinates every 1.5 seconds to maintain the position.
</details>

<details>
<summary><strong>The app says "No device connected"</strong></summary>

1. Make sure your iPhone is connected via USB
2. Unlock your iPhone and check for a "Trust This Computer?" dialog
3. Verify Developer Mode is enabled (Settings > Privacy & Security > Developer Mode)
4. Try unplugging and replugging the cable
5. Click **Connect USB** or **Connect WiFi** in the Location panel
6. Restart the app
</details>

<details>
<summary><strong>Can I use WiFi instead of USB?</strong></summary>

Yes. Connect via USB first to establish trust, then click the device badge in the top bar and select a WiFi connection. Your iPhone must be on the same network as your computer. WiFi mode lets you unplug the cable while spoofing.
</details>

<details>
<summary><strong>Can I spoof multiple iPhones at once?</strong></summary>

The app detects all connected devices. Click the device badge in the top bar to see available iPhones and switch between them. Each device can be connected via USB or WiFi independently.
</details>

## Changelog

| Version | Highlights |
|---------|-----------|
| **v1.4.0** | Neon cyberpunk UI, floating HUD panels, 12 new features (route history, undo, live tracking, keyboard shortcuts, multi-device picker, inline forms, coordinate HUD, search navigation, animated routes) |
| **v1.3.0** | Fix connection flow, WiFi/USB connect from UI, Python 3.13 support |
| **v1.2.0** | WiFi mode, persistence tips |
| **v1.1.0** | App icon, multi-page onboarding |
| **v1.0.0** | Initial release — click to spoof, teleport mode, search, movement simulation, dark UI |

## License

MIT — free for personal and commercial use.
