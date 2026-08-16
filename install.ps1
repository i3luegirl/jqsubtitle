# JQSubtitle one-line installer
# Copyright (c) 2026 JQ Park. MIT License.
# Usage (PowerShell):  irm https://raw.githubusercontent.com/i3luegirl/jqsubtitle/main/install.ps1 | iex

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor 3072  # TLS 1.2
$RepoRaw    = "https://raw.githubusercontent.com/i3luegirl/jqsubtitle/main"
# v1.2부터 배포 파일명은 버전 없이 고정. 새 버전이 나와도 이 줄은 그대로 둔다.
$AppFile    = "jqsubtitle.py"
$IconFile   = "jqsubtitle.ico"
$InstallDir = Join-Path $env:LOCALAPPDATA "JQSubtitle"

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

Write-Host ""
Write-Host "  JQSubtitle installer — Just Quality AI Subtitle Maker" -ForegroundColor Green
Write-Host "  JQSubtitle 설치를 시작합니다" -ForegroundColor Green
Write-Host ""

# ---------- 1) Find Python 3.10+ ----------
function Find-Python {
    $candidates = @(
        @{ exe = "py";     args = @("-3", "-c", "import sys;print('%d %d'%sys.version_info[:2]);print(sys.executable)") },
        @{ exe = "python"; args = @("-c",       "import sys;print('%d %d'%sys.version_info[:2]);print(sys.executable)") }
    )
    foreach ($c in $candidates) {
        try {
            $out = & $c.exe @($c.args) 2>$null
            if ($LASTEXITCODE -eq 0 -and $out) {
                $lines = @($out)
                $ver = $lines[0].Trim().Split(" ")
                if ([int]$ver[0] -eq 3 -and [int]$ver[1] -ge 10) { return $lines[1].Trim() }
            }
        } catch { }
    }
    return $null
}

Write-Step "Checking Python... (Python 확인 중)"
$pyexe = Find-Python
if ($pyexe) {
    Write-Host "    Found: $pyexe"
} else {
    Write-Step "Python not found - installing Python 3.12 (Python이 없어 자동 설치합니다, 몇 분 걸립니다)"
    $installed = $false
    try {
        winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -eq 0) { $installed = $true }
    } catch { }
    if (-not $installed) {
        $url = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
        $tmp = Join-Path $env:TEMP "python-installer.exe"
        Write-Host "    Downloading from python.org..."
        Invoke-WebRequest $url -OutFile $tmp
        Start-Process $tmp -ArgumentList "/quiet", "InstallAllUsers=0", "PrependPath=1" -Wait
        Remove-Item $tmp -ErrorAction SilentlyContinue
    }
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "Machine")
    $pyexe = Find-Python
    if (-not $pyexe) {
        throw "Python install failed. Install Python 3.10+ from python.org, then run this again. / Python 자동 설치 실패 — python.org에서 설치 후 다시 실행해 주세요."
    }
    Write-Host "    Installed: $pyexe"
}

# ---------- 2) Download JQSubtitle ----------
Write-Step "Downloading JQSubtitle... (프로그램 다운로드 중)"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
$target = Join-Path $InstallDir "jqsubtitle.py"
$tmp    = "$target.download"
Invoke-WebRequest "$RepoRaw/$AppFile" -OutFile $tmp
Move-Item $tmp $target -Force          # 중간에 끊겨도 기존 설치가 깨지지 않도록
Write-Host "    Saved to: $target"

$icon = Join-Path $InstallDir "jqsubtitle.ico"
try {
    Invoke-WebRequest "$RepoRaw/$IconFile" -OutFile $icon
} catch {
    Write-Host "    Icon download skipped (using default icon)." -ForegroundColor Yellow
    Remove-Item $icon -Force -ErrorAction SilentlyContinue   # 잘린 파일이 남지 않도록
    $icon = $null
}

# ---------- 3) Install the speech engine ----------
Write-Step "Installing the speech engine (faster-whisper)... (음성 인식 엔진 설치 중 — 수 분 소요)"
& $pyexe -m pip install --upgrade faster-whisper tkinterdnd2
if ($LASTEXITCODE -ne 0) {
    Write-Host "    Engine install had an issue - JQSubtitle will retry automatically on first launch." -ForegroundColor Yellow
}

# ---------- 4) Desktop shortcut ----------
Write-Step "Creating desktop shortcut... (바탕화면 바로가기 생성)"
$pyw = $pyexe -replace "python\.exe$", "pythonw.exe"
if (-not (Test-Path $pyw)) { $pyw = $pyexe }
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut((Join-Path ([Environment]::GetFolderPath("Desktop")) "JQSubtitle.lnk"))
$lnk.TargetPath = $pyw
$lnk.Arguments = '"' + $target + '"'
$lnk.WorkingDirectory = $InstallDir
$lnk.Description = "JQSubtitle - Just Quality AI Subtitle Maker"
if ($icon -and (Test-Path $icon)) { $lnk.IconLocation = "$icon,0" }
$lnk.Save()

# Refresh the Windows icon cache so the new icon shows right away
try {
    $sig = '[DllImport("shell32.dll")] public static extern void SHChangeNotify(int e, uint f, IntPtr a, IntPtr b);'
    $sh = Add-Type -MemberDefinition $sig -Name JQShell -Namespace JQ -PassThru
    $sh::SHChangeNotify(0x08000000, 0, [IntPtr]::Zero, [IntPtr]::Zero)
} catch { }

# ---------- Done ----------
Write-Host ""
Write-Host "  Done! Double-click the JQSubtitle icon on your Desktop to start." -ForegroundColor Green
Write-Host "  설치 완료! 바탕화면의 JQSubtitle 아이콘으로 실행하세요." -ForegroundColor Green
Write-Host "  (First subtitle run downloads the Whisper model, ~3 GB, once.)"
Write-Host ""
Start-Process $pyw -ArgumentList ('"' + $target + '"') -WorkingDirectory $InstallDir
