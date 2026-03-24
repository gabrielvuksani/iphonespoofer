"""Tunnel service manager.

Handles starting pymobiledevice3 tunneld with admin privileges.
Two modes:
  1. Subprocess mode (for .app): launches tunneld via osascript admin prompt
  2. Direct mode (for start.sh): tunneld already running, just verify
"""

import os
import subprocess
import sys
import time

import requests as http_requests


TUNNELD_PORT = 49151
TUNNELD_URL = f"http://127.0.0.1:{TUNNELD_PORT}"


def is_tunneld_running():
    """Check if tunneld HTTP API is responding."""
    try:
        r = http_requests.get(TUNNELD_URL, timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def _get_tunneld_command():
    """Build the command to run tunneld."""
    # If frozen (PyInstaller), use bundled executable with --tunneld flag
    if getattr(sys, "frozen", False):
        exe = sys.executable
        return f'"{exe}" --tunneld'

    # Dev mode: use venv's pymobiledevice3
    pmd3 = os.path.join(os.path.dirname(sys.executable), "pymobiledevice3")
    if os.path.exists(pmd3):
        return f'"{pmd3}" remote tunneld'

    return f'"{sys.executable}" -m pymobiledevice3 remote tunneld'


def start_tunneld_with_admin():
    """Start tunneld using macOS admin dialog for root privileges.

    Shows the standard macOS password prompt. Returns True if started.
    """
    cmd = _get_tunneld_command()

    # osascript runs the command as root after user enters password
    # nohup + & ensures it keeps running after osascript returns
    script = (
        f'do shell script '
        f'"nohup {cmd} > /tmp/iphonespoofer-tunneld.log 2>&1 &"'
        f' with administrator privileges'
    )

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            print(f"[!] Admin auth failed or cancelled: {result.stderr.strip()}")
            return False
        return True
    except subprocess.TimeoutExpired:
        print("[!] Admin prompt timed out")
        return False
    except Exception as e:
        print(f"[!] Failed to start tunnel: {e}")
        return False


def ensure_tunnel(timeout=30):
    """Ensure tunneld is running. Start it if needed.

    Returns True when tunnel is ready, False on failure.
    """
    if is_tunneld_running():
        print("[+] Tunnel already running")
        return True

    print("[*] Starting tunnel (admin password required)...")
    if not start_tunneld_with_admin():
        return False

    # Wait for it to come up
    print("[*] Waiting for tunnel...")
    for i in range(timeout):
        if is_tunneld_running():
            print("[+] Tunnel ready")
            return True
        time.sleep(1)

    print("[!] Tunnel failed to start. Check /tmp/iphonespoofer-tunneld.log")
    return False


def run_tunneld_directly():
    """Run tunneld in-process (called when app is launched with --tunneld).

    This runs with root privileges via osascript.
    """
    # Import here to avoid loading pymobiledevice3 CLI machinery at app startup
    from pymobiledevice3.cli.remote import cli
    sys.argv = ["pymobiledevice3", "remote", "tunneld"]
    try:
        cli(standalone_mode=False)
    except SystemExit:
        pass
