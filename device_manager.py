import subprocess
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
    """Persistent asyncio event loop in a background thread.
    Needed because pymobiledevice3 v9+ is fully async but Flask is sync.
    The loop stays alive so DVT connections persist across calls."""

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def run(self, coro):
        """Submit an async coroutine and block until it completes."""
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result(timeout=30)


class DeviceManager:
    def __init__(self):
        self.tunneld_process = None
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
        }
        atexit.register(self.shutdown)

    def _get_tunnel_info(self, retries=15, delay=2):
        """Poll the tunneld HTTP API until a USB device is found."""
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

                # Prefer USB-connected device over network
                for device_udid, entries in data.items():
                    for entry in entries:
                        iface = entry.get("interface", "")
                        if "USB" in iface:
                            print(f"[+] Found USB device: {device_udid}")
                            print(f"    Tunnel: {entry['tunnel-address']}:{entry['tunnel-port']}")
                            return entry["tunnel-address"], entry["tunnel-port"], device_udid

                # Fallback to first device if no USB found
                device_udid = list(data.keys())[0]
                entry = data[device_udid][0]
                print(f"[+] Found device: {device_udid}")
                print(f"    Tunnel: {entry['tunnel-address']}:{entry['tunnel-port']}")
                return entry["tunnel-address"], entry["tunnel-port"], device_udid

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
            "  1. iPhone connected via USB cable\n"
            "  2. iPhone unlocked and 'Trust This Computer' accepted\n"
            "  3. Developer Mode enabled: Settings > Privacy & Security > Developer Mode\n"
        )

    async def _init_connection(self, tunnel_address, tunnel_port):
        """Initialize the RSD + DVT connection to the device."""
        self.rsd = RemoteServiceDiscoveryService((tunnel_address, tunnel_port))
        await self.rsd.connect()

        # Extract device info from peer_info.Properties
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

        # Connect the DVT provider
        self.provider = DvtProvider(self.rsd)
        await self.provider.connect()

        # Create and connect the location simulator (acquires DTX channel)
        self.simulator = LocationSimulation(self.provider)
        await self.simulator.connect()

    def connect(self):
        """Full connection flow: find device via tunnel, init DVT, return info."""
        tunnel_address, tunnel_port, udid = self._get_tunnel_info()
        self.device_info["udid"] = udid

        self.bridge.run(self._init_connection(tunnel_address, tunnel_port))

        self.device_info["connected"] = True
        print(f"[+] Connected: {self.device_info['name']} | "
              f"iOS {self.device_info['ios_version']} | "
              f"{self.device_info['model']}")
        return self.device_info

    def get_device_info(self):
        return dict(self.device_info)

    def shutdown(self):
        """Clean up DVT connection and tunneld subprocess."""
        if self.provider:
            try:
                self.bridge.run(self.provider.close())
            except Exception:
                pass

        if self.tunneld_process and self.tunneld_process.poll() is None:
            print("\n[*] Shutting down tunneld...")
            self.tunneld_process.terminate()
            try:
                self.tunneld_process.wait(timeout=5)
                print("[+] tunneld terminated")
            except subprocess.TimeoutExpired:
                self.tunneld_process.kill()
                print("[!] tunneld force killed")
        self.device_info["connected"] = False
