param(
  [string]$ProjectPath = "C:\Users\monke\Desktop\WeCount\teamhome\frontend",
  [string]$TencentRoot = "C:\Program Files (x86)\Tencent\"
)

function Resolve-WeChatDevToolsDir {
  param([string]$RootDir)
  if (-not (Test-Path $RootDir)) { return $null }

  $allDirs = Get-ChildItem -Path $RootDir -Directory -ErrorAction SilentlyContinue
  foreach ($dir in $allDirs) {
    $cli = Join-Path $dir.FullName "cli.bat"
    if (Test-Path $cli) {
      return $dir.FullName
    }
  }
  return $null
}

$ConfiguredDirName = -join ([char[]](0x5FAE,0x4FE1,0x77,0x65,0x62,0x5F00,0x53D1,0x8005,0x5DE5,0x5177))
$ConfiguredDir = Join-Path $TencentRoot $ConfiguredDirName

$WeChatDevToolsDir = if (Test-Path $ConfiguredDir) {
  $ConfiguredDir
} else {
  Resolve-WeChatDevToolsDir -RootDir $TencentRoot
}
$projectOk = Test-Path $ProjectPath

if (-not $WeChatDevToolsDir) {
  Write-Error "Cannot locate WeChat DevTools directory under $TencentRoot (cli.bat not found)."
  exit 1
}

$CliPath = Join-Path $WeChatDevToolsDir "cli.bat"
$Exe = Get-ChildItem -Path $WeChatDevToolsDir -Filter "*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
$ExePath = if ($Exe) { $Exe.FullName } else { Join-Path $WeChatDevToolsDir "*.exe" }

$dirOk = Test-Path $WeChatDevToolsDir
$cliOk = Test-Path $CliPath
$exeOk = Test-Path $ExePath

Write-Host "WeChat DevTools path: $WeChatDevToolsDir"
Write-Host "Project path: $ProjectPath"
Write-Host ("Directory exists: " + $dirOk)
Write-Host ("CLI exists: " + $cliOk + " -> " + $CliPath)
Write-Host ("EXE exists: " + $exeOk + " -> " + $ExePath)
Write-Host ("Project exists: " + $projectOk)

if (-not $dirOk -or -not $projectOk) {
  Write-Error "Path check failed. Please verify installation/project path."
  exit 1
}

if ($cliOk) {
  Write-Host "Ready: can use cli.bat for upload/preview automation."
} else {
  Write-Host "Warning: cli.bat not found. GUI self-test still available."
}

exit 0
