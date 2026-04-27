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
MAC_SIGN_IDENTITY="${MAC_SIGN_IDENTITY:--}"

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
  yanzhen_worker
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

# Important: workers are copied after PyInstaller signs the app bundle,
# so we must re-sign the final app to avoid "app is damaged" on other Macs.
xattr -cr "$APP_PATH" || true
codesign --force --deep --sign "$MAC_SIGN_IDENTITY" "$APP_PATH"
codesign --verify --deep --strict "$APP_PATH"

DMG_PATH="$RELEASE_DIR/AutoPaperdownload-${VERSION}-mac-arm64.dmg"
for i in 1 2 3; do
  if hdiutil create -volname "$APP_NAME" -srcfolder "$APP_PATH" -ov -format UDZO "$DMG_PATH"; then
    break
  fi
  if [ "$i" -eq 3 ]; then
    echo "错误: DMG 生成失败，请重试（hdiutil 连续 3 次失败）" >&2
    exit 1
  fi
  echo "警告: 第 $i 次生成 DMG 失败，3 秒后重试..." >&2
  sleep 3
done
shasum -a 256 "$DMG_PATH" > "$DMG_PATH.sha256"

echo "构建完成: $DMG_PATH"
