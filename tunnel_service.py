"""Tunnel service manager — cross-platform (macOS + Windows).

Handles starting pymobiledevice3 tunneld with admin/root privileges.
- macOS: uses osascript for standard password dialog
- Windows: uses PowerShell Start-Process -Verb RunAs for UAC prompt
"""

import os
import platform
import subprocess
import sys
import time
import tempfile

import requests as http_requests


TUNNELD_PORT = 49151
TUNNELD_URL = f"http://127.0.0.1:{TUNNELD_PORT}"
IS_WINDOWS = platform.system() == "Windows"
IS_FROZEN = getattr(sys, "frozen", False)


def is_tunneld_running():
    try:
        r = http_requests.get(TUNNELD_URL, timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def _get_tunneld_command():
    """Return (executable, args_list) for running tunneld."""
    if IS_FROZEN:
        return sys.executable, ["--tunneld"]

    # Dev mode: try direct CLI, then python -m
    pmd3_name = "pymobiledevice3.exe" if IS_WINDOWS else "pymobiledevice3"
    pmd3 = os.path.join(os.path.dirname(sys.executable), pmd3_name)
    if os.path.exists(pmd3):
        return pmd3, ["remote", "tunneld"]

    return sys.executable, ["-m", "pymobiledevice3", "remote", "tunneld"]


def _log_path():
    if IS_WINDOWS:
        return os.path.join(tempfile.gettempdir(), "iphonespoofer-tunneld.log")
    return "/tmp/iphonespoofer-tunneld.log"


def start_tunneld_with_admin():
    """Start tunneld with elevated privileges. Returns True if launched."""
    exe, args = _get_tunneld_command()
    log = _log_path()

    if IS_WINDOWS:
        return _start_windows(exe, args, log)
    else:
        return _start_macos(exe, args, log)


def _start_macos(exe, args, log):
    cmd_str = f'"{exe}" {" ".join(args)}'
    script = (
        f'do shell script '
        f'"nohup {cmd_str} > {log} 2>&1 &"'
        f' with administrator privileges'
    )
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=120,
        )
        return result.returncode == 0
    except Exception as e:
        print(f"[!] Failed to start tunnel: {e}")
        return False


def _start_windows(exe, args, log):
    """Use PowerShell to elevate via UAC prompt."""
    full_args = " ".join(f'"{a}"' for a in args)
    # Write a small batch wrapper that redirects output to log
    wrapper = os.path.join(tempfile.gettempdir(), "iphonespoofer_tunnel.bat")
    with open(wrapper, "w") as f:
        f.write(f'@echo off\n"{exe}" {full_args} > "{log}" 2>&1\n')

    try:
        # Start-Process with -Verb RunAs triggers UAC
        ps_cmd = (
            f'Start-Process -FilePath "cmd.exe" '
            f'-ArgumentList "/c","{wrapper}" '
            f'-Verb RunAs -WindowStyle Hidden'
        )
        result = subprocess.run(
            ["powershell", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=120,
        )
        return result.returncode == 0
    except Exception as e:
        print(f"[!] Failed to start tunnel: {e}")
        return False


def ensure_tunnel(timeout=30):
    """Ensure tunneld is running. Start it if needed."""
    if is_tunneld_running():
        print("[+] Tunnel already running")
        return True

    print("[*] Starting tunnel (admin access required)...")
    if not start_tunneld_with_admin():
        print("[!] Admin prompt cancelled or failed")
        return False

    print("[*] Waiting for tunnel...")
    for _ in range(timeout):
        if is_tunneld_running():
            print("[+] Tunnel ready")
            return True
        time.sleep(1)

    print(f"[!] Tunnel timeout. Check {_log_path()}")
    return False


def run_tunneld_directly():
    """Run tunneld in-process (called with --tunneld flag)."""
    from pymobiledevice3.cli.remote import cli
    sys.argv = ["pymobiledevice3", "remote", "tunneld"]
    try:
        cli(standalone_mode=False)
    except SystemExit:
        pass
