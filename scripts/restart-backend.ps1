param(
  [switch]$NoBuild
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
& (Join-Path $ScriptDir "backend-dev.ps1") -Action restart -NoBuild:$NoBuild
