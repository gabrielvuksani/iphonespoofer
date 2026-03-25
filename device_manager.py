import asyncio
import atexit
import threading
import time
import sys

import requests as http_requests

from pymobiledevice3.remote.remote_service_discovery import RemoteServiceDiscoveryService
from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation


TUNNELD_PORT = 49151


class AsyncBridge:
    """Persistent asyncio event loop in a background thread."""

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def run(self, coro):
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result(timeout=30)


class DeviceManager:
    def __init__(self):
        self.rsd = None
        self.provider = None
        self.simulator = None
        self.bridge = AsyncBridge()
        self.device_info = {
            "name": None,
            "ios_version": None,
            "udid": None,
            "model": None,
            "connected": False,
            "connection_type": None,
        }
        self._auto_reconnect = False
        self._reconnect_thread = None
        self._reconnect_callback = None  # Called after successful reconnect
        atexit.register(self.shutdown)

    # ── Auto-reconnect ─────────────────────────────────────

    def enable_auto_reconnect(self, callback=None):
        """Start background auto-reconnect. callback(device_info) is called on reconnect."""
        self._auto_reconnect = True
        self._reconnect_callback = callback
        if not self._reconnect_thread or not self._reconnect_thread.is_alive():
            self._reconnect_thread = threading.Thread(target=self._reconnect_loop, daemon=True)
            self._reconnect_thread.start()
        return {"status": "Auto-reconnect enabled"}

    def disable_auto_reconnect(self):
        self._auto_reconnect = False
        if self._reconnect_thread and self._reconnect_thread.is_alive():
            self._reconnect_thread.join(timeout=5)
        self._reconnect_thread = None
        return {"status": "Auto-reconnect disabled"}

    def _reconnect_loop(self):
        """Periodically check connection and reconnect if needed."""
        while self._auto_reconnect:
            if self.device_info.get("connected"):
                # Verify connection is still alive
                if not self._is_connection_alive():
                    print("[!] Device disconnected, attempting auto-reconnect...")
                    self.device_info["connected"] = False
                    try:
                        prefer_wifi = self.device_info.get("connection_type") == "WiFi"
                        self.disconnect()
                        info = self.connect(prefer_wifi=prefer_wifi, retries=3, delay=2)
                        print(f"[+] Auto-reconnected ({info.get('connection_type', 'USB')})")
                        if self._reconnect_callback:
                            try:
                                self._reconnect_callback(info)
                            except Exception:
                                pass
                    except Exception as e:
                        print(f"[!] Auto-reconnect failed: {e}")
            time.sleep(10)

    def _is_connection_alive(self):
        """Quick check if the current connection is still responsive."""
        if not self.simulator:
            return False
        try:
            # Attempt a lightweight operation
            self.bridge.run(self.simulator.set(0, 0))
            # Clear immediately to avoid side effects
            self.bridge.run(self.simulator.clear())
            return True
        except Exception:
            return False

    # ── Tunnel discovery ───────────────────────────────────

    def _get_tunnel_info(self, prefer_wifi=False, retries=15, delay=2):
        """Poll tunneld HTTP API. Can prefer WiFi or USB connections."""
        for attempt in range(retries):
            try:
                resp = http_requests.get(
                    f"http://127.0.0.1:{TUNNELD_PORT}", timeout=5
                )
                data = resp.json()

                if not data:
                    print(
                        f"  [{attempt+1}/{retries}] No devices found, "
                        "make sure iPhone is connected via USB and trusted..."
                    )
                    time.sleep(delay)
                    continue

                usb_connections = []
                wifi_connections = []
                for device_udid, entries in data.items():
                    for entry in entries:
                        iface = entry.get("interface", "")
                        info = (entry["tunnel-address"], entry["tunnel-port"], device_udid, iface)
                        if "USB" in iface:
                            usb_connections.append(info)
                        else:
                            wifi_connections.append(info)

                if prefer_wifi and wifi_connections:
                    addr, port, udid, iface = wifi_connections[0]
                    conn_type = "WiFi"
                elif usb_connections:
                    addr, port, udid, iface = usb_connections[0]
                    conn_type = "USB"
                elif wifi_connections:
                    addr, port, udid, iface = wifi_connections[0]
                    conn_type = "WiFi"
                else:
                    time.sleep(delay)
                    continue

                print(f"[+] Found device ({conn_type}): {udid}")
                print(f"    Tunnel: {addr}:{port}")
                return addr, port, udid, conn_type

            except (
                http_requests.ConnectionError,
                http_requests.Timeout,
                KeyError,
                IndexError,
            ) as e:
                print(f"  [{attempt+1}/{retries}] Waiting for tunnel... ({e})")
                time.sleep(delay)

        raise ConnectionError(
            "Could not find a connected device after multiple retries.\n"
            "Checklist:\n"
            "  1. iPhone connected via USB or on the same WiFi network\n"
            "  2. iPhone unlocked and 'Trust This Computer' accepted\n"
            "  3. Developer Mode enabled: Settings > Privacy & Security > Developer Mode\n"
        )

    def get_available_connections(self):
        """Return list of available device connections (USB and WiFi)."""
        try:
            resp = http_requests.get(f"http://127.0.0.1:{TUNNELD_PORT}", timeout=3)
            data = resp.json()
            connections = []
            for udid, entries in data.items():
                for entry in entries:
                    iface = entry.get("interface", "")
                    connections.append({
                        "udid": udid,
                        "type": "USB" if "USB" in iface else "WiFi",
                        "address": entry["tunnel-address"],
                        "port": entry["tunnel-port"],
                    })
            return connections
        except Exception:
            return []

    def get_all_devices(self):
        """Return unique device UDIDs with their available connection types."""
        try:
            resp = http_requests.get(f"http://127.0.0.1:{TUNNELD_PORT}", timeout=3)
            data = resp.json()
            devices = {}
            for udid, entries in data.items():
                types = set()
                for entry in entries:
                    iface = entry.get("interface", "")
                    types.add("USB" if "USB" in iface else "WiFi")
                devices[udid] = {"udid": udid, "connection_types": sorted(types)}
            return list(devices.values())
        except Exception:
            return []

    # ── Connection management ──────────────────────────────

    async def _init_connection(self, tunnel_address, tunnel_port):
        self.rsd = RemoteServiceDiscoveryService((tunnel_address, tunnel_port))
        await self.rsd.connect()

        props = {}
        try:
            props = self.rsd.peer_info.get("Properties", {})
        except Exception:
            pass

        self.device_info["name"] = props.get("DeviceClass", "iPhone")
        self.device_info["ios_version"] = (
            props.get("HumanReadableProductVersionString")
            or props.get("OSVersion")
            or "Unknown"
        )
        self.device_info["model"] = props.get("ProductType", "Unknown")
        self.device_info["udid"] = props.get("UniqueDeviceID", self.device_info.get("udid"))

        self.provider = DvtProvider(self.rsd)
        await self.provider.connect()

        self.simulator = LocationSimulation(self.provider)
        await self.simulator.connect()

    def connect(self, prefer_wifi=False, retries=15, delay=2):
        """Full connection flow."""
        addr, port, udid, conn_type = self._get_tunnel_info(
            prefer_wifi=prefer_wifi, retries=retries, delay=delay
        )
        self.device_info["udid"] = udid
        self.device_info["connection_type"] = conn_type

        self.bridge.run(self._init_connection(addr, port))

        self.device_info["connected"] = True
        print(f"[+] Connected ({conn_type}): {self.device_info['name']} | "
              f"iOS {self.device_info['ios_version']} | "
              f"{self.device_info['model']}")
        return self.device_info

    def disconnect(self):
        """Disconnect from the current device."""
        if self.provider:
            try:
                self.bridge.run(self.provider.close())
            except Exception:
                pass
            self.provider = None
            self.simulator = None
        if self.rsd:
            try:
                self.bridge.run(self.rsd.close())
            except Exception:
                pass
            self.rsd = None
        self.device_info["connected"] = False
        self.device_info["connection_type"] = None

    def reconnect(self, prefer_wifi=False, retries=15, delay=2):
        """Disconnect current and reconnect."""
        self.disconnect()
        return self.connect(prefer_wifi=prefer_wifi, retries=retries, delay=delay)

    def get_device_info(self):
        return dict(self.device_info)

    def shutdown(self):
        self._auto_reconnect = False
        if self.provider:
            try:
                self.bridge.run(self.provider.close())
            except Exception:
                pass
            self.provider = None
            self.simulator = None
        if self.rsd:
            try:
                self.bridge.run(self.rsd.close())
            except Exception:
                pass
            self.rsd = None
        self.device_info["connected"] = False
