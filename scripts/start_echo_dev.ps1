<#
.SYNOPSIS
    Starts ECHO's local dev environment safely: reuses a healthy backend on
    port 8000 if one is already running (e.g. via Docker Compose), starts
    the backend only if the port is genuinely free, and never kills or
    silently reassigns an occupied-but-unhealthy port 8000 to something
    else (see check_echo_ports.ps1 for read-only diagnosis of that case).

.DESCRIPTION
    Case A: 8000 already healthy (e.g. Docker) -> reuse it, start only the
            frontend on 5174.
    Case B: 8000 free -> start the backend (backend/.venv) on 8000, then
            the frontend on 5174.
    Case C: 8000 occupied but NOT healthy -> stop, report the owning
            process, and ask you to resolve it manually. This script never
            force-kills a process it didn't start.

.EXAMPLE
    ./scripts/start_echo_dev.ps1
#>

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

function Test-BackendHealthy {
    try {
        $resp = Invoke-WebRequest -Uri "http://localhost:8000/api/health" -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
        return $resp.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Get-Port8000Owner {
    $conns = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
    if (-not $conns) { return $null }
    $conn = $conns | Select-Object -First 1
    $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
    if ($proc) { return "$($proc.ProcessName) (PID $($conn.OwningProcess))" }
    return "PID $($conn.OwningProcess)"
}

Write-Output "=== ECHO dev startup ==="
Write-Output ""

$port8000Owner = Get-Port8000Owner

if ($port8000Owner) {
    if (Test-BackendHealthy) {
        Write-Output "Case A: port 8000 is already serving a healthy ECHO backend ($port8000Owner) - reusing it."
    } else {
        Write-Warning "Case C: port 8000 is occupied by $port8000Owner but did not respond to a health check."
        Write-Warning "This script will NOT kill it. Investigate with scripts/check_echo_ports.ps1, resolve manually, then re-run this script."
        exit 1
    }
} else {
    Write-Output "Case B: port 8000 is free - starting the backend."
    $venvPython = Join-Path $repoRoot "backend\.venv\Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        Write-Error "backend/.venv not found at $venvPython - set up the backend venv first (see DEVELOPMENT.md)."
        exit 1
    }
    Start-Process -FilePath $venvPython `
        -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "backend") `
        -WorkingDirectory $repoRoot `
        -WindowStyle Normal
    Write-Output "Backend starting in a new window - waiting for it to become healthy..."
    $attempts = 0
    while (-not (Test-BackendHealthy) -and $attempts -lt 20) {
        Start-Sleep -Milliseconds 500
        $attempts++
    }
    if (Test-BackendHealthy) {
        Write-Output "Backend is healthy on http://localhost:8000"
    } else {
        Write-Warning "Backend did not report healthy within 10s - check its window for errors."
    }
}

Write-Output ""
Write-Output "Starting frontend on port 5174..."
$frontendDir = Join-Path $repoRoot "frontend"
Start-Process -FilePath "npm" -ArgumentList @("run", "dev") -WorkingDirectory $frontendDir -WindowStyle Normal

Write-Output ""
Write-Output "=== URLs ==="
Write-Output "Backend:  http://localhost:8000"
Write-Output "Frontend: http://localhost:5174"
Write-Output ""
Write-Output "Frontend was started in a new window - watch it for the 'ready' message."
