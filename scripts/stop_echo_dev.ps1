<#
.SYNOPSIS
    Stops ECHO dev processes started by start_echo_dev.ps1 (a local uvicorn
    on 8000, a local `npm run dev` on 5174) — identifies them by command
    line before stopping, and NEVER touches Docker containers or a process
    it can't positively identify as an ECHO dev process. If port 8000 is
    owned by Docker (com.docker.backend / wslrelay), this script leaves it
    alone and says so.

.EXAMPLE
    ./scripts/stop_echo_dev.ps1
#>

$ErrorActionPreference = "Continue"

function Stop-IfIdentifiable {
    param([int]$Port, [string]$ExpectedCommandLineSubstring, [string]$Label)

    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $conns) {
        Write-Output "$Label (port $Port): nothing listening - nothing to stop."
        return
    }

    foreach ($conn in $conns) {
        $procId = $conn.OwningProcess
        $wmiProc = Get-CimInstance Win32_Process -Filter "ProcessId = $procId" -ErrorAction SilentlyContinue
        if (-not $wmiProc) {
            Write-Warning "$Label (port $Port): PID $procId - could not read its command line, leaving it alone."
            continue
        }
        if ($wmiProc.Name -match "docker|wslrelay|com.docker") {
            Write-Output "$Label (port $Port): owned by $($wmiProc.Name) (Docker) - leaving it alone, this script never touches Docker."
            continue
        }
        if ($wmiProc.CommandLine -and $wmiProc.CommandLine -like "*$ExpectedCommandLineSubstring*") {
            Write-Output "$Label (port $Port): stopping $($wmiProc.Name) (PID $procId) - confirmed ECHO dev process by command line."
            Stop-Process -Id $procId -Force -Confirm:$false
        } else {
            Write-Warning "$Label (port $Port): PID $procId ($($wmiProc.Name)) does not look like an ECHO dev process (command line: $($wmiProc.CommandLine)) - leaving it alone. Stop it manually if you're sure."
        }
    }
}

Write-Output "=== Stopping ECHO dev processes ==="
Write-Output ""
Stop-IfIdentifiable -Port 8000 -ExpectedCommandLineSubstring "uvicorn" -Label "Backend"
Stop-IfIdentifiable -Port 5174 -ExpectedCommandLineSubstring "vite" -Label "Frontend"
Write-Output ""
Write-Output "Done. Docker containers (if any) were never touched by this script."
