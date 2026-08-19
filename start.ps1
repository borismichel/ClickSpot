#Requires -Version 5.1
<#
.SYNOPSIS
    Windows sibling of start.sh: starts ClickHouse, FastAPI, Dagster, and the
    frontend dev server, and kills the whole process tree on Ctrl+C.

.NOTES
    If script execution is blocked, run once with
        powershell -ExecutionPolicy Bypass -File start.ps1
    or unblock your user scope permanently:
        Set-ExecutionPolicy RemoteSigned -Scope CurrentUser

    ClickHouse modes (CLICKSPOT_CLICKHOUSE_MODE in .env): docker (default on
    Windows, needs Docker Desktop) or external. The Docker-free "local" mode is
    Linux-only -- use WSL with ./start.sh if you want it.
#>

$ErrorActionPreference = 'Stop'

$Root = $PSScriptRoot
Set-Location $Root

function Log([string]$msg)  { Write-Host "[start] $msg" -ForegroundColor Green }
function Warn([string]$msg) { Write-Host "[start] $msg" -ForegroundColor Yellow }
function Err([string]$msg)  { Write-Host "[start] $msg" -ForegroundColor Red }

# ---------- Load .env ----------
if (Test-Path (Join-Path $Root '.env')) {
    foreach ($line in Get-Content (Join-Path $Root '.env')) {
        $line = $line.Trim()
        if ($line -eq '' -or $line.StartsWith('#')) { continue }
        $eq = $line.IndexOf('=')
        if ($eq -lt 1) { continue }
        $key = $line.Substring(0, $eq).Trim()
        $val = $line.Substring($eq + 1).Trim()
        if ($val.Length -ge 2) {
            $first = $val.Substring(0, 1)
            $last = $val.Substring($val.Length - 1, 1)
            if (($first -eq '"' -and $last -eq '"') -or ($first -eq "'" -and $last -eq "'")) {
                $val = $val.Substring(1, $val.Length - 2)
            }
        }
        Set-Item -Path "Env:$key" -Value $val
    }
}

# ---------- Activate project venv ----------
$Activate = Join-Path $Root '.venv\Scripts\Activate.ps1'
if (Test-Path $Activate) {
    . $Activate
} else {
    Warn ".venv\Scripts\Activate.ps1 not found -- using python/uvicorn/dagster from PATH."
    Warn "Create the venv with: python -m venv .venv; .venv\Scripts\pip install -e `".[dev]`""
}

# ---------- Ensure DAGSTER_HOME exists ----------
if (-not $env:DAGSTER_HOME) { $env:DAGSTER_HOME = Join-Path $Root '.dagster_home' }
New-Item -ItemType Directory -Force -Path $env:DAGSTER_HOME | Out-Null

# ---------- 1. ClickHouse ----------
# Windows default is the ClickHouse container: the single-binary auto-download
# behind "local" mode has no Windows build. Override with CLICKSPOT_CLICKHOUSE_MODE.
$Mode = 'docker'
if ($env:CLICKSPOT_CLICKHOUSE_MODE) { $Mode = $env:CLICKSPOT_CLICKHOUSE_MODE }

$ChHost = 'localhost'
if ($env:CLICKHOUSE_HOST) { $ChHost = $env:CLICKHOUSE_HOST }
$ChPort = '8124'
if ($env:CLICKHOUSE_PORT) { $ChPort = $env:CLICKHOUSE_PORT }
$PingUrl = "http://${ChHost}:${ChPort}/ping"

function Test-ClickHouse {
    try {
        $resp = Invoke-WebRequest -Uri $PingUrl -UseBasicParsing -TimeoutSec 2
        return ($resp.StatusCode -eq 200)
    } catch {
        return $false
    }
}

Log "Starting ClickHouse ($Mode)..."
switch ($Mode) {
    'docker' {
        # cmd /c wrappers: redirecting a native command's stderr directly in
        # PowerShell 5.1 turns stderr lines into terminating errors under
        # $ErrorActionPreference = 'Stop'.
        cmd /c "docker info >NUL 2>&1"
        if ($LASTEXITCODE -ne 0) {
            Err "Docker isn't running. Start Docker Desktop and retry, or set"
            Err "CLICKSPOT_CLICKHOUSE_MODE=external in .env to point at your own ClickHouse."
            exit 1
        }
        # Only the clickhouse service: start.ps1 runs FastAPI/Dagster/frontend on
        # the host, so bringing up the full compose stack would double-bind their ports.
        $running = cmd /c "docker compose ps --status running clickhouse 2>NUL" | Select-String 'clickhouse'
        if ($running) {
            Log "ClickHouse container already running"
        } else {
            docker compose up -d clickhouse
            if ($LASTEXITCODE -ne 0) {
                Err "docker compose up -d clickhouse failed"
                exit 1
            }
        }
    }
    'external' {
        Log "Using external ClickHouse at ${ChHost}:${ChPort}"
    }
    'local' {
        Err "CLICKSPOT_CLICKHOUSE_MODE=local is Linux-only (no Windows build of the"
        Err "single-binary auto-download). Use WSL with ./start.sh, or set the mode"
        Err "to docker or external in .env."
        exit 1
    }
    default {
        Err "Unknown CLICKSPOT_CLICKHOUSE_MODE=$Mode (expected docker or external on Windows)"
        exit 1
    }
}

# Wait for ClickHouse to accept connections in every mode.
Log "Waiting for ClickHouse..."
$Ready = $false
for ($i = 0; $i -lt 60; $i++) {
    if (Test-ClickHouse) { $Ready = $true; break }
    Start-Sleep -Seconds 1
}
if (-not $Ready) {
    Err "ClickHouse is not reachable at ${ChHost}:${ChPort}"
    exit 1
}
Log "ClickHouse ready on port $ChPort"

# ---------- 2. Init schemas (idempotent) ----------
Log "Ensuring ClickHouse schemas..."
python (Join-Path $Root 'scripts\init_clickhouse.py')
if ($LASTEXITCODE -ne 0) {
    Err "scripts\init_clickhouse.py failed"
    exit 1
}

# ---------- 2a. Customer config hint (first-run portal setup) ----------
if (-not (Test-Path (Join-Path $HOME '.clickspot\customer.json'))) {
    Warn "No ~\.clickspot\customer.json found."
    Warn "On first run, the LLM will produce generic SQL without portal-specific filters."
    Warn "After bronze+silver load, run: python -m app.customer.onboarding"
    Warn "to walk through pipelines / main pipeline / canonical revenue column."
}

# ---------- 3-5. Services (uvicorn, dagster, vite) ----------
$Procs = @()
try {
    Log "Starting FastAPI on :8192..."
    $Procs += Start-Process -FilePath 'uvicorn' `
        -ArgumentList 'app.main:app', '--host', '0.0.0.0', '--port', '8192', '--reload', '--log-level', 'info' `
        -WorkingDirectory $Root -NoNewWindow -PassThru

    Log "Starting Dagster on :8194..."
    $Procs += Start-Process -FilePath 'dagster' `
        -ArgumentList 'dev', '-p', '8194' `
        -WorkingDirectory $Root -NoNewWindow -PassThru

    Log "Starting frontend on :8193..."
    $Frontend = Join-Path $Root 'frontend'
    Push-Location $Frontend
    try {
        & npm install --silent
        if ($LASTEXITCODE -ne 0) { throw "npm install failed" }
    } finally {
        Pop-Location
    }
    # Via cmd /c so taskkill /T can reach the node process npx.cmd spawns.
    $Procs += Start-Process -FilePath 'cmd' `
        -ArgumentList '/c', 'npx vite --port 8193' `
        -WorkingDirectory $Frontend -NoNewWindow -PassThru

    Write-Host ''
    Log 'All services running:'
    Log "  ClickHouse  -> http://localhost:$ChPort"
    Log '  FastAPI     -> http://localhost:8192'
    Log '  Dagster     -> http://localhost:8194'
    Log '  Frontend    -> http://localhost:8193'
    Write-Host ''
    Log 'Press Ctrl+C to stop all services'

    # -InputObject (not -Id): waiting on held Process objects can't throw the
    # "process not found" error -Id hits when a service exits before we get here.
    Wait-Process -InputObject $Procs
} finally {
    Write-Host ''
    Log 'Shutting down...'
    foreach ($p in $Procs) {
        if ($p -and -not $p.HasExited) {
            # /T kills the whole child tree (vite's node, dagster's workers).
            cmd /c "taskkill /PID $($p.Id) /T /F >NUL 2>&1"
        }
    }
    Log 'Done.'
}
