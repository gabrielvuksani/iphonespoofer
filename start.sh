#!/bin/bash
# Developer mode: starts tunnel + Flask server in terminal.
# For the GUI app, use build.sh to create the .app + DMG instead.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="$SCRIPT_DIR/.venv"
TUNNELD_PID=""
APP_PORT=8080

cleanup() {
    echo ""
    echo "[*] Shutting down..."
    if [ -n "$TUNNELD_PID" ] && kill -0 "$TUNNELD_PID" 2>/dev/null; then
        kill "$TUNNELD_PID" 2>/dev/null
        wait "$TUNNELD_PID" 2>/dev/null
    fi
    exit 0
}
trap cleanup SIGINT SIGTERM

echo "=================================================="
echo "  iPhone Location Spoofer (Dev Mode)"
echo "=================================================="
echo ""

# ── Sudo check ───────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    echo "[!] Run with: sudo ./start.sh"
    exit 1
fi

REAL_USER="${SUDO_USER:-$USER}"

# ── Python ───────────────────────────────────────────────
PYTHON=$(su "$REAL_USER" -c "which python3" 2>/dev/null || which python3)
PY_VER=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "[+] Python $PY_VER ($PYTHON)"

# ── Venv (owned by real user) ────────────────────────────
if [ ! -d "$VENV_DIR" ] || [ "$(stat -f '%Su' "$VENV_DIR" 2>/dev/null)" = "root" ]; then
    rm -rf "$VENV_DIR" 2>/dev/null || true
    echo "[*] Creating venv..."
    su "$REAL_USER" -c "'$PYTHON' -m venv '$VENV_DIR'"
fi

VPYTHON="$VENV_DIR/bin/python3"

echo "[*] Installing deps..."
su "$REAL_USER" -c "'$VENV_DIR/bin/pip' install --no-cache-dir -q -r '$SCRIPT_DIR/requirements.txt'" 2>&1 \
    | grep -v "already satisfied" | grep -v "pip version" | grep -v "You should" || true
echo "[+] Ready"

# ── Free port ────────────────────────────────────────────
lsof -ti :"$APP_PORT" 2>/dev/null | xargs kill -9 2>/dev/null || true

# ── Tunnel ───────────────────────────────────────────────
echo ""
if curl -s http://127.0.0.1:49151 &>/dev/null; then
    echo "[+] Tunnel running"
else
    echo "[*] Starting tunnel..."
    "$VPYTHON" -m pymobiledevice3 remote tunneld > /tmp/iphonespoofer-tunneld.log 2>&1 &
    TUNNELD_PID=$!
    for i in $(seq 1 30); do
        if ! kill -0 "$TUNNELD_PID" 2>/dev/null; then
            echo "[!] Tunnel crashed:"; cat /tmp/iphonespoofer-tunneld.log 2>/dev/null; exit 1
        fi
        curl -s http://127.0.0.1:49151 &>/dev/null && echo "[+] Tunnel ready" && break
        [ "$i" -eq 30 ] && echo "[!] Tunnel timeout" && exit 1
        sleep 1
    done
fi

# ── Launch ───────────────────────────────────────────────
echo ""
(sleep 2 && su "$REAL_USER" -c "open 'http://localhost:$APP_PORT'" 2>/dev/null) &
su "$REAL_USER" -c "cd '$SCRIPT_DIR' && '$VPYTHON' app.py"
cleanup
