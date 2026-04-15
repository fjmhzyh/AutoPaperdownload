$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

$version = python -c "from app_version import APP_VERSION; print(APP_VERSION)"
$distDir = Join-Path $root "dist\\AutoPaperdownload"
$pyiConfigDir = Join-Path $root ".pyinstaller-cache"
$buildAssetsDir = Join-Path $root ".build_assets"
$csvTemplatePath = Join-Path $buildAssetsDir "PaperDoi.csv"

if (-not $env:PYINSTALLER_CONFIG_DIR) {
  $env:PYINSTALLER_CONFIG_DIR = $pyiConfigDir
}
if (-not (Test-Path $env:PYINSTALLER_CONFIG_DIR)) {
  New-Item -ItemType Directory -Path $env:PYINSTALLER_CONFIG_DIR | Out-Null
}
if (-not (Test-Path $buildAssetsDir)) {
  New-Item -ItemType Directory -Path $buildAssetsDir | Out-Null
}
"DOI,DownloadStatus,Filename,URL,DownloadURL,SIDownloadStatus,SIFilename,HTMLFilename" | Set-Content -Path $csvTemplatePath -Encoding utf8

$commonHidden = @(
  '--hidden-import', 'pyautogui',
  '--hidden-import', 'pyscreeze',
  '--hidden-import', 'pyperclip',
  '--hidden-import', 'mouseinfo',
  '--hidden-import', 'cv2',
  '--hidden-import', 'PIL',
  '--hidden-import', 'psutil'
)

$dataArgs = @(
  '--add-data', 'photos;photos',
  '--add-data', 'DomainBranch.json;.',
  '--add-data', 'DownloadSettings.json;.',
  '--add-data', 'DownloadTemplates.json;.',
  '--add-data', 'LoginConfig.json;.',
  '--add-data', 'Paperkeyword.json;.',
  '--add-data', 'SIkeyword.json;.',
  '--add-data', 'initial_tabs.json;.',
  '--add-data', "$csvTemplatePath;.",
  '--add-data', 'edgedriver;edgedriver'
)

$workers = @(
  'getdoi_worker',
  'paper_worker',
  'si_worker',
  'clean_worker',
  'csv_turner_worker',
  'doiexacter_worker'
)

if (Test-Path build) { Remove-Item build -Recurse -Force }
if (Test-Path dist) { Remove-Item dist -Recurse -Force }
if (-not (Test-Path 'release\\win')) { New-Item -ItemType Directory -Path 'release\\win' | Out-Null }

python -m PyInstaller --noconfirm --clean --onedir --windowed --name AutoPaperdownload config_manager.py @commonHidden @dataArgs

foreach ($worker in $workers) {
  python -m PyInstaller --noconfirm --onefile --name $worker "$worker.py" @commonHidden @dataArgs
  Copy-Item "dist\\$worker.exe" -Destination "$distDir\\$worker.exe" -Force
}

$iscc = "${env:ProgramFiles(x86)}\\Inno Setup 6\\ISCC.exe"
if (Test-Path $iscc) {
  & $iscc "/DMyAppVersion=$version" "/DSourceDir=$distDir" "packaging\\autopaperdownload.iss"
  Write-Host "安装包已生成到 release\\win"
} else {
  Write-Warning "未检测到 Inno Setup，已生成可分发目录: $distDir"
}
