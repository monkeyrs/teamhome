param(
  [switch]$SkipDb
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
& (Join-Path $ScriptDir "backend-dev.ps1") -Action start -SkipDb:$SkipDb
