# build.ps1 - Drive-safe build: make icon, freeze ClickLater.exe (icon + CTk assets), run it.
#     powershell -ExecutionPolicy Bypass -File .\build.ps1
#
# SENIOR notes:
#   * NEVER build inside Google Drive (My Drive\). The Drive sync client locks
#     files mid-write and PyInstaller's cleanup dies with 'Access denied'. We
#     freeze to $env:TEMP and copy only the finished exe back into .\dist.
#   * --collect-all customtkinter bundles CTk's theme JSON/assets (data files,
#     not code - PyInstaller won't grab them on its own -> frozen app crashes).
#   * --add-data "<ico>;." ships the icon inside the exe so the running window
#     and taskbar can load it from sys._MEIPASS at runtime.
#   * A running onefile exe LOCKS its file, so kill any live instance first.

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

# deps
python -c "import customtkinter, PIL" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing customtkinter + pillow..." -ForegroundColor Cyan
    python -m pip install --upgrade customtkinter pillow
}

# icon
python make_icon.py
$ico = (Resolve-Path .\click_later.ico).Path

# free the exe if it is already running
Get-Process ClickLater -ErrorAction SilentlyContinue | Stop-Process -Force

# build in LOCAL temp (outside Google Drive), then copy the exe back
$work = Join-Path $env:TEMP 'cl_build'
$dist = Join-Path $env:TEMP 'cl_dist'
Remove-Item $work, $dist -Recurse -Force -ErrorAction SilentlyContinue

python -m PyInstaller --onefile --windowed --noconfirm --name ClickLater `
    --icon $ico --add-data "$ico;." --collect-all customtkinter `
    --workpath $work --distpath $dist click_later.py

New-Item -ItemType Directory -Force -Path .\dist | Out-Null
Copy-Item (Join-Path $dist 'ClickLater.exe') .\dist\ClickLater.exe -Force

if (Test-Path .\dist\ClickLater.exe) {
    $mb = (Get-Item .\dist\ClickLater.exe).Length / 1MB
    Write-Host ("Built: .\dist\ClickLater.exe  ({0:N1} MB)" -f $mb) -ForegroundColor Green
    Start-Process .\dist\ClickLater.exe
} else {
    throw "Build produced no exe - scroll up for the PyInstaller error."
}
