#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

APP_NAME="iPhone Spoofer"
BUNDLE_ID="com.iphonespoofer.app"
VERSION="1.0.0"
VENV_DIR="$SCRIPT_DIR/.venv"
DIST_DIR="$SCRIPT_DIR/dist"
APP_DIR="$DIST_DIR/$APP_NAME.app"
DMG_NAME="iPhone-Spoofer-${VERSION}"

echo "=================================================="
echo "  Building $APP_NAME v$VERSION"
echo "=================================================="
echo ""

# ── 1. Venv ──────────────────────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
    echo "[1/5] Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
else
    echo "[1/5] Using existing venv"
fi

VPYTHON="$VENV_DIR/bin/python3"
VPIP="$VENV_DIR/bin/pip"

# ── 2. Dependencies ─────────────────────────────────────
echo "[2/5] Installing dependencies..."
"$VPIP" install --no-cache-dir -q -r requirements.txt pyinstaller 2>&1 \
    | grep -v "already satisfied" \
    | grep -v "pip version" \
    | grep -v "You should consider" || true
echo "      Done"

# ── 3. Clean ─────────────────────────────────────────────
echo "[3/5] Cleaning previous builds..."
rm -rf "$DIST_DIR" build *.spec

# ── 4. PyInstaller ───────────────────────────────────────
echo "[4/5] Building app bundle..."
echo "      This takes 2-5 minutes..."

"$VPYTHON" -m PyInstaller \
    --name "$APP_NAME" \
    --windowed \
    --onedir \
    --noconfirm \
    --clean \
    --log-level WARN \
    --osx-bundle-identifier "$BUNDLE_ID" \
    --add-data "templates:templates" \
    --add-data "static:static" \
    --collect-all pymobiledevice3 \
    --collect-all webview \
    --hidden-import pymobiledevice3.cli.remote \
    --hidden-import pymobiledevice3.remote.tunnel_service \
    --hidden-import webview.platforms.cocoa \
    main_app.py \
    2>&1 | grep -E "^(INFO|WARNING|ERROR|Building)" || true

if [ ! -d "$APP_DIR" ]; then
    echo "[!] Build failed"
    exit 1
fi

# Write Info.plist with proper metadata
cat > "$APP_DIR/Contents/Info.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>$APP_NAME</string>
    <key>CFBundleDisplayName</key>
    <string>$APP_NAME</string>
    <key>CFBundleIdentifier</key>
    <string>$BUNDLE_ID</string>
    <key>CFBundleVersion</key>
    <string>$VERSION</string>
    <key>CFBundleShortVersionString</key>
    <string>$VERSION</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleExecutable</key>
    <string>$APP_NAME</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.15</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>LSUIElement</key>
    <false/>
    <key>NSAppTransportSecurity</key>
    <dict>
        <key>NSAllowsArbitraryLoads</key>
        <true/>
    </dict>
</dict>
</plist>
PLIST

echo "      App bundle created"

# ── 5. DMG ───────────────────────────────────────────────
echo "[5/5] Creating DMG..."

DMG_FINAL="$DIST_DIR/$DMG_NAME.dmg"
DMG_STAGING="$DIST_DIR/dmg_staging"

# Stage files
rm -rf "$DMG_STAGING"
mkdir -p "$DMG_STAGING"
cp -R "$APP_DIR" "$DMG_STAGING/"
ln -s /Applications "$DMG_STAGING/Applications"

# Create compressed DMG directly from staging directory
rm -f "$DMG_FINAL"
hdiutil create \
    -volname "$APP_NAME" \
    -srcfolder "$DMG_STAGING" \
    -ov \
    -format UDZO \
    "$DMG_FINAL" \
    -quiet

rm -rf "$DMG_STAGING"

APP_SIZE=$(du -sh "$APP_DIR" | cut -f1)
DMG_SIZE=$(du -sh "$DMG_FINAL" | cut -f1)

echo ""
echo "=================================================="
echo "  Build complete!"
echo "=================================================="
echo ""
echo "  App:  $APP_DIR ($APP_SIZE)"
echo "  DMG:  $DMG_FINAL ($DMG_SIZE)"
echo ""
echo "  Test:   open '$APP_DIR'"
echo "  Share:  Send the DMG file"
echo ""
