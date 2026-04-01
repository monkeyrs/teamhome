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

function Set-ComposeEnvironment {
  $env:POSTGRES_DB = Get-DotEnvValue -Key "POSTGRES_DB" -Default "teamhome"
  $env:POSTGRES_USER = Get-DotEnvValue -Key "POSTGRES_USER" -Default "admin"
  $env:POSTGRES_PASSWORD = Get-DotEnvValue -Key "POSTGRES_PASSWORD" -Default "admin"
  $defaultDatabaseUrl = "postgresql+psycopg2://$($env:POSTGRES_USER):$($env:POSTGRES_PASSWORD)@db:5432/$($env:POSTGRES_DB)"
  $env:DATABASE_URL = Get-DotEnvValue -Key "DATABASE_URL" -Default $defaultDatabaseUrl
  $env:LANGGRAPH_HOST_PORT = Get-DotEnvValue -Key "LANGGRAPH_HOST_PORT" -Default "22024"
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

function Get-DemoSeedMode {
  $configured = (Get-DotEnvValue -Key "DEMO_SEED_MODE" -Default "").ToLowerInvariant()
  if (-not [string]::IsNullOrWhiteSpace($configured)) {
    return $configured
  }
  return "auto"
}

function Get-ApiContainerName {
  $containerId = (& docker compose -f $ComposeFile ps -q api 2>$null | Select-Object -First 1)
  if (-not [string]::IsNullOrWhiteSpace($containerId)) {
    $resolved = (& docker inspect --format "{{.Name}}" $containerId 2>$null)
    if (-not [string]::IsNullOrWhiteSpace($resolved)) {
      return $resolved.TrimStart("/")
    }
  }
  return ""
}

function Invoke-InApiContainer {
  param(
    [string]$Command
  )

  $container = Get-ApiContainerName
  if (-not [string]::IsNullOrWhiteSpace($container)) {
    & docker exec $container sh -lc $Command
    return
  }

  & docker compose -f $ComposeFile run --rm api sh -lc $Command
}

function Invoke-DemoSeed {
  if ((Get-DemoSeedMode) -ne "auto") {
    Write-Host "Demo seed step: skipped"
    return
  }

  Invoke-InApiContainer "DEMO_SEED_MODE=manual python -m app.commands.seed_demo_data"
  $exitCode = $LASTEXITCODE
  if ($exitCode -ne 0) {
    throw "demo seed failed."
  }
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

  & docker compose -f $ComposeFile up -d api langgraph
  if ($LASTEXITCODE -ne 0) {
    throw "docker compose up for api/langgraph failed."
  }

  Invoke-InApiContainer "alembic upgrade head"
  $exitCode = $LASTEXITCODE
  if ($exitCode -ne 0) {
    throw "database migrations failed."
  }

  Invoke-DemoSeed

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
  Invoke-InApiContainer "alembic current"
  $exitCode = $LASTEXITCODE
  if ($exitCode -eq 0) {
    Write-Host "Database migrations: current"
  } else {
    Write-Host "Database migrations: unavailable"
  }
  Write-Host "Demo seed mode: $(Get-DemoSeedMode)"
  try {
    $resp = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 5
    Write-Host "API health: HTTP $($resp.StatusCode)"
    $openapi = $resp.Content | ConvertFrom-Json
    if ($openapi.paths.PSObject.Properties.Name -contains "/timeline") {
      Write-Host "Timeline route: OK"
    } else {
      Write-Host "Timeline route: MISSING"
    }
    if ($openapi.paths.PSObject.Properties.Name -contains "/teams") {
      Write-Host "Team bootstrap route: OK"
    } else {
      Write-Host "Team bootstrap route: MISSING"
    }
  } catch {
    Write-Host "API health: unreachable ($HealthUrl)"
  }
  try {
    $graphPort = Get-DotEnvValue -Key "LANGGRAPH_HOST_PORT" -Default "22024"
    $graphHealthUrl = "http://127.0.0.1:$graphPort/docs"
    $graphResp = Invoke-WebRequest -Uri $graphHealthUrl -UseBasicParsing -TimeoutSec 5
    Write-Host "LangGraph health: HTTP $($graphResp.StatusCode)"
  } catch {
    $graphPort = Get-DotEnvValue -Key "LANGGRAPH_HOST_PORT" -Default "22024"
    Write-Host "LangGraph health: unreachable (http://127.0.0.1:$graphPort/docs)"
  }
}

try {
  Ensure-ComposeFile
  Ensure-Docker
  Set-ComposeEnvironment

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
