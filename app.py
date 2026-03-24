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
    """Return approximate location via IP geolocation. Tries multiple providers."""
    # Provider 1: ipinfo.io (most reliable, works on most networks)
    try:
        r = http_requests.get("https://ipinfo.io/json", timeout=3,
                              headers={"User-Agent": "iPhoneSpoofer/1.0"})
        data = r.json()
        loc = data.get("loc", "")
        if "," in loc:
            lat, lon = loc.split(",")
            return jsonify({"lat": float(lat), "lon": float(lon),
                            "city": data.get("city", ""), "country": data.get("country", "")})
    except Exception:
        pass

    # Provider 2: ipwho.is
    try:
        r = http_requests.get("https://ipwho.is/", timeout=3)
        data = r.json()
        if data.get("success") and "latitude" in data:
            return jsonify({"lat": data["latitude"], "lon": data["longitude"],
                            "city": data.get("city", ""), "country": data.get("country", "")})
    except Exception:
        pass

    # Provider 3: ip-api.com (HTTP only, blocked on some networks)
    try:
        r = http_requests.get("http://ip-api.com/json/?fields=lat,lon,city,country", timeout=2)
        data = r.json()
        if "lat" in data and "lon" in data:
            return jsonify(data)
    except Exception:
        pass

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

def _dedup_results(results):
    """Remove duplicate locations. Two results are duplicates if they have
    the same display name (case-insensitive) or are within ~200m of each other."""
    seen_names = set()
    seen_coords = []
    out = []
    for r in results:
        name_key = r["display_name"].lower().strip()
        if name_key in seen_names:
            continue
        # Check coordinate proximity (0.002 deg ≈ 200m)
        lat, lon = r["lat"], r["lon"]
        too_close = False
        for slat, slon in seen_coords:
            if abs(lat - slat) < 0.002 and abs(lon - slon) < 0.002:
                too_close = True
                break
        if too_close:
            continue
        seen_names.add(name_key)
        seen_coords.append((lat, lon))
        out.append(r)
    return out


def _parse_photon(data):
    """Parse Photon GeoJSON response into our result format."""
    results = []
    for f in data.get("features", []):
        props = f.get("properties", {})
        coords = f.get("geometry", {}).get("coordinates", [])
        if len(coords) < 2:
            continue
        name = props.get("name", "")
        if not name:
            continue
        parts = [name]
        for key in ("street", "city", "state", "country"):
            val = props.get(key)
            if val and val != name:
                parts.append(val)
        results.append({
            "display_name": ", ".join(parts),
            "lat": coords[1],
            "lon": coords[0],
            "type": props.get("osm_value", props.get("type", "")),
        })
    return results


def _parse_nominatim(data):
    """Parse Nominatim JSON response into our result format."""
    results = []
    for r in data:
        try:
            results.append({
                "display_name": r["display_name"],
                "lat": float(r["lat"]),
                "lon": float(r["lon"]),
                "type": r.get("type", ""),
            })
        except (KeyError, ValueError):
            continue
    return results


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

    all_results = []
    headers = {"User-Agent": "iPhoneSpoofer/1.0"}

    # Query Photon (fast, good autocomplete, up to 15 results)
    try:
        resp = http_requests.get(
            "https://photon.komoot.io/api/",
            params={"q": query, "limit": 15},
            headers=headers,
            timeout=5,
        )
        all_results.extend(_parse_photon(resp.json()))
    except Exception:
        pass

    # Query Nominatim (different ranking, catches things Photon misses)
    try:
        resp = http_requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "json", "limit": 10, "addressdetails": 0},
            headers=headers,
            timeout=8,
        )
        all_results.extend(_parse_nominatim(resp.json()))
    except Exception:
        pass

    if not all_results:
        return jsonify([])

    # Deduplicate and return up to 12 results
    return jsonify(_dedup_results(all_results)[:12])


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
