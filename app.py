import threading
import time

import requests as http_requests
from flask import Flask, jsonify, request, render_template

from device_manager import DeviceManager
from location_service import LocationService
from tunnel_service import is_tunneld_running, ensure_tunnel


PORT = 8080

app = Flask(__name__)

# Global state — initialized by main() or main_app.py
device_mgr = None
loc_svc = None
_state_lock = threading.Lock()
_schedule_thread = None
_schedule_active = False

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
                        "udid": None, "model": None, "connection_type": None,
                        "error": "Tunnel not running"})
    return jsonify(device_mgr.get_device_info())


@app.route("/api/device/connections")
def api_device_connections():
    if device_mgr is None:
        return jsonify([])
    return jsonify(device_mgr.get_available_connections())


@app.route("/api/devices")
def api_devices_list():
    """List all unique devices visible to the tunnel."""
    if device_mgr is None:
        return jsonify([])
    return jsonify(device_mgr.get_all_devices())


@app.route("/api/device/switch", methods=["POST"])
def api_device_switch():
    if device_mgr is None:
        return jsonify({"error": "Not initialized"}), 503
    data = request.json or {}
    prefer_wifi = data.get("wifi", False)
    try:
        if loc_svc:
            loc_svc._stop_keepalive()
        info = device_mgr.reconnect(prefer_wifi=prefer_wifi)
        if loc_svc:
            loc_svc.simulator = device_mgr.simulator
            if loc_svc.current_location:
                loc_svc._start_keepalive()
        return jsonify({"status": "Switched", **info})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/device/connect", methods=["POST"])
def api_device_connect():
    global device_mgr, loc_svc

    data = request.json or {}
    prefer_wifi = data.get("wifi", False)

    if not is_tunneld_running():
        if not ensure_tunnel(timeout=30):
            return jsonify({"error": "Tunnel failed to start. Grant admin access when prompted."}), 503

    with _state_lock:
        if device_mgr is None:
            device_mgr = DeviceManager()

        if loc_svc:
            loc_svc._stop_keepalive()
            loc_svc.stop_route()

        try:
            if device_mgr.device_info.get("connected"):
                info = device_mgr.reconnect(prefer_wifi=prefer_wifi, retries=10)
            else:
                info = device_mgr.connect(prefer_wifi=prefer_wifi, retries=10)

            loc_svc = LocationService(device_mgr.simulator, device_mgr.bridge)
            _start_schedule_checker()
            return jsonify({"status": "Connected", **info})
        except Exception as e:
            return jsonify({"error": str(e)}), 500


@app.route("/api/device/auto-reconnect", methods=["POST"])
def api_auto_reconnect():
    if device_mgr is None:
        return jsonify({"error": "Not initialized"}), 503
    data = request.json or {}
    enabled = data.get("enabled", True)

    def on_reconnect(info):
        global loc_svc
        if device_mgr and device_mgr.simulator:
            loc_svc = LocationService(device_mgr.simulator, device_mgr.bridge)

    if enabled:
        return jsonify(device_mgr.enable_auto_reconnect(callback=on_reconnect))
    else:
        return jsonify(device_mgr.disable_auto_reconnect())


@app.route("/api/tunnel/status")
def api_tunnel_status():
    running = is_tunneld_running()
    return jsonify({"running": running})


# ── Default location ───────────────────────────────────────────

@app.route("/api/default-location")
def api_default_location():
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

    try:
        r = http_requests.get("https://ipwho.is/", timeout=3)
        data = r.json()
        if data.get("success") and "latitude" in data:
            return jsonify({"lat": data["latitude"], "lon": data["longitude"],
                            "city": data.get("city", ""), "country": data.get("country", "")})
    except Exception:
        pass

    try:
        r = http_requests.get("http://ip-api.com/json/?fields=lat,lon,city,country", timeout=2)
        data = r.json()
        if "lat" in data and "lon" in data:
            return jsonify({"lat": data["lat"], "lon": data["lon"],
                            "city": data.get("city", ""), "country": data.get("country", "")})
    except Exception:
        pass

    return jsonify({"lat": 40.7128, "lon": -74.006, "city": "New York", "country": "US"})


# ── Stealth / Anti-detection API ──────────────────────────────

_ip_cache = {"data": None, "ts": 0}


def _get_ip_location():
    """Get the user's real IP geolocation (cached 5 min). Returns dict or None."""
    global _ip_cache
    if _ip_cache["data"] and time.time() - _ip_cache["ts"] < 300:
        return _ip_cache["data"]

    result = None
    try:
        r = http_requests.get("https://ipinfo.io/json", timeout=3,
                              headers={"User-Agent": "iPhoneSpoofer/1.0"})
        data = r.json()
        loc = data.get("loc", "")
        if "," in loc:
            lat, lon = loc.split(",")
            result = {"lat": float(lat), "lon": float(lon),
                      "city": data.get("city", ""), "country": data.get("country", ""),
                      "timezone": data.get("timezone", "")}
    except Exception:
        pass

    if result is None:
        try:
            r = http_requests.get("https://ipwho.is/", timeout=3)
            data = r.json()
            if data.get("success") and "latitude" in data:
                result = {"lat": data["latitude"], "lon": data["longitude"],
                          "city": data.get("city", ""), "country": data.get("country_code", ""),
                          "timezone": data.get("timezone", {}).get("id", "")}
        except Exception:
            pass

    if result:
        _ip_cache = {"data": result, "ts": time.time()}
    return result


@app.route("/api/stealth/check")
def api_stealth_check():
    """Check for IP vs GPS mismatch and timezone warnings."""
    result = {"ip_mismatch": False, "ip_location": None,
              "spoof_location": None, "distance_km": None, "warnings": []}

    if loc_svc is None or loc_svc.get_current() is None:
        return jsonify(result)

    spoof = loc_svc.get_current()
    ip_loc = _get_ip_location()
    if ip_loc is None:
        return jsonify(result)

    result["ip_location"] = ip_loc
    result["spoof_location"] = spoof

    dist = LocationService._haversine(
        ip_loc["lat"], ip_loc["lon"], spoof["lat"], spoof["lon"]
    ) / 1000
    result["distance_km"] = round(dist, 1)

    # IP mismatch: >100 km apart
    if dist > 100:
        severity = "high" if dist > 500 else "medium"
        result["ip_mismatch"] = True
        result["warnings"].append({
            "type": "ip_mismatch",
            "severity": severity,
            "message": (f"Your IP is in {ip_loc.get('city', '?')}, "
                        f"{ip_loc.get('country', '?')} but GPS is "
                        f"{round(dist)} km away. Use a VPN to match."),
        })

    # Timezone: estimate UTC offset from longitude
    spoof_utc = round(spoof["lon"] / 15)
    ip_utc = round(ip_loc["lon"] / 15)
    if abs(spoof_utc - ip_utc) > 1:
        sign = "+" if spoof_utc >= 0 else ""
        result["warnings"].append({
            "type": "timezone_mismatch",
            "severity": "medium",
            "message": (f"Device timezone may not match spoofed location "
                        f"(~UTC{sign}{spoof_utc}). Change in iOS Settings "
                        f"> General > Date & Time."),
        })

    return jsonify(result)


# ── Location API ───────────────────────────────────────────────

@app.route("/api/location/set", methods=["POST"])
def api_set_location():
    err = _check_ready()
    if err:
        return err
    data = request.json or {}
    try:
        lat = float(data["lat"])
        lon = float(data["lon"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "lat and lon are required (numbers)"}), 400

    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return jsonify({"error": "Invalid coordinates"}), 400

    try:
        if loc_svc._route_active:
            loc_svc.stop_route()
        loc_svc.joystick_stop()
        loc_svc.stop_wander()
        result = loc_svc.set_location(lat, lon)
        loc_svc.add_to_history(lat, lon)
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


# ── Cooldown API ───────────────────────────────────────────────

@app.route("/api/cooldown")
def api_cooldown():
    if loc_svc is None:
        return jsonify({"active": False, "remaining_seconds": 0})
    return jsonify(loc_svc.get_cooldown())


# ── Joystick API ───────────────────────────────────────────────

@app.route("/api/joystick/move", methods=["POST"])
def api_joystick_move():
    err = _check_ready()
    if err:
        return err
    data = request.json or {}
    direction = data.get("direction", "n")
    speed = data.get("speed", 5)
    try:
        speed = float(speed)
    except (TypeError, ValueError):
        speed = 5
    try:
        result = loc_svc.joystick_start(direction, speed)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/joystick/stop", methods=["POST"])
def api_joystick_stop():
    err = _check_ready()
    if err:
        return err
    return jsonify(loc_svc.joystick_stop())


# ── Search API ────────────────────────────────────────────────

def _dedup_results(results):
    seen_names = set()
    seen_coords = []
    out = []
    for r in results:
        name_key = r["display_name"].lower().strip()
        if name_key in seen_names:
            continue
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
            "lat": coords[1], "lon": coords[0],
            "type": props.get("osm_value", props.get("type", "")),
        })
    return results


def _parse_nominatim(data):
    results = []
    for r in data:
        try:
            results.append({
                "display_name": r["display_name"],
                "lat": float(r["lat"]), "lon": float(r["lon"]),
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

    try:
        resp = http_requests.get(
            "https://photon.komoot.io/api/",
            params={"q": query, "limit": 15},
            headers=headers, timeout=5,
        )
        all_results.extend(_parse_photon(resp.json()))
    except Exception:
        pass

    try:
        resp = http_requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "json", "limit": 10, "addressdetails": 0},
            headers=headers, timeout=8,
        )
        all_results.extend(_parse_nominatim(resp.json()))
    except Exception:
        pass

    if not all_results:
        return jsonify([])

    return jsonify(_dedup_results(all_results)[:12])


# ── Route API ──────────────────────────────────────────────────

@app.route("/api/route/start", methods=["POST"])
def api_route_start():
    err = _check_ready()
    if err:
        return err
    data = request.json or {}
    waypoints = data.get("waypoints", [])
    speed = data.get("speed", 5)
    mode = data.get("mode", "once")
    randomize = data.get("randomize_speed", False)
    try:
        speed = float(speed)
    except (TypeError, ValueError):
        speed = 5
    try:
        result = loc_svc.start_route(waypoints, speed_kmh=speed, mode=mode, randomize_speed=randomize)
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
    return jsonify(loc_svc.stop_route())


@app.route("/api/route/pause", methods=["POST"])
def api_route_pause():
    err = _check_ready()
    if err:
        return err
    return jsonify(loc_svc.pause_route())


@app.route("/api/route/resume", methods=["POST"])
def api_route_resume():
    err = _check_ready()
    if err:
        return err
    return jsonify(loc_svc.resume_route())


@app.route("/api/route/status")
def api_route_status():
    if loc_svc is None:
        return jsonify({"error": "Not connected"}), 503
    status = loc_svc.get_route_status()
    if status is None:
        return jsonify({"error": "No route active"}), 404
    return jsonify(status)


@app.route("/api/route/circular", methods=["POST"])
def api_route_circular():
    err = _check_ready()
    if err:
        return err
    data = request.json or {}
    try:
        lat = float(data["lat"])
        lon = float(data["lon"])
        radius = float(data.get("radius", 200))
        points = int(data.get("points", 36))
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "lat, lon, and radius are required"}), 400

    waypoints = loc_svc.generate_circular_route(lat, lon, radius, points)
    return jsonify({"waypoints": waypoints, "count": len(waypoints)})


# ── Wander API ─────────────────────────────────────────────────

@app.route("/api/wander/start", methods=["POST"])
def api_wander_start():
    err = _check_ready()
    if err:
        return err
    data = request.json or {}
    try:
        lat = float(data["lat"])
        lon = float(data["lon"])
        radius = float(data.get("radius", 100))
        speed = float(data.get("speed", 5))
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "lat and lon are required"}), 400
    try:
        result = loc_svc.start_wander(lat, lon, radius, speed)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/wander/stop", methods=["POST"])
def api_wander_stop():
    err = _check_ready()
    if err:
        return err
    return jsonify(loc_svc.stop_wander())


@app.route("/api/wander/status")
def api_wander_status():
    if loc_svc is None:
        return jsonify({"active": False})
    return jsonify(loc_svc.get_wander_status())


# ── GPX API ────────────────────────────────────────────────────

@app.route("/api/gpx/import", methods=["POST"])
def api_gpx_import():
    err = _check_ready()
    if err:
        return err
    # Accept either file upload or raw body
    if request.files and "file" in request.files:
        content = request.files["file"].read().decode("utf-8")
    else:
        content = request.get_data(as_text=True)
    if not content:
        return jsonify({"error": "No GPX data provided"}), 400
    try:
        result = loc_svc.import_gpx(content)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Failed to parse GPX: {e}"}), 400


@app.route("/api/gpx/export")
def api_gpx_export():
    if loc_svc is None:
        return jsonify({"error": "Not connected"}), 503
    name = request.args.get("name", "iPhone Spoofer Route")
    gpx_str = loc_svc.export_gpx(name)
    return app.response_class(gpx_str, mimetype="application/gpx+xml",
                              headers={"Content-Disposition": f"attachment; filename=route.gpx"})


# ── Saved locations API ───────────────────────────────────────

@app.route("/api/saved")
def api_saved_list():
    if loc_svc is None:
        return jsonify([])
    category = request.args.get("category")
    locs = loc_svc.get_saved()
    if category:
        locs = [l for l in locs if l.get("category", "default") == category]
    return jsonify(locs)


@app.route("/api/saved", methods=["POST"])
def api_saved_add():
    if loc_svc is None:
        return jsonify({"error": "Not connected"}), 503
    data = request.json or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Name is required"}), 400
    try:
        lat = float(data["lat"])
        lon = float(data["lon"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "lat and lon are required"}), 400
    category = data.get("category", "default")
    result = loc_svc.save_location(name, lat, lon, category)
    return jsonify(result)


@app.route("/api/saved/<path:name>", methods=["DELETE"])
def api_saved_delete(name):
    if loc_svc is None:
        return jsonify({"error": "Not connected"}), 503
    return jsonify(loc_svc.delete_location(name))


@app.route("/api/saved/categories")
def api_saved_categories():
    if loc_svc is None:
        return jsonify([])
    return jsonify(loc_svc.get_categories())


# ── History API ────────────────────────────────────────────────

@app.route("/api/history")
def api_history():
    if loc_svc is None:
        return jsonify([])
    return jsonify(loc_svc.get_history())


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


# ── Profiles API ───────────────────────────────────────────────

@app.route("/api/profiles")
def api_profiles_list():
    if loc_svc is None:
        return jsonify([])
    return jsonify(loc_svc.get_profiles())


@app.route("/api/profiles", methods=["POST"])
def api_profiles_save():
    if loc_svc is None:
        return jsonify({"error": "Not connected"}), 503
    data = request.json or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Name is required"}), 400
    return jsonify(loc_svc.save_profile(name, data))


@app.route("/api/profiles/<path:name>/load", methods=["POST"])
def api_profiles_load(name):
    err = _check_ready()
    if err:
        return err
    try:
        return jsonify(loc_svc.load_profile(name))
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@app.route("/api/profiles/<path:name>", methods=["DELETE"])
def api_profiles_delete(name):
    if loc_svc is None:
        return jsonify({"error": "Not connected"}), 503
    return jsonify(loc_svc.delete_profile(name))


# ── Schedules API ──────────────────────────────────────────────

@app.route("/api/schedules")
def api_schedules_list():
    if loc_svc is None:
        return jsonify([])
    return jsonify(loc_svc.get_schedules())


@app.route("/api/schedules", methods=["POST"])
def api_schedules_create():
    if loc_svc is None:
        return jsonify({"error": "Not connected"}), 503
    data = request.json or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Name is required"}), 400
    try:
        lat = float(data["lat"])
        lon = float(data["lon"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "lat and lon are required"}), 400
    time_str = data.get("time", "")
    days = data.get("days", None)
    return jsonify(loc_svc.save_schedule(name, lat, lon, time_str, days))


@app.route("/api/schedules/<schedule_id>", methods=["DELETE"])
def api_schedules_delete(schedule_id):
    if loc_svc is None:
        return jsonify({"error": "Not connected"}), 503
    return jsonify(loc_svc.delete_schedule(schedule_id))


@app.route("/api/schedules/<schedule_id>/toggle", methods=["POST"])
def api_schedules_toggle(schedule_id):
    if loc_svc is None:
        return jsonify({"error": "Not connected"}), 503
    data = request.json or {}
    return jsonify(loc_svc.toggle_schedule(schedule_id, data.get("enabled", True)))


# ── Schedule checker ───────────────────────────────────────────

def _start_schedule_checker():
    global _schedule_thread, _schedule_active
    if _schedule_active:
        return
    _schedule_active = True
    _schedule_thread = threading.Thread(target=_schedule_loop, daemon=True)
    _schedule_thread.start()


def _schedule_loop():
    """Check schedules every 30 seconds."""
    last_check_minute = None
    while _schedule_active:
        if loc_svc:
            import datetime
            now = datetime.datetime.now()
            current_minute = now.strftime("%H:%M")
            if current_minute != last_check_minute:
                last_check_minute = current_minute
                try:
                    loc_svc.check_schedules()
                except Exception:
                    pass
        time.sleep(30)


# ── API docs ───────────────────────────────────────────────────

@app.route("/api")
def api_docs():
    """Simple API documentation."""
    endpoints = []
    for rule in app.url_map.iter_rules():
        if rule.rule.startswith("/api"):
            endpoints.append({
                "path": rule.rule,
                "methods": sorted(rule.methods - {"OPTIONS", "HEAD"}),
            })
    endpoints.sort(key=lambda e: e["path"])
    return jsonify({"endpoints": endpoints, "version": "1.5.0"})


# ── CLI Main (for start.sh usage) ─────────────────────────────

def main():
    global device_mgr, loc_svc

    print()
    print("=" * 50)
    print("  iPhone Location Spoofer")
    print("=" * 50)
    print()

    device_mgr = DeviceManager()

    print("[*] Looking for device...")
    try:
        info = device_mgr.connect(retries=5)
        print(f"    UDID: {info['udid']}")
        loc_svc = LocationService(device_mgr.simulator, device_mgr.bridge)
        _start_schedule_checker()
        print("[+] Device connected")
    except Exception:
        print("[*] No device found yet — connect from the UI")
        loc_svc = None

    print()
    print(f"[+] Ready! Open http://localhost:{PORT} in your browser")
    print("    Press Ctrl+C to stop")
    print()

    app.run(host="127.0.0.1", port=PORT, debug=False)


if __name__ == "__main__":
    main()
