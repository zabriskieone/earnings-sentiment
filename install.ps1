# EarningsPulse one-line installer for Windows (PowerShell):
#
#   irm https://raw.githubusercontent.com/zabriskieone/earnings-sentiment/main/install.ps1 | iex
#
# Downloads the app to %USERPROFILE%\EarningsPulse and runs start.bat, which sets
# everything up and opens the dashboard in your browser.
$ErrorActionPreference = "Stop"
$repo = if ($env:EARNINGSPULSE_REPO) { $env:EARNINGSPULSE_REPO } else { "https://github.com/zabriskieone/earnings-sentiment" }
$dir = if ($env:EARNINGSPULSE_DIR) { $env:EARNINGSPULSE_DIR } else { Join-Path $env:USERPROFILE "EarningsPulse" }

if (Test-Path (Join-Path $dir ".git")) {
    Write-Host "> Updating EarningsPulse in $dir ..."
    git -C $dir pull --ff-only --quiet
} elseif (Test-Path (Join-Path $dir "start.bat")) {
    Write-Host "> Using the existing copy in $dir"
} elseif (Get-Command git -ErrorAction SilentlyContinue) {
    Write-Host "> Downloading EarningsPulse to $dir ..."
    git clone --quiet --depth 1 $repo $dir
} else {
    Write-Host "> Downloading EarningsPulse to $dir ..."
    $zip = Join-Path $env:TEMP "earningspulse.zip"
    Invoke-WebRequest "$repo/archive/refs/heads/main.zip" -OutFile $zip
    $tmp = Join-Path $env:TEMP "earningspulse-unzip"
    if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
    Expand-Archive $zip -DestinationPath $tmp
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    Copy-Item (Join-Path (Get-ChildItem $tmp | Select-Object -First 1).FullName "*") $dir -Recurse -Force
    Remove-Item $zip, $tmp -Recurse -Force
}

Write-Host "Installed in $dir. Next time, double-click start.bat in that folder." -ForegroundColor Green
Start-Process -FilePath (Join-Path $dir "start.bat") -WorkingDirectory $dir
