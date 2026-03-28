param(
  [switch]$NoBuild
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
Write-Host "Backend security and migration preflight are enabled."
& (Join-Path $ScriptDir "backend-dev.ps1") -Action restart -NoBuild:$NoBuild
