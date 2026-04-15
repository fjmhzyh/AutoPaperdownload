#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

APP_NAME="AutoPaperdownload"
VERSION="$(python3 -c 'from app_version import APP_VERSION; print(APP_VERSION)')"
RELEASE_DIR="$ROOT_DIR/release/mac"
APP_PATH="$ROOT_DIR/dist/${APP_NAME}.app"
APP_WORKERS_DIR="$APP_PATH/Contents/Workers"
BUILD_ASSETS_DIR="$ROOT_DIR/.build_assets"
CSV_TEMPLATE_PATH="$BUILD_ASSETS_DIR/PaperDoi.csv"

if [ -z "${PYINSTALLER_CONFIG_DIR:-}" ]; then
  export PYINSTALLER_CONFIG_DIR="$ROOT_DIR/.pyinstaller-cache"
fi
mkdir -p "$PYINSTALLER_CONFIG_DIR"
mkdir -p "$BUILD_ASSETS_DIR"
printf 'DOI,DownloadStatus,Filename,URL,DownloadURL,SIDownloadStatus,SIFilename,HTMLFilename\n' > "$CSV_TEMPLATE_PATH"

COMMON_HIDDEN=(
  --hidden-import pyautogui
  --hidden-import pyscreeze
  --hidden-import pyperclip
  --hidden-import mouseinfo
  --hidden-import cv2
  --hidden-import PIL
  --hidden-import psutil
)

DATA_ARGS=(
  --add-data "photos:photos"
  --add-data "DomainBranch.json:."
  --add-data "DownloadSettings.json:."
  --add-data "DownloadTemplates.json:."
  --add-data "LoginConfig.json:."
  --add-data "Paperkeyword.json:."
  --add-data "SIkeyword.json:."
  --add-data "initial_tabs.json:."
  --add-data "$CSV_TEMPLATE_PATH:."
)

WORKERS=(
  getdoi_worker
  paper_worker
  si_worker
  clean_worker
  csv_turner_worker
  doiexacter_worker
)

rm -rf build dist "$RELEASE_DIR"
mkdir -p "$RELEASE_DIR"

pyinstaller --noconfirm --clean --windowed --name "$APP_NAME" config_manager.py "${COMMON_HIDDEN[@]}" "${DATA_ARGS[@]}"
mkdir -p "$APP_WORKERS_DIR"

for worker in "${WORKERS[@]}"; do
  pyinstaller --noconfirm --onedir --name "$worker" "$worker.py" "${COMMON_HIDDEN[@]}" "${DATA_ARGS[@]}"
  rm -rf "$APP_WORKERS_DIR/$worker"
  cp -R "dist/$worker" "$APP_WORKERS_DIR/$worker"
  chmod +x "$APP_WORKERS_DIR/$worker/$worker"
done

DMG_PATH="$RELEASE_DIR/AutoPaperdownload-${VERSION}-mac-arm64.dmg"
hdiutil create -volname "$APP_NAME" -srcfolder "$APP_PATH" -ov -format UDZO "$DMG_PATH"

echo "构建完成: $DMG_PATH"
