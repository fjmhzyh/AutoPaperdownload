param(
  [string]$IsccPath
)

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

function Normalize-ExePath {
  param([string]$RawPath)
  if ([string]::IsNullOrWhiteSpace($RawPath)) { return $null }

  $value = $RawPath.Trim()
  if ($value.StartsWith('"')) {
    $match = [regex]::Match($value, '^"([^"]+)"')
    if ($match.Success) { $value = $match.Groups[1].Value }
  } else {
    $match = [regex]::Match($value, '^([^\s]+\.exe)')
    if ($match.Success) { $value = $match.Groups[1].Value }
  }

  if ($value -match ',\d+$') {
    $value = $value -replace ',\d+$', ''
  }

  return $value
}

function Add-IsccCandidate {
  param(
    [System.Collections.ArrayList]$Checked,
    [ref]$ResolvedPath,
    [string]$Candidate
  )

  if ([string]::IsNullOrWhiteSpace($Candidate)) { return }
  $normalized = Normalize-ExePath -RawPath ([Environment]::ExpandEnvironmentVariables($Candidate))
  if ([string]::IsNullOrWhiteSpace($normalized)) { return }

  if (-not ($Checked -contains $normalized)) {
    [void]$Checked.Add($normalized)
  }

  if (-not $ResolvedPath.Value -and (Test-Path $normalized -PathType Leaf)) {
    $ResolvedPath.Value = (Resolve-Path $normalized).Path
  }
}

function Resolve-IsccPath {
  param([string]$ManualPath)

  $checked = New-Object System.Collections.ArrayList
  $resolved = $null

  # 1) Manual parameter
  Add-IsccCandidate -Checked $checked -ResolvedPath ([ref]$resolved) -Candidate $ManualPath

  # 2) Environment variable
  Add-IsccCandidate -Checked $checked -ResolvedPath ([ref]$resolved) -Candidate $env:ISCC_PATH

  # 3) PATH
  try {
    $cmd = Get-Command ISCC.exe -ErrorAction Stop | Select-Object -First 1
    if ($cmd) {
      Add-IsccCandidate -Checked $checked -ResolvedPath ([ref]$resolved) -Candidate $cmd.Source
    }
  } catch {
    # Ignore and continue probing
  }

  # 4) Common install paths
  $pf86 = [Environment]::GetEnvironmentVariable('ProgramFiles(x86)')
  $pf64 = [Environment]::GetEnvironmentVariable('ProgramFiles')
  if (-not [string]::IsNullOrWhiteSpace($pf86)) {
    Add-IsccCandidate -Checked $checked -ResolvedPath ([ref]$resolved) -Candidate (Join-Path $pf86 "Inno Setup 6\ISCC.exe")
  }
  if (-not [string]::IsNullOrWhiteSpace($pf64)) {
    Add-IsccCandidate -Checked $checked -ResolvedPath ([ref]$resolved) -Candidate (Join-Path $pf64 "Inno Setup 6\ISCC.exe")
  }

  # 5) Registry (uninstall keys + App Paths, 64/32 views)
  $uninstallKeys = @(
    "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1",
    "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"
  )
  foreach ($key in $uninstallKeys) {
    try {
      if (-not (Test-Path $key)) { continue }
      $props = Get-ItemProperty -Path $key -ErrorAction Stop
      if ($props.InstallLocation) {
        Add-IsccCandidate -Checked $checked -ResolvedPath ([ref]$resolved) -Candidate (Join-Path $props.InstallLocation "ISCC.exe")
      }
      if ($props.DisplayIcon) {
        Add-IsccCandidate -Checked $checked -ResolvedPath ([ref]$resolved) -Candidate $props.DisplayIcon
      }
    } catch {
      continue
    }
  }

  $appPathKeys = @(
    "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\ISCC.exe",
    "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\ISCC.exe"
  )
  foreach ($key in $appPathKeys) {
    try {
      if (-not (Test-Path $key)) { continue }
      $item = Get-Item -Path $key -ErrorAction Stop
      $defaultExe = $item.GetValue("")
      Add-IsccCandidate -Checked $checked -ResolvedPath ([ref]$resolved) -Candidate $defaultExe

      $props = Get-ItemProperty -Path $key -ErrorAction SilentlyContinue
      if ($props -and $props.Path) {
        Add-IsccCandidate -Checked $checked -ResolvedPath ([ref]$resolved) -Candidate (Join-Path $props.Path "ISCC.exe")
      }
    } catch {
      continue
    }
  }

  return [pscustomobject]@{
    Path = $resolved
    Checked = @($checked)
  }
}

function Invoke-PyInstallerChecked {
  param(
    [Parameter(Mandatory = $true)]
    [string[]]$Arguments,
    [Parameter(Mandatory = $true)]
    [string]$StepName
  )

  Write-Host "[Build] $StepName"
  & python @Arguments
  if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller failed at step '$StepName', exit code: $LASTEXITCODE"
    exit 1
  }
}

if (Test-Path build) { Remove-Item build -Recurse -Force }
if (Test-Path dist) { Remove-Item dist -Recurse -Force }
if (-not (Test-Path 'release\\win')) { New-Item -ItemType Directory -Path 'release\\win' | Out-Null }

${guiArgs} = @(
  "-m", "PyInstaller",
  "--noconfirm",
  "--clean",
  "--onedir",
  "--windowed",
  "--name", "AutoPaperdownload",
  "config_manager.py"
) + $commonHidden + $dataArgs
Invoke-PyInstallerChecked -StepName "Build GUI (AutoPaperdownload)" -Arguments $guiArgs

foreach ($worker in $workers) {
  ${workerArgs} = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--onefile",
    "--name", $worker,
    "$worker.py"
  ) + $commonHidden + $dataArgs
  Invoke-PyInstallerChecked -StepName "Build worker ($worker)" -Arguments $workerArgs

  $workerExeOnefile = "dist\\$worker.exe"
  $workerExeOnedir = "dist\\$worker\\$worker.exe"
  $workerSource = $null
  if (Test-Path $workerExeOnefile -PathType Leaf) {
    $workerSource = $workerExeOnefile
  } elseif (Test-Path $workerExeOnedir -PathType Leaf) {
    $workerSource = $workerExeOnedir
  }

  if (-not $workerSource) {
    Write-Error "Worker build output missing for '$worker'. Checked: $workerExeOnefile, $workerExeOnedir"
    exit 1
  }

  Copy-Item $workerSource -Destination "$distDir\\$worker.exe" -Force
  Write-Host "[Build] Worker copied: $workerSource -> $distDir\\$worker.exe"
}

$resolveResult = Resolve-IsccPath -ManualPath $IsccPath
Write-Host "[Inno] Checked ISCC path candidates:"
if ($resolveResult.Checked.Count -eq 0) {
  Write-Host "  - (none)"
} else {
  $resolveResult.Checked | ForEach-Object { Write-Host "  - $_" }
}

$iscc = $resolveResult.Path
if ($iscc) {
  Write-Host "[Inno] Using ISCC: $iscc"
  & $iscc "/DMyAppVersion=$version" "/DSourceDir=$distDir" "packaging\\autopaperdownload.iss"
  if ($LASTEXITCODE -ne 0) {
    Write-Error "Inno Setup compilation failed, exit code: $LASTEXITCODE"
    exit 1
  }

  $hashOut = "release\\win\\SHA256SUMS.txt"
  if (Test-Path $hashOut) { Remove-Item $hashOut -Force }
  Get-ChildItem "release\\win\\*.exe" | ForEach-Object {
    $h = Get-FileHash $_.FullName -Algorithm SHA256
    "$($h.Hash)  $($_.Name)" | Out-File -FilePath $hashOut -Encoding utf8 -Append
  }

  Write-Host "Installer generated in release\\win"
  $artifacts = Get-ChildItem "release\\win" -File | Where-Object { $_.Extension -eq ".exe" -or $_.Name -eq "SHA256SUMS.txt" }
  if ($artifacts) {
    Write-Host "[Inno] release\\win artifacts:"
    $artifacts | Sort-Object Name | ForEach-Object { Write-Host "  - $($_.Name)" }
  }
} else {
  Write-Warning "Inno Setup (ISCC.exe) not found. Portable output generated: $distDir"
  Write-Warning "Only dist will be generated; release\\win installer will not be created. Use -IsccPath to specify ISCC.exe."
}
