import json
import math
import os
import platform
import random
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime

import requests as http_requests


# ── Cooldown table (Pokemon Go style) ─────────────────────────
# (distance_km, cooldown_seconds)
COOLDOWN_TABLE = [
    (1, 60), (5, 120), (10, 420), (25, 660), (30, 840),
    (65, 1320), (81, 1500), (100, 2100), (250, 2700),
    (500, 3600), (750, 4800), (1000, 7200),
]


def _get_data_dir():
    """Get the user-writable data directory (platform-aware)."""
    if platform.system() == "Windows":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        d = os.path.join(base, "iPhone Spoofer")
    else:
        d = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "iPhone Spoofer")
    os.makedirs(d, exist_ok=True)
    return d


DATA_DIR = _get_data_dir()
SAVED_FILE = os.path.join(DATA_DIR, "saved_locations.json")
PROFILES_FILE = os.path.join(DATA_DIR, "profiles.json")
SCHEDULES_FILE = os.path.join(DATA_DIR, "schedules.json")
ROUTES_FILE = os.path.join(DATA_DIR, "routes.json")


class LocationService:
    def __init__(self, simulator, bridge):
        self.simulator = simulator
        self.bridge = bridge
        self.current_location = None
        self._keepalive_active = False
        self._keepalive_thread = None
        self._keepalive_lock = threading.Lock()
        self._file_lock = threading.Lock()

        # Route state
        self._route_active = False
        self._route_paused = False
        self._route_thread = None
        self._route_progress = 0
        self._route_distance = 0
        self._route_duration = 0
        self._route_speed = 0
        self._route_coordinates = None
        self._route_mode = "once"       # "once", "loop", "pingpong"
        self._speed_randomize = False

        # Joystick state
        self._joystick_active = False
        self._joystick_thread = None
        self._joystick_direction = None
        self._joystick_speed = 5

        # Cooldown state
        self._last_teleport_time = None
        self._last_teleport_coords = None
        self._cooldown_end = 0

        # Random wander state
        self._wander_active = False
        self._wander_thread = None
        self._wander_center = None
        self._wander_radius = 0
        self._wander_speed = 5

    # ── Core ───────────────────────────────────────────────

    def _sim_set(self, lat, lon):
        self.bridge.run(self.simulator.set(lat, lon))

    def _sim_clear(self):
        self.bridge.run(self.simulator.clear())

    def set_location(self, lat, lon):
        # Update cooldown before moving
        if self.current_location:
            old = self.current_location
            dist = self._haversine(old["lat"], old["lon"], lat, lon) / 1000
            self._cooldown_end = time.time() + self._calculate_cooldown(dist)
        self._last_teleport_time = time.time()
        self._last_teleport_coords = {"lat": lat, "lon": lon}

        self._stop_keepalive()
        self._sim_set(lat, lon)
        self.current_location = {"lat": lat, "lon": lon}
        self._start_keepalive()
        return {"status": "Location set", "lat": lat, "lon": lon}

    def clear_location(self):
        self._stop_keepalive()
        self.current_location = None
        self.stop_route()
        self.joystick_stop()
        self.stop_wander()
        try:
            self._sim_clear()
        except Exception:
            pass
        return {"status": "Location cleared"}

    def get_current(self):
        return self.current_location

    # ── Cooldown ───────────────────────────────────────────

    @staticmethod
    def _calculate_cooldown(distance_km):
        """Return cooldown seconds for a given teleport distance."""
        if distance_km <= 0:
            return 0
        for max_dist, secs in COOLDOWN_TABLE:
            if distance_km <= max_dist:
                return secs
        return 7200  # 2 hours for 1000+ km

    def get_cooldown(self):
        """Return cooldown state."""
        now = time.time()
        remaining = max(0, self._cooldown_end - now)
        return {
            "active": remaining > 0,
            "remaining_seconds": round(remaining),
            "total_seconds": round(self._cooldown_end - (self._last_teleport_time or now)) if self._last_teleport_time else 0,
            "last_teleport": self._last_teleport_time,
        }

    # ── Keep-alive ─────────────────────────────────────────

    def _start_keepalive(self):
        with self._keepalive_lock:
            if self._keepalive_thread and self._keepalive_thread.is_alive():
                return
            self._keepalive_active = True
            self._keepalive_thread = threading.Thread(target=self._keepalive_loop, daemon=True)
            self._keepalive_thread.start()

    def _stop_keepalive(self):
        with self._keepalive_lock:
            self._keepalive_active = False
            t = self._keepalive_thread
            self._keepalive_thread = None
        if t and t.is_alive():
            t.join(timeout=3)

    def _keepalive_loop(self):
        fail_count = 0
        while self._keepalive_active:
            try:
                if self.current_location:
                    lat = self.current_location["lat"]
                    lon = self.current_location["lon"]
                    # Natural GPS jitter: 1-5m random drift per tick
                    jitter_m = random.uniform(1, 5)
                    angle = random.uniform(0, 2 * math.pi)
                    dlat = (jitter_m / 111320) * math.cos(angle)
                    dlon = (jitter_m / (111320 * max(math.cos(math.radians(lat)), 0.01))) * math.sin(angle)
                    self._sim_set(lat + dlat, lon + dlon)
                    fail_count = 0
            except Exception:
                fail_count += 1
                if fail_count >= 10:
                    print("[!] Keep-alive: device unresponsive after 10 failures, stopping")
                    break
            time.sleep(1.5)

    # ── Joystick / WASD movement ───────────────────────────

    # Direction vectors (lat_delta, lon_delta) normalized
    _DIRECTIONS = {
        "n":  (1, 0), "s":  (-1, 0), "e":  (0, 1), "w":  (0, -1),
        "ne": (1, 1), "nw": (1, -1), "se": (-1, 1), "sw": (-1, -1),
    }

    def joystick_start(self, direction, speed_kmh=5):
        """Start continuous movement in a direction."""
        if direction not in self._DIRECTIONS:
            raise ValueError(f"Invalid direction: {direction}")
        if not self.current_location:
            raise ValueError("No location set. Set a location first.")

        self._joystick_direction = direction
        self._joystick_speed = speed_kmh

        if not self._joystick_active:
            self._stop_keepalive()
            self._joystick_active = True
            self._joystick_thread = threading.Thread(target=self._joystick_loop, daemon=True)
            self._joystick_thread.start()

        return {"status": "Moving", "direction": direction, "speed": speed_kmh}

    def joystick_stop(self):
        """Stop joystick movement."""
        self._joystick_active = False
        if self._joystick_thread and self._joystick_thread.is_alive():
            self._joystick_thread.join(timeout=2)
        self._joystick_thread = None
        if self.current_location:
            self._start_keepalive()
        return {"status": "Stopped"}

    def _joystick_loop(self):
        TICK = 0.2  # 200ms per tick
        while self._joystick_active and self.current_location:
            d = self._DIRECTIONS.get(self._joystick_direction, (0, 0))
            lat = self.current_location["lat"]
            lon = self.current_location["lon"]

            # Convert speed to degrees per tick
            speed_deg = self._joystick_speed / (111.32 * 3600) * TICK
            # Normalize diagonal so it's not faster
            mag = math.sqrt(d[0] ** 2 + d[1] ** 2) or 1
            dlat = d[0] / mag * speed_deg
            # Longitude correction for latitude
            dlon = d[1] / mag * speed_deg / max(math.cos(math.radians(lat)), 0.01)

            new_lat = max(-90, min(90, lat + dlat))
            new_lon = max(-180, min(180, lon + dlon))

            try:
                self._sim_set(new_lat, new_lon)
                self.current_location = {"lat": new_lat, "lon": new_lon}
            except Exception:
                pass
            time.sleep(TICK)

    # ── Movement / Routes ──────────────────────────────────

    def start_route(self, waypoints, speed_kmh=5, mode="once", randomize_speed=False):
        if self._route_active:
            raise ValueError("A route is already running. Stop it first.")
        if len(waypoints) < 2:
            raise ValueError("Need at least 2 waypoints.")
        if mode not in ("once", "loop", "pingpong"):
            mode = "once"

        coords_str = ";".join(f"{wp['lng']},{wp['lat']}" for wp in waypoints)
        url = f"http://router.project-osrm.org/route/v1/driving/{coords_str}?geometries=geojson&overview=full"

        resp = http_requests.get(url, timeout=15)
        data = resp.json()

        if data.get("code") != "Ok" or not data.get("routes"):
            raise ValueError(f"Routing failed: {data.get('message', 'No route found')}")

        route = data["routes"][0]
        coordinates = route["geometry"]["coordinates"]
        self._route_distance = route["distance"]
        self._route_duration = route["duration"]
        self._route_coordinates = coordinates
        self._route_speed = speed_kmh
        self._route_mode = mode
        self._speed_randomize = randomize_speed
        self._route_active = True
        self._route_paused = False
        self._route_progress = 0
        self._stop_keepalive()
        self.joystick_stop()
        self.stop_wander()

        self._route_thread = threading.Thread(
            target=self._route_loop, args=(coordinates, speed_kmh), daemon=True
        )
        self._route_thread.start()

        return {
            "status": "Route started",
            "distance_km": round(self._route_distance / 1000, 2),
            "total_points": len(coordinates),
            "coordinates": coordinates,
            "mode": mode,
        }

    def _route_loop(self, coordinates, speed_kmh):
        speed_ms = speed_kmh / 3.6
        total = len(coordinates)
        iteration = 0
        reverse = False

        while self._route_active:
            seq = list(range(total))
            if reverse:
                seq = list(reversed(seq))

            for idx, i in enumerate(seq):
                if not self._route_active:
                    break

                # Handle pause
                while self._route_paused and self._route_active:
                    time.sleep(0.2)

                if not self._route_active:
                    break

                lng, lat = coordinates[i]
                try:
                    self._sim_set(lat, lng)
                except Exception:
                    pass
                self.current_location = {"lat": lat, "lon": lng}
                self._route_progress = ((idx + 1) / total) * 100

                if idx < total - 1:
                    next_i = seq[idx + 1]
                    nlng, nlat = coordinates[next_i]
                    dist = self._haversine(lat, lng, nlat, nlng)
                    sleep_time = max(0.1, min(dist / speed_ms if speed_ms > 0 else 0.5, 10.0))
                    if self._speed_randomize:
                        sleep_time *= random.uniform(0.8, 1.2)
                    time.sleep(sleep_time)

            iteration += 1

            if self._route_mode == "once":
                break
            elif self._route_mode == "pingpong":
                reverse = not reverse
            # "loop" just repeats with reverse=False

        if self._route_active:
            self._route_progress = 100
            self._route_active = False
            if self.current_location:
                self._start_keepalive()

    def pause_route(self):
        if not self._route_active:
            return {"status": "No route running"}
        self._route_paused = True
        return {"status": "Route paused"}

    def resume_route(self):
        if not self._route_active:
            return {"status": "No route running"}
        self._route_paused = False
        return {"status": "Route resumed"}

    def stop_route(self):
        self._route_active = False
        self._route_paused = False
        if self._route_thread and self._route_thread.is_alive():
            self._route_thread.join(timeout=5)
        self._route_thread = None
        if self.current_location and not (self._keepalive_thread and self._keepalive_thread.is_alive()):
            self._start_keepalive()
        return {"status": "Route stopped"}

    def get_route_status(self):
        if self._route_coordinates is None:
            return None
        return {
            "active": self._route_active,
            "paused": self._route_paused,
            "progress_pct": round(self._route_progress, 1),
            "distance_km": round(self._route_distance / 1000, 2),
            "duration_min": round(self._route_duration / 60, 1),
            "speed_kmh": self._route_speed,
            "mode": self._route_mode,
        }

    # ── Circular route generator ───────────────────────────

    def generate_circular_route(self, center_lat, center_lon, radius_m, points=36):
        """Generate waypoints in a circle. Returns list of {lat, lng}."""
        waypoints = []
        for i in range(points + 1):  # +1 to close the circle
            angle = 2 * math.pi * i / points
            dlat = (radius_m / 111320) * math.cos(angle)
            dlon = (radius_m / (111320 * math.cos(math.radians(center_lat)))) * math.sin(angle)
            waypoints.append({
                "lat": center_lat + dlat,
                "lng": center_lon + dlon,
            })
        return waypoints

    # ── Random wander ──────────────────────────────────────

    def start_wander(self, lat, lon, radius_m, speed_kmh=5):
        if self._wander_active:
            raise ValueError("Wander is already running.")
        if not self.current_location:
            self.set_location(lat, lon)

        self._wander_center = {"lat": lat, "lon": lon}
        self._wander_radius = radius_m
        self._wander_speed = speed_kmh
        self._wander_active = True
        self._stop_keepalive()
        self.joystick_stop()

        self._wander_thread = threading.Thread(target=self._wander_loop, daemon=True)
        self._wander_thread.start()

        return {"status": "Wandering", "center": self._wander_center, "radius": radius_m}

    def stop_wander(self):
        self._wander_active = False
        if self._wander_thread and self._wander_thread.is_alive():
            self._wander_thread.join(timeout=5)
        self._wander_thread = None
        if self.current_location:
            self._start_keepalive()
        return {"status": "Wander stopped"}

    def _wander_loop(self):
        speed_ms = self._wander_speed / 3.6
        while self._wander_active and self.current_location:
            # Pick a random point within radius
            angle = random.uniform(0, 2 * math.pi)
            dist = random.uniform(0, self._wander_radius)
            c = self._wander_center
            dlat = (dist / 111320) * math.cos(angle)
            dlon = (dist / (111320 * math.cos(math.radians(c["lat"])))) * math.sin(angle)
            target_lat = c["lat"] + dlat
            target_lon = c["lon"] + dlon

            # Walk to the target in small steps
            cur = self.current_location
            total_dist = self._haversine(cur["lat"], cur["lon"], target_lat, target_lon)
            steps = max(1, int(total_dist / (speed_ms * 0.3)))  # step every 300ms

            for s in range(steps):
                if not self._wander_active:
                    return
                frac = (s + 1) / steps
                nlat = cur["lat"] + (target_lat - cur["lat"]) * frac
                nlon = cur["lon"] + (target_lon - cur["lon"]) * frac
                try:
                    self._sim_set(nlat, nlon)
                    self.current_location = {"lat": nlat, "lon": nlon}
                except Exception:
                    pass
                time.sleep(0.3)

            # Pause briefly at the destination
            time.sleep(random.uniform(1, 4))

    def get_wander_status(self):
        return {
            "active": self._wander_active,
            "center": self._wander_center,
            "radius": self._wander_radius,
            "speed_kmh": self._wander_speed,
        }

    # ── GPX import / export ────────────────────────────────

    def import_gpx(self, gpx_content):
        """Parse GPX XML and return waypoints [{lat, lng, name?}]."""
        root = ET.fromstring(gpx_content)
        ns = {"gpx": "http://www.topografix.com/GPX/1/1"}
        waypoints = []

        # Try track points first
        for trkpt in root.findall(".//gpx:trkpt", ns) or root.findall(".//{http://www.topografix.com/GPX/1/0}trkpt"):
            lat = float(trkpt.get("lat"))
            lon = float(trkpt.get("lon"))
            waypoints.append({"lat": lat, "lng": lon})

        # Fallback: route points
        if not waypoints:
            for rtept in root.findall(".//gpx:rtept", ns) or root.findall(".//{http://www.topografix.com/GPX/1/0}rtept"):
                lat = float(rtept.get("lat"))
                lon = float(rtept.get("lon"))
                waypoints.append({"lat": lat, "lng": lon})

        # Fallback: waypoints (wpt)
        if not waypoints:
            for wpt in root.findall(".//gpx:wpt", ns) or root.findall(".//{http://www.topografix.com/GPX/1/0}wpt"):
                lat = float(wpt.get("lat"))
                lon = float(wpt.get("lon"))
                name_el = wpt.find("gpx:name", ns) or wpt.find("{http://www.topografix.com/GPX/1/0}name")
                name = name_el.text if name_el is not None else None
                waypoints.append({"lat": lat, "lng": lon, "name": name})

        # Try without namespace (common in simple GPX files)
        if not waypoints:
            for tag in ("trkpt", "rtept", "wpt"):
                for el in root.iter(tag):
                    lat = float(el.get("lat"))
                    lon = float(el.get("lon"))
                    waypoints.append({"lat": lat, "lng": lon})
                if waypoints:
                    break

        if not waypoints:
            raise ValueError("No waypoints found in GPX file")

        return {"waypoints": waypoints, "count": len(waypoints)}

    def export_gpx(self, name="iPhone Spoofer Route"):
        """Export current route coordinates or saved locations as GPX."""
        gpx = ET.Element("gpx", version="1.1", creator="iPhoneSpoofer",
                         xmlns="http://www.topografix.com/GPX/1/1")

        if self._route_coordinates:
            trk = ET.SubElement(gpx, "trk")
            ET.SubElement(trk, "name").text = name
            trkseg = ET.SubElement(trk, "trkseg")
            for lng, lat in self._route_coordinates:
                ET.SubElement(trkseg, "trkpt", lat=str(lat), lon=str(lng))
        elif self.current_location:
            wpt = ET.SubElement(gpx, "wpt",
                                lat=str(self.current_location["lat"]),
                                lon=str(self.current_location["lon"]))
            ET.SubElement(wpt, "name").text = "Current Location"

        return ET.tostring(gpx, encoding="unicode", xml_declaration=True)

    # ── Profiles ───────────────────────────────────────────

    def get_profiles(self):
        if not os.path.exists(PROFILES_FILE):
            return []
        try:
            with open(PROFILES_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []

    def save_profile(self, name, data=None):
        """Save current state as a named profile."""
        profile = {
            "name": name,
            "lat": data.get("lat") if data else (self.current_location or {}).get("lat"),
            "lon": data.get("lon") if data else (self.current_location or {}).get("lon"),
            "speed": data.get("speed", self._route_speed) if data else self._route_speed,
            "route_mode": data.get("route_mode", self._route_mode) if data else self._route_mode,
            "created": datetime.now().isoformat(),
        }
        with self._file_lock:
            profiles = self.get_profiles()
            # Update existing or append
            for i, p in enumerate(profiles):
                if p["name"] == name:
                    profiles[i] = profile
                    break
            else:
                profiles.append(profile)
            with open(PROFILES_FILE, "w") as f:
                json.dump(profiles, f, indent=2)
        return {"status": f"Profile '{name}' saved", "profile": profile}

    def load_profile(self, name):
        """Load a named profile and apply it."""
        profiles = self.get_profiles()
        for p in profiles:
            if p["name"] == name:
                if p.get("lat") is not None and p.get("lon") is not None:
                    self.set_location(p["lat"], p["lon"])
                return {"status": f"Profile '{name}' loaded", "profile": p}
        raise ValueError(f"Profile '{name}' not found")

    def delete_profile(self, name):
        with self._file_lock:
            profiles = [p for p in self.get_profiles() if p["name"] != name]
            with open(PROFILES_FILE, "w") as f:
                json.dump(profiles, f, indent=2)
        return {"status": f"Profile '{name}' deleted"}

    # ── Schedules ──────────────────────────────────────────

    def get_schedules(self):
        if not os.path.exists(SCHEDULES_FILE):
            return []
        try:
            with open(SCHEDULES_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []

    def save_schedule(self, name, lat, lon, time_str, days=None):
        """Save a scheduled location. time_str is 'HH:MM', days is list like ['mon','tue']."""
        schedule = {
            "id": str(int(time.time() * 1000)),
            "name": name,
            "lat": lat, "lon": lon,
            "time": time_str,
            "days": days or ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
            "enabled": True,
        }
        with self._file_lock:
            schedules = self.get_schedules()
            schedules.append(schedule)
            with open(SCHEDULES_FILE, "w") as f:
                json.dump(schedules, f, indent=2)
        return {"status": "Schedule created", "schedule": schedule}

    def delete_schedule(self, schedule_id):
        with self._file_lock:
            schedules = [s for s in self.get_schedules() if s["id"] != schedule_id]
            with open(SCHEDULES_FILE, "w") as f:
                json.dump(schedules, f, indent=2)
        return {"status": "Schedule deleted"}

    def toggle_schedule(self, schedule_id, enabled):
        with self._file_lock:
            schedules = self.get_schedules()
            for s in schedules:
                if s["id"] == schedule_id:
                    s["enabled"] = enabled
                    break
            with open(SCHEDULES_FILE, "w") as f:
                json.dump(schedules, f, indent=2)
        return {"status": "Schedule updated"}

    def check_schedules(self):
        """Check if any schedule should fire now. Called periodically."""
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        day_name = now.strftime("%a").lower()

        for s in self.get_schedules():
            if not s.get("enabled", True):
                continue
            if s["time"] == current_time and day_name in s.get("days", []):
                try:
                    self.set_location(s["lat"], s["lon"])
                    print(f"[*] Schedule fired: {s['name']} -> {s['lat']}, {s['lon']}")
                except Exception as e:
                    print(f"[!] Schedule error: {e}")

    # ── Saved locations ────────────────────────────────────

    def get_saved(self):
        if not os.path.exists(SAVED_FILE):
            return []
        try:
            with open(SAVED_FILE, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
        # Ensure all items have a category field
        for loc in data:
            if "category" not in loc:
                loc["category"] = "default"
        return data

    def save_location(self, name, lat, lon, category="default"):
        with self._file_lock:
            locations = self.get_saved()
            for loc in locations:
                if loc["name"] == name:
                    loc["lat"] = lat
                    loc["lon"] = lon
                    loc["category"] = category
                    break
            else:
                locations.append({"name": name, "lat": lat, "lon": lon, "category": category})
            with open(SAVED_FILE, "w") as f:
                json.dump(locations, f, indent=2)
        return {"status": f"Saved '{name}'"}

    def delete_location(self, name):
        with self._file_lock:
            locations = [loc for loc in self.get_saved() if loc["name"] != name]
            with open(SAVED_FILE, "w") as f:
                json.dump(locations, f, indent=2)
        return {"status": f"Deleted '{name}'"}

    def get_categories(self):
        """Return list of unique categories."""
        cats = set()
        for loc in self.get_saved():
            cats.add(loc.get("category", "default"))
        return sorted(cats)

    # ── History timeline ───────────────────────────────────

    def get_history(self):
        """Return location history from localStorage-compatible file."""
        hist_file = os.path.join(DATA_DIR, "history.json")
        if not os.path.exists(hist_file):
            return []
        try:
            with open(hist_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []

    def add_to_history(self, lat, lon):
        hist_file = os.path.join(DATA_DIR, "history.json")
        with self._file_lock:
            history = self.get_history()
            history.insert(0, {
                "lat": lat, "lon": lon,
                "ts": time.time(),
                "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            })
            history = history[:100]  # Keep last 100
            with open(hist_file, "w") as f:
                json.dump(history, f, indent=2)

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
            routes = routes[:50]
            with open(ROUTES_FILE, "w") as f:
                json.dump(routes, f, indent=2)
        return {"status": f"Route '{name}' saved", "route": route}

    def delete_route(self, route_id):
        with self._file_lock:
            routes = [r for r in self.get_routes() if r["id"] != route_id]
            with open(ROUTES_FILE, "w") as f:
                json.dump(routes, f, indent=2)
        return {"status": "Route deleted"}

    # ── Helpers ────────────────────────────────────────────

    @staticmethod
    def _haversine(lat1, lon1, lat2, lon2):
        R = 6371000
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dp = math.radians(lat2 - lat1)
        dl = math.radians(lon2 - lon1)
        a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
