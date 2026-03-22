param(
  [ValidateSet("start", "restart", "stop", "status", "logs")]
  [string]$Action = "start",
  [int]$Port = 8000,
  [int]$LogTail = 200,
  [switch]$NoBuild
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Resolve-Path (Join-Path $ScriptDir "..")
$ComposeFile = Join-Path $RootDir "docker-compose.yml"
$HealthUrl = "http://127.0.0.1:$Port/openapi.json"
$GraphHealthUrl = "http://127.0.0.1:22024/docs"

function Ensure-ComposeFile {
  if (-not (Test-Path $ComposeFile)) {
    throw "docker-compose.yml not found: $ComposeFile"
  }
}

function Ensure-Docker {
  if ($null -eq (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "docker not found in PATH."
  }
  & docker compose version *> $null
  if ($LASTEXITCODE -ne 0) {
    throw "docker compose unavailable. Please install/enable Docker Compose."
  }
  & docker info *> $null
  if ($LASTEXITCODE -ne 0) {
    throw "docker daemon is not running."
  }
}

function Compose-Up {
  if ($NoBuild) {
    & docker compose -f $ComposeFile up -d
  } else {
    & docker compose -f $ComposeFile up -d --build
  }
  if ($LASTEXITCODE -ne 0) {
    throw "docker compose up failed."
  }
}

function Compose-Stop {
  & docker compose -f $ComposeFile stop
  if ($LASTEXITCODE -ne 0) {
    throw "docker compose stop failed."
  }
}

function Compose-Logs {
  & docker compose -f $ComposeFile logs -f --tail=$LogTail api langgraph
}

function Show-Status {
  & docker compose -f $ComposeFile ps api langgraph db
  try {
    $resp = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 5
    Write-Host "API health: HTTP $($resp.StatusCode)"
  } catch {
    Write-Host "API health: unreachable ($HealthUrl)"
  }
  try {
    $graphResp = Invoke-WebRequest -Uri $GraphHealthUrl -UseBasicParsing -TimeoutSec 5
    Write-Host "LangGraph health: HTTP $($graphResp.StatusCode)"
  } catch {
    Write-Host "LangGraph health: unreachable ($GraphHealthUrl)"
  }
}

try {
  Ensure-ComposeFile
  Ensure-Docker

  switch ($Action) {
    "start" {
      Compose-Up
      Show-Status
    }
    "restart" {
      Compose-Up
      Show-Status
    }
    "stop" {
      Compose-Stop
      Show-Status
    }
    "status" {
      Show-Status
    }
    "logs" {
      Compose-Logs
    }
  }
} catch {
  Write-Error $_.Exception.Message
  exit 1
}

exit 0
