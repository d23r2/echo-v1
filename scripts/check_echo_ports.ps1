<#
.SYNOPSIS
    Identifies whatever is using ECHO's expected ports (8000 backend, 5174
    frontend) and reports whether the backend is actually healthy — never
    stops or modifies anything, purely diagnostic.

.EXAMPLE
    ./scripts/check_echo_ports.ps1
#>

$ErrorActionPreference = "Continue"

function Get-PortOwner {
    param([int]$Port)
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $conns) { return $null }
    $results = @()
    foreach ($conn in $conns) {
        $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
        if ($proc) {
            $results += [PSCustomObject]@{ PID = $conn.OwningProcess; Name = $proc.ProcessName }
        }
    }
    return $results
}

Write-Output "=== ECHO port check ==="
Write-Output ""

foreach ($portInfo in @(
    @{ Port = 8000; Label = "backend" },
    @{ Port = 5174; Label = "frontend" }
)) {
    $port = $portInfo.Port
    $label = $portInfo.Label
    $owners = Get-PortOwner -Port $port
    if (-not $owners) {
        Write-Output "Port $port ($label): free"
        continue
    }
    foreach ($owner in $owners) {
        Write-Output "Port $port ($label): in use by $($owner.Name) (PID $($owner.PID))"
    }
}

Write-Output ""
Write-Output "=== Backend health (http://localhost:8000) ==="
try {
    $resp = Invoke-WebRequest -Uri "http://localhost:8000/api/health" -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
    Write-Output "Backend responded: HTTP $($resp.StatusCode) - $($resp.Content)"
} catch {
    Write-Output "Backend did not respond on 8000 (either free, or occupied by something unhealthy): $($_.Exception.Message)"
}

Write-Output ""
Write-Output "=== Docker containers (if Docker is running) ==="
try {
    docker ps --format "table {{.Names}}\t{{.Ports}}\t{{.Status}}" 2>$null
} catch {
    Write-Output "Docker not available or not running."
}

Write-Output ""
Write-Output "Nothing was stopped or modified by this script."
