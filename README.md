# iPhone Location Spoofer

Spoof your iPhone's GPS location from your Mac. Works with **all apps** — Find My, Life360, Pokemon Go, Maps, Uber, and everything else.

No jailbreak required. Uses Apple's own developer debugging interface via [pymobiledevice3](https://github.com/doronz88/pymobiledevice3).

## Features

- **Set any location** — Click the map or search any address
- **Movement simulation** — Walk, bike, or drive along real roads (via OSRM routing)
- **Save favorites** — Quick-switch between saved locations
- **Keep-alive** — Maintains spoofed location on iOS 18+ (re-sends every 1.5s)
- **Native macOS app** — WebView window, no browser needed
- **Dark mode UI** — Apple-style minimal design with CartoDB dark map tiles
- **Free** — No API keys, no subscriptions, no accounts

## Download

Download the latest `.dmg` from [Releases](../../releases), open it, and drag **iPhone Spoofer** to Applications.

## Requirements

- **macOS** 10.15+ (Catalina or later)
- **iPhone** connected via USB
- **Developer Mode** enabled on iPhone (Settings → Privacy & Security → Developer Mode)

## How It Works

1. Launch the app
2. Enter your Mac password when prompted (required for the iOS tunnel)
3. Plug in your iPhone and accept "Trust This Computer"
4. Click the map to set your location — done

The app uses `pymobiledevice3` to communicate with your iPhone through Apple's developer debugging interface. When you set a simulated location, the entire iOS system believes it's at those coordinates.

## Supported Devices

- All iPhones running iOS 17+ (iPhone 8 through iPhone 16 Pro Max)
- iOS 18+: Location resets when unplugged — keep your phone connected while spoofing

## Development

For development without building the .app:

```bash
# Terminal mode (requires sudo for the iOS tunnel)
sudo ./start.sh
```

To build the .app + DMG:

```bash
./build.sh
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Device communication | pymobiledevice3 |
| Backend | Python + Flask |
| Frontend | Leaflet.js + CartoDB tiles |
| Search | Photon (Komoot) + Nominatim |
| Routing | OSRM |
| Native window | pywebview |
| Packaging | PyInstaller |

## License

MIT
