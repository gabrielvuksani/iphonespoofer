"""iPhone Location Spoofer — App Entry Point.

Handles two modes:
  --tunneld   : Run tunneld server (launched as root subprocess via osascript)
  (default)   : Launch Flask backend + native WebView window
"""

import sys
import os
import threading
import time
import socket

# Handle PyInstaller frozen paths
if getattr(sys, "frozen", False):
    _base = sys._MEIPASS
    os.environ.setdefault("FLASK_APP_ROOT", _base)
else:
    _base = os.path.dirname(os.path.abspath(__file__))

# ── Tunneld mode ──────────────────────────────────────────────

if "--tunneld" in sys.argv:
    from tunnel_service import run_tunneld_directly
    run_tunneld_directly()
    sys.exit(0)

# ── Normal app mode ───────────────────────────────────────────

from app import app, PORT
from tunnel_service import ensure_tunnel
from device_manager import DeviceManager
from location_service import LocationService

import app as app_module


def start_backend():
    """Initialize tunnel, optional device connection, and Flask server."""
    # Step 1: Tunnel
    print("[1/2] Setting up tunnel...")
    ensure_tunnel(timeout=30)

    # Step 2: Create device manager, try quick auto-connect
    device_mgr = DeviceManager()
    app_module.device_mgr = device_mgr
    app_module.loc_svc = None

    print("[2/2] Looking for device...")
    try:
        device_mgr.connect(retries=3)
        app_module.loc_svc = LocationService(device_mgr.simulator, device_mgr.bridge)
        print("[+] Device connected")
    except Exception:
        print("[*] No device yet — connect from the UI")

    app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False)


def wait_for_server(port, timeout=30):
    """Block until Flask is accepting connections."""
    for _ in range(timeout * 2):
        try:
            s = socket.create_connection(("127.0.0.1", port), timeout=0.5)
            s.close()
            return True
        except (ConnectionRefusedError, OSError):
            time.sleep(0.5)
    return False


def main():
    print("=" * 44)
    print("  iPhone Location Spoofer")
    print("=" * 44)

    # Start Flask in background
    server = threading.Thread(target=start_backend, daemon=True)
    server.start()

    if not wait_for_server(PORT):
        print("[!] Server failed to start")
        return

    # Try native WebView window, fall back to browser
    try:
        import webview
        webview.create_window(
            "iPhone Spoofer",
            f"http://127.0.0.1:{PORT}",
            width=1280,
            height=800,
            min_size=(900, 600),
            background_color="#0a0a0f",
            text_select=False,
        )
        webview.start()
    except Exception:
        import webbrowser
        print(f"[*] Opening http://localhost:{PORT}")
        webbrowser.open(f"http://localhost:{PORT}")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
