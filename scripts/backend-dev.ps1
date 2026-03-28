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
$EnvFile = Join-Path $RootDir "backend\\.env"
$HealthUrl = "http://127.0.0.1:$Port/openapi.json"
$GraphHealthUrl = "http://127.0.0.1:22024/docs"

$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

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

function Get-DotEnvValue {
  param(
    [string]$Key,
    [string]$Default = ""
  )

  if (-not (Test-Path $EnvFile)) {
    return $Default
  }

  $line = Get-Content $EnvFile | Where-Object { $_ -match "^\s*$Key\s*=" } | Select-Object -Last 1
  if ($null -eq $line) {
    return $Default
  }

  $value = ($line -replace "^\s*$Key\s*=\s*", "").Trim()
  if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) {
    $value = $value.Substring(1, $value.Length - 2)
  }
  return $value
}

function Test-BackendSecurityConfig {
  if (-not (Test-Path $EnvFile)) {
    throw "backend/.env not found: $EnvFile"
  }

  $environment = (Get-DotEnvValue -Key "ENVIRONMENT" -Default "development").ToLowerInvariant()
  if ($environment -ne "production") {
    Write-Host "Backend security preflight: ENVIRONMENT=$environment"
    return
  }

  $issues = [System.Collections.Generic.List[string]]::new()
  $jwtSecret = Get-DotEnvValue -Key "JWT_SECRET"
  if ([string]::IsNullOrWhiteSpace($jwtSecret) -or $jwtSecret -eq "dev-secret-change-me" -or $jwtSecret.Length -lt 32) {
    $issues.Add("JWT_SECRET must be a non-default value with at least 32 characters.")
  }

  $corsOrigins = Get-DotEnvValue -Key "CORS_ALLOW_ORIGINS" -Default "*"
  if ($corsOrigins -match '\*') {
    $issues.Add("CORS_ALLOW_ORIGINS must not contain '*'.")
  }

  if ([string]::IsNullOrWhiteSpace((Get-DotEnvValue -Key "WECHAT_APPID"))) {
    $issues.Add("WECHAT_APPID is required.")
  }
  if ([string]::IsNullOrWhiteSpace((Get-DotEnvValue -Key "WECHAT_SECRET"))) {
    $issues.Add("WECHAT_SECRET is required.")
  }

  $allowInsecureDevAuth = (Get-DotEnvValue -Key "ALLOW_INSECURE_DEV_AUTH" -Default "false").ToLowerInvariant()
  if ($allowInsecureDevAuth -eq "true") {
    $issues.Add("ALLOW_INSECURE_DEV_AUTH must be false.")
  }

  $enableDebugEndpoints = (Get-DotEnvValue -Key "ENABLE_DEBUG_ENDPOINTS" -Default "false").ToLowerInvariant()
  if ($enableDebugEndpoints -eq "true") {
    $issues.Add("ENABLE_DEBUG_ENDPOINTS must be false.")
  }

  if ($issues.Count -gt 0) {
    throw ("Unsafe production backend config in backend/.env: " + ($issues -join " "))
  }

  Write-Host "Backend security preflight: production config OK"
}

function Compose-Up {
  & docker compose -f $ComposeFile up -d db
  if ($LASTEXITCODE -ne 0) {
    throw "docker compose up for db failed."
  }

  if (-not $NoBuild) {
    & docker compose -f $ComposeFile build api langgraph
    if ($LASTEXITCODE -ne 0) {
      throw "docker compose build failed."
    }
  }

  & docker compose -f $ComposeFile run --rm api alembic upgrade head
  if ($LASTEXITCODE -ne 0) {
    throw "database migrations failed."
  }

  & docker compose -f $ComposeFile up -d --force-recreate api langgraph
  if ($LASTEXITCODE -ne 0) {
    throw "docker compose up failed. If images already exist and the build step is blocked by network/auth issues, retry with -NoBuild."
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
  & docker compose -f $ComposeFile run --rm api alembic current
  if ($LASTEXITCODE -eq 0) {
    Write-Host "Database migrations: current"
  } else {
    Write-Host "Database migrations: unavailable"
  }
  try {
    $resp = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 5
    Write-Host "API health: HTTP $($resp.StatusCode)"
    $openapi = $resp.Content | ConvertFrom-Json
    if ($openapi.paths.PSObject.Properties.Name -contains "/timeline") {
      Write-Host "Timeline route: OK"
    } else {
      Write-Host "Timeline route: MISSING"
    }
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
      Test-BackendSecurityConfig
      Compose-Up
      Show-Status
    }
    "restart" {
      Test-BackendSecurityConfig
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
