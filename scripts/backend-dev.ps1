param(
  [ValidateSet("start", "restart", "stop", "status")]
  [string]$Action = "start",
  [int]$Port = 8000,
  [switch]$SkipDb
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Resolve-Path (Join-Path $ScriptDir "..")
$BackendDir = Join-Path $RootDir "backend"
$ComposeFile = Join-Path $RootDir "docker-compose.yml"
$RunDir = Join-Path $BackendDir ".run"
$PidFile = Join-Path $RunDir "uvicorn.pid"
$StdoutLogFile = Join-Path $RunDir "uvicorn.stdout.log"
$StderrLogFile = Join-Path $RunDir "uvicorn.stderr.log"
$HealthUrl = "http://127.0.0.1:$Port/openapi.json"

function Ensure-RunDir {
  if (-not (Test-Path $RunDir)) {
    New-Item -ItemType Directory -Path $RunDir | Out-Null
  }
}

function Has-Command {
  param([string]$Name)
  return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Get-RunningBackendProcess {
  if (-not (Test-Path $PidFile)) {
    return $null
  }
  $backendPid = Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $backendPid) {
    return $null
  }
  return Get-Process -Id $backendPid -ErrorAction SilentlyContinue
}

function Get-PortProcess {
  param([int]$ListenPort)
  try {
    $conn = Get-NetTCPConnection -LocalAddress "127.0.0.1" -LocalPort $ListenPort -State Listen -ErrorAction Stop | Select-Object -First 1
    if (-not $conn) { return $null }
    return Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
  } catch {
    return $null
  }
}

function Ensure-DockerAndDb {
  if ($SkipDb) {
    Write-Host "SkipDb enabled: not starting PostgreSQL container."
    return
  }

  if (-not (Has-Command "docker")) {
    throw "docker not found in PATH. Please install Docker Desktop and retry."
  }
  & docker compose version *> $null
  if ($LASTEXITCODE -ne 0) {
    throw "docker compose unavailable. Open Docker Desktop and ensure compose is enabled."
  }

  & docker info *> $null
  if ($LASTEXITCODE -ne 0) {
    $dockerDesktop = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dockerDesktop) {
      Write-Host "Docker daemon not ready. Launching Docker Desktop..."
      Start-Process -FilePath $dockerDesktop | Out-Null
      Write-Host "Waiting for Docker daemon (up to 90s)..."
      $ready = $false
      for ($i = 0; $i -lt 45; $i++) {
        Start-Sleep -Seconds 2
        & docker info *> $null
        if ($LASTEXITCODE -eq 0) {
          $ready = $true
          break
        }
      }
      if (-not $ready) {
        throw "Docker Desktop launched but daemon still unavailable. Wait until Docker shows 'Engine running', then rerun script."
      }
    } else {
      throw "Docker daemon unavailable. Start Docker Desktop manually and rerun script."
    }
  }

  if (-not (Test-Path $ComposeFile)) {
    throw "docker-compose.yml not found: $ComposeFile"
  }

  Write-Host "Starting PostgreSQL container (db)..."
  & docker compose -f $ComposeFile up -d db
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to start db service via docker compose."
  }
}

function Stop-Backend {
  $proc = Get-RunningBackendProcess
  if ($proc) {
    Write-Host "Stopping backend process PID $($proc.Id)..."
    Stop-Process -Id $proc.Id -Force
  } else {
    $portProc = Get-PortProcess -ListenPort $Port
    if ($portProc) {
      Write-Host "Stopping process on port ${Port}: PID $($portProc.Id) ($($portProc.ProcessName))..."
      Stop-Process -Id $portProc.Id -Force
    } else {
      Write-Host "Backend process not running."
    }
  }
  if (Test-Path $PidFile) {
    Remove-Item $PidFile -Force
  }
}

function Start-Backend {
  Ensure-RunDir
  $current = Get-RunningBackendProcess
  if ($current) {
    Write-Host "Backend already running. PID: $($current.Id)"
    return
  }
  if (-not (Test-Path $BackendDir)) {
    throw "backend directory not found: $BackendDir"
  }

  Write-Host "Starting backend on http://127.0.0.1:$Port ..."
  if (-not (Test-Path $StdoutLogFile)) {
    New-Item -ItemType File -Path $StdoutLogFile -Force | Out-Null
  }
  if (-not (Test-Path $StderrLogFile)) {
    New-Item -ItemType File -Path $StderrLogFile -Force | Out-Null
  }
  $proc = Start-Process `
    -FilePath "python" `
    -ArgumentList "-m uvicorn app.main:app --host 127.0.0.1 --port $Port --reload" `
    -WorkingDirectory $BackendDir `
    -RedirectStandardOutput $StdoutLogFile `
    -RedirectStandardError $StderrLogFile `
    -PassThru

  Set-Content -Path $PidFile -Value $proc.Id -Encoding ASCII
  Start-Sleep -Seconds 2

  try {
    $resp = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 6
    Write-Host "Backend ready. Status: $($resp.StatusCode)"
  } catch {
    Write-Host "Backend process started but health check failed. Check log:"
    Write-Host "  $StdoutLogFile"
    Write-Host "  $StderrLogFile"
    throw $_
  }
}

function Show-Status {
  $proc = Get-RunningBackendProcess
  if ($proc) {
    Write-Host "Backend: RUNNING (PID $($proc.Id))"
  } else {
    $portProc = Get-PortProcess -ListenPort $Port
    if ($portProc) {
      Write-Host "Backend: RUNNING (external PID $($portProc.Id), $($portProc.ProcessName))"
    } else {
      Write-Host "Backend: STOPPED"
    }
  }

  try {
    $resp = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 4
    Write-Host "API health: HTTP $($resp.StatusCode)"
  } catch {
    Write-Host "API health: unreachable"
  }

  if ($SkipDb) {
    Write-Host "Docker db status: skipped"
  } elseif (Has-Command "docker") {
    Write-Host "Docker db status:"
    & docker info *> $null
    if ($LASTEXITCODE -eq 0) {
      & docker compose -f $ComposeFile ps db
    } else {
      Write-Host "Docker daemon not running."
    }
  } else {
    Write-Host "Docker not installed in PATH."
  }
}

try {
  switch ($Action) {
    "start" {
      Ensure-DockerAndDb
      Start-Backend
      Show-Status
    }
    "restart" {
      Ensure-DockerAndDb
      Stop-Backend
      Start-Backend
      Show-Status
    }
    "stop" {
      Stop-Backend
      Show-Status
    }
    "status" {
      Show-Status
    }
  }
} catch {
  Write-Error $_.Exception.Message
  exit 1
}

exit 0
