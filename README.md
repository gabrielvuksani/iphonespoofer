# iPhone Location Spoofer

Spoof your iPhone's GPS location from your Mac or PC. Works with **all apps** — Find My, Life360, Pokemon Go, Maps, Uber, and everything else.

No jailbreak required. Uses Apple's own developer debugging interface via [pymobiledevice3](https://github.com/doronz88/pymobiledevice3).

## Features

- **Teleport mode** — Click the map to instantly move your GPS
- **Search** — Find any address or place name worldwide
- **Movement simulation** — Walk, bike, or drive along real roads
- **Paste coordinates** — Paste from clipboard or Google Maps URLs
- **Recent history** — Auto-tracked history of your last 15 locations
- **Save favorites** — Bookmark locations for quick access
- **Popular spots** — One-click presets for famous landmarks
- **Keep-alive** — Maintains spoofed location on iOS 18+
- **Onboarding** — First-launch guide for new users
- **Native app** — WebView window, no browser needed
- **Free** — No API keys, no subscriptions, no accounts

## Download

**macOS:** Download the `.dmg` from [Releases](../../releases), open it, and drag to Applications.

**Windows:** Download the `.zip` from [Releases](../../releases), extract, and run `iPhone Spoofer.exe`.

## Requirements

| | macOS | Windows |
|---|---|---|
| OS | 10.15+ (Catalina) | 10/11 |
| iPhone | iOS 17+ via USB | iOS 17+ via USB |
| Extra | — | iTunes installed |
| Setup | Developer Mode on iPhone | Developer Mode on iPhone |

## How It Works

1. Launch the app
2. Accept the admin/UAC prompt (required for the iOS tunnel)
3. Plug in your iPhone and accept "Trust This Computer"
4. Click the map to set your location — done

The app uses `pymobiledevice3` to communicate with your iPhone through Apple's developer debugging interface. When you set a simulated location, the entire iOS system believes it's at those coordinates — every app reads from the same CoreLocation framework.

## Development

```bash
# macOS
sudo ./start.sh

# Windows (run as Administrator)
start.bat
```

Build distributable:
```bash
# macOS → .app + .dmg
./build.sh

# Windows → .exe folder
build_windows.bat
```

## License

MIT
