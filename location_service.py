import json
import math
import os
import threading
import time

import requests as http_requests


def _get_data_dir():
    """Get the user-writable data directory."""
    d = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "iPhone Spoofer")
    os.makedirs(d, exist_ok=True)
    return d


SAVED_FILE = os.path.join(_get_data_dir(), "saved_locations.json")


class LocationService:
    def __init__(self, simulator, bridge):
        self.simulator = simulator
        self.bridge = bridge
        self.current_location = None
        self._keepalive_active = False
        self._keepalive_thread = None
        self._route_active = False
        self._route_thread = None
        self._route_progress = 0
        self._route_distance = 0
        self._route_duration = 0
        self._route_speed = 0
        self._route_coordinates = None

    # ── Core ───────────────────────────────────────────────

    def _sim_set(self, lat, lon):
        self.bridge.run(self.simulator.set(lat, lon))

    def _sim_clear(self):
        self.bridge.run(self.simulator.clear())

    def set_location(self, lat, lon):
        self._stop_keepalive()
        self._sim_set(lat, lon)
        self.current_location = {"lat": lat, "lon": lon}
        self._start_keepalive()
        return {"status": "Location set", "lat": lat, "lon": lon}

    def clear_location(self):
        self._stop_keepalive()
        self.stop_route()
        try:
            self._sim_clear()
        except Exception:
            pass
        self.current_location = None
        return {"status": "Location cleared"}

    def get_current(self):
        return self.current_location

    # ── Keep-alive ─────────────────────────────────────────

    def _start_keepalive(self):
        self._keepalive_active = True
        self._keepalive_thread = threading.Thread(target=self._keepalive_loop, daemon=True)
        self._keepalive_thread.start()

    def _stop_keepalive(self):
        self._keepalive_active = False
        if self._keepalive_thread and self._keepalive_thread.is_alive():
            self._keepalive_thread.join(timeout=3)
        self._keepalive_thread = None

    def _keepalive_loop(self):
        while self._keepalive_active:
            try:
                if self.current_location:
                    self._sim_set(self.current_location["lat"], self.current_location["lon"])
            except Exception:
                pass
            time.sleep(1.5)

    # ── Movement ───────────────────────────────────────────

    def start_route(self, waypoints, speed_kmh=5):
        if self._route_active:
            raise ValueError("A route is already running. Stop it first.")
        if len(waypoints) < 2:
            raise ValueError("Need at least 2 waypoints.")

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
        self._route_active = True
        self._route_progress = 0
        self._stop_keepalive()

        self._route_thread = threading.Thread(
            target=self._route_loop, args=(coordinates, speed_kmh), daemon=True
        )
        self._route_thread.start()

        return {
            "status": "Route started",
            "distance_km": round(self._route_distance / 1000, 2),
            "total_points": len(coordinates),
            "coordinates": coordinates,
        }

    def _route_loop(self, coordinates, speed_kmh):
        speed_ms = speed_kmh / 3.6
        total = len(coordinates)

        for i in range(total):
            if not self._route_active:
                break
            lng, lat = coordinates[i]
            try:
                self._sim_set(lat, lng)
            except Exception:
                continue
            self.current_location = {"lat": lat, "lon": lng}
            self._route_progress = ((i + 1) / total) * 100

            if i < total - 1:
                nlng, nlat = coordinates[i + 1]
                dist = self._haversine(lat, lng, nlat, nlng)
                sleep_time = max(0.1, min(dist / speed_ms if speed_ms > 0 else 0.5, 10.0))
                time.sleep(sleep_time)

        if self._route_active:
            self._route_progress = 100
            self._route_active = False
            if self.current_location:
                self._start_keepalive()

    def stop_route(self):
        self._route_active = False
        if self._route_thread and self._route_thread.is_alive():
            self._route_thread.join(timeout=5)
        self._route_thread = None
        if self.current_location:
            self._start_keepalive()
        return {"status": "Route stopped"}

    def get_route_status(self):
        if self._route_coordinates is None:
            return None
        return {
            "active": self._route_active,
            "progress_pct": round(self._route_progress, 1),
            "distance_km": round(self._route_distance / 1000, 2),
            "duration_min": round(self._route_duration / 60, 1),
            "speed_kmh": self._route_speed,
        }

    @staticmethod
    def _haversine(lat1, lon1, lat2, lon2):
        R = 6371000
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dp = math.radians(lat2 - lat1)
        dl = math.radians(lon2 - lon1)
        a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    # ── Saved locations ────────────────────────────────────

    def get_saved(self):
        if not os.path.exists(SAVED_FILE):
            return []
        try:
            with open(SAVED_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []

    def save_location(self, name, lat, lon):
        locations = self.get_saved()
        for loc in locations:
            if loc["name"] == name:
                loc["lat"] = lat
                loc["lon"] = lon
                break
        else:
            locations.append({"name": name, "lat": lat, "lon": lon})
        with open(SAVED_FILE, "w") as f:
            json.dump(locations, f, indent=2)
        return {"status": f"Saved '{name}'"}

    def delete_location(self, name):
        locations = [loc for loc in self.get_saved() if loc["name"] != name]
        with open(SAVED_FILE, "w") as f:
            json.dump(locations, f, indent=2)
        return {"status": f"Deleted '{name}'"}
