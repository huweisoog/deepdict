# DeepDict Windows CLI Installer
# Usage:
#   irm https://raw.githubusercontent.com/<huweisoog>/deepdict/main/scripts/install.ps1 | iex
# Or install from a local clone:
#   powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1 -Source .

param(
    [string]$Source = "",
    [switch]$NoShortcut
)

$ErrorActionPreference = "Stop"

$DefaultRepo = "git+https://github.com/huweisoog/deepdict.git"
if (-not $Source) {
    if ($env:DEEPDICT_SOURCE) {
        $Source = $env:DEEPDICT_SOURCE
    } elseif ($PSScriptRoot -and (Test-Path (Join-Path (Split-Path $PSScriptRoot -Parent) "pyproject.toml"))) {
        $Source = Split-Path $PSScriptRoot -Parent
    } else {
        $Source = $DefaultRepo
    }
}

$InstallRoot = Join-Path $env:LOCALAPPDATA "DeepDict"
$VenvDir = Join-Path $InstallRoot "venv"
$BinDir = Join-Path $InstallRoot "bin"

Write-Host "==> DeepDict Windows Installer" -ForegroundColor Cyan
Write-Host "    Source : $Source"
Write-Host "    Target : $InstallRoot"

$PythonCmd = $null
foreach ($candidate in @("py", "python", "python3")) {
    $found = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($found) {
        $PythonCmd = $found.Source
        break
    }
}
if (-not $PythonCmd) {
    throw "Python 3.10+ not found. Please install Python from https://www.python.org/downloads/ and re-run."
}

New-Item -ItemType Directory -Force -Path $InstallRoot, $BinDir | Out-Null

if (-not (Test-Path (Join-Path $VenvDir "Scripts\python.exe"))) {
    Write-Host "==> Creating isolated virtual environment..." -ForegroundColor Cyan
    if ((Split-Path $PythonCmd -Leaf) -ieq "py.exe") {
        & $PythonCmd -3 -m venv $VenvDir
    } else {
        & $PythonCmd -m venv $VenvDir
    }
}

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$VenvPythonW = Join-Path $VenvDir "Scripts\pythonw.exe"

Write-Host "==> Upgrading pip and installing DeepDict..." -ForegroundColor Cyan
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install --upgrade $Source

$CmdShim = Join-Path $BinDir "deepdict.cmd"
$ShimBody = @"
@echo off
setlocal
if "%~1"=="--help" goto cli
if "%~1"=="-h" goto cli
if "%~1"=="--version" goto cli
if "%~1"=="-V" goto cli
if "%~1"=="--selftest" goto cli
start "" "$VenvPythonW" -m deepdict %*
exit /b 0
:cli
"$VenvPython" -m deepdict %*
"@
Set-Content -Path $CmdShim -Value $ShimBody -Encoding ASCII

$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (-not $UserPath) { $UserPath = "" }
$PathItems = $UserPath -split ";" | Where-Object { $_ -ne "" }
if ($PathItems -notcontains $BinDir) {
    $NewPath = ($PathItems + $BinDir) -join ";"
    [Environment]::SetEnvironmentVariable("Path", $NewPath, "User")
    Write-Host "==> Added $BinDir to User PATH (restart terminal to use 'deepdict')." -ForegroundColor Green
}

if (-not $NoShortcut) {
    try {
        $Desktop = [Environment]::GetFolderPath("Desktop")
        if ($Desktop -and (Test-Path $Desktop)) {
            $Shell = New-Object -ComObject WScript.Shell
            $Lnk = $Shell.CreateShortcut((Join-Path $Desktop "DeepDict.lnk"))
            $Lnk.TargetPath = $VenvPythonW
            $Lnk.Arguments = "-m deepdict"
            $Lnk.WorkingDirectory = $InstallRoot
            $Lnk.Description = "DeepDict - Global Selection Translator powered by DeepSeek"
            $Lnk.Save()
            Write-Host "==> Created Desktop shortcut: DeepDict.lnk" -ForegroundColor Green
        }
    } catch {
        Write-Host "    (Skipped Desktop shortcut: $($_.Exception.Message))" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "DeepDict installed successfully!" -ForegroundColor Green
Write-Host "  Run GUI      : deepdict"
Write-Host "  Demo mode    : deepdict --demo"
Write-Host "  Self check   : deepdict --selftest"
