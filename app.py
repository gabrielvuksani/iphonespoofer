import time
import sys

import requests as http_requests
from flask import Flask, jsonify, request, render_template

from device_manager import DeviceManager
from location_service import LocationService


PORT = 8080

app = Flask(__name__)

# Global state — initialized by main() or main_app.py
device_mgr = None
loc_svc = None

# Rate limit for search
_last_search_time = 0


def _check_ready():
    """Return error response if device/service not ready, else None."""
    if device_mgr is None:
        return jsonify({"error": "Tunnel not connected. Ensure iPhone is plugged in and restart the app."}), 503
    if loc_svc is None:
        return jsonify({"error": "No device connected. Plug in your iPhone and restart."}), 503
    return None


# ── Pages ──────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ── Device API ─────────────────────────────────────────────────

@app.route("/api/device")
def api_device():
    if device_mgr is None:
        return jsonify({"connected": False, "name": None, "ios_version": None,
                        "udid": None, "model": None, "error": "Tunnel not running"})
    return jsonify(device_mgr.get_device_info())


# ── Default location (IP geolocation for initial map center) ──

@app.route("/api/default-location")
def api_default_location():
    """Return approximate location based on IP for initial map centering."""
    try:
        r = http_requests.get("http://ip-api.com/json/?fields=lat,lon,city,country", timeout=3)
        data = r.json()
        if "lat" in data and "lon" in data:
            return jsonify(data)
    except Exception:
        pass
    # Fallback: New York
    return jsonify({"lat": 40.7128, "lon": -74.006, "city": "New York", "country": "US"})


# ── Location API ───────────────────────────────────────────────

@app.route("/api/location/set", methods=["POST"])
def api_set_location():
    err = _check_ready()
    if err:
        return err
    data = request.json
    try:
        lat = float(data["lat"])
        lon = float(data["lon"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "lat and lon are required (numbers)"}), 400

    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return jsonify({"error": "Invalid coordinates"}), 400

    try:
        result = loc_svc.set_location(lat, lon)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/location/clear", methods=["POST"])
def api_clear_location():
    err = _check_ready()
    if err:
        return err
    try:
        result = loc_svc.clear_location()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/location/current")
def api_current_location():
    if loc_svc is None:
        return jsonify({"error": "Not connected"}), 503
    loc = loc_svc.get_current()
    if loc is None:
        return jsonify({"error": "No location set"}), 404
    return jsonify(loc)


# ── Search API ────────────────────────────────────────────────

@app.route("/api/search")
def api_search():
    global _last_search_time
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify([])

    now = time.time()
    wait = 0.3 - (now - _last_search_time)
    if wait > 0:
        time.sleep(wait)
    _last_search_time = time.time()

    # Photon (fast, great autocomplete) → Nominatim fallback
    try:
        resp = http_requests.get(
            "https://photon.komoot.io/api/",
            params={"q": query, "limit": 6},
            headers={"User-Agent": "iPhoneSpoofer/1.0"},
            timeout=5,
        )
        data = resp.json()
        results = []
        for f in data.get("features", []):
            props = f.get("properties", {})
            coords = f.get("geometry", {}).get("coordinates", [])
            if len(coords) < 2:
                continue
            parts = [props.get("name", "")]
            for key in ("city", "state", "country"):
                if props.get(key):
                    parts.append(props[key])
            results.append({
                "display_name": ", ".join(p for p in parts if p),
                "lat": coords[1],
                "lon": coords[0],
                "type": props.get("osm_value", ""),
            })
        if results:
            return jsonify(results)
    except Exception:
        pass

    try:
        resp = http_requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "json", "limit": 6},
            headers={"User-Agent": "iPhoneSpoofer/1.0"},
            timeout=10,
        )
        return jsonify([
            {"display_name": r["display_name"], "lat": float(r["lat"]),
             "lon": float(r["lon"]), "type": r.get("type", "")}
            for r in resp.json()
        ])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Route API ──────────────────────────────────────────────────

@app.route("/api/route/start", methods=["POST"])
def api_route_start():
    err = _check_ready()
    if err:
        return err
    data = request.json
    waypoints = data.get("waypoints", [])
    speed = data.get("speed", 5)
    try:
        speed = float(speed)
    except (TypeError, ValueError):
        speed = 5
    try:
        result = loc_svc.start_route(waypoints, speed_kmh=speed)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/route/stop", methods=["POST"])
def api_route_stop():
    err = _check_ready()
    if err:
        return err
    result = loc_svc.stop_route()
    return jsonify(result)


@app.route("/api/route/status")
def api_route_status():
    if loc_svc is None:
        return jsonify({"error": "Not connected"}), 503
    status = loc_svc.get_route_status()
    if status is None:
        return jsonify({"error": "No route active"}), 404
    return jsonify(status)


# ── Saved locations API ───────────────────────────────────────

@app.route("/api/saved")
def api_saved_list():
    if loc_svc is None:
        return jsonify([])
    return jsonify(loc_svc.get_saved())


@app.route("/api/saved", methods=["POST"])
def api_saved_add():
    if loc_svc is None:
        return jsonify({"error": "Not connected"}), 503
    data = request.json
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Name is required"}), 400
    try:
        lat = float(data["lat"])
        lon = float(data["lon"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "lat and lon are required"}), 400
    result = loc_svc.save_location(name, lat, lon)
    return jsonify(result)


@app.route("/api/saved/<name>", methods=["DELETE"])
def api_saved_delete(name):
    if loc_svc is None:
        return jsonify({"error": "Not connected"}), 503
    result = loc_svc.delete_location(name)
    return jsonify(result)


# ── CLI Main (for start.sh usage) ─────────────────────────────

def main():
    global device_mgr, loc_svc

    print()
    print("=" * 50)
    print("  iPhone Location Spoofer")
    print("=" * 50)
    print()

    device_mgr = DeviceManager()

    print("[1/2] Connecting to device...")
    info = device_mgr.connect()
    print(f"      UDID:  {info['udid']}")

    print("[2/2] Starting location service...")
    loc_svc = LocationService(device_mgr.simulator, device_mgr.bridge)
    print()
    print(f"[+] Ready! Open http://localhost:{PORT} in your browser")
    print("    Press Ctrl+C to stop")
    print()

    app.run(host="0.0.0.0", port=PORT, debug=False)


if __name__ == "__main__":
    main()
