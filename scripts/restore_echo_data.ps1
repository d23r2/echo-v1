<#
.SYNOPSIS
    Restores ECHO's SQLite database and Chroma vector store from a backup
    produced by scripts/backup_echo_data.ps1.

.DESCRIPTION
    Destructive to the CURRENT backend/data/echo.db and backend/data/chroma —
    always makes a safety copy of whatever's currently there (suffixed
    .pre-restore-<timestamp>) before overwriting, and requires -Confirm:$false
    to skip the interactive prompt. Stop the backend before restoring so
    nothing is writing to the database mid-copy.

.EXAMPLE
    ./scripts/restore_echo_data.ps1 -BackupPath backend\data\backups\20260101-120000
#>
param(
    [Parameter(Mandatory=$true)]
    [string]$BackupPath,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$dataDir = Join-Path $repoRoot "backend\data"

if (-not (Test-Path $BackupPath)) {
    Write-Error "Backup path not found: $BackupPath"
    exit 1
}

$backupDb = Join-Path $BackupPath "echo.db"
$backupChroma = Join-Path $BackupPath "chroma"
if (-not (Test-Path $backupDb) -and -not (Test-Path $backupChroma)) {
    Write-Error "Neither echo.db nor a chroma/ directory found under $BackupPath — is this a valid backup folder?"
    exit 1
}

if (-not $Force) {
    Write-Warning "This will overwrite the CURRENT backend/data/echo.db and backend/data/chroma with the backup at:`n  $BackupPath"
    Write-Warning "Stop the ECHO backend first — restoring while it's running can corrupt the database."
    $answer = Read-Host "Type 'yes' to continue"
    if ($answer -ne "yes") {
        Write-Output "Cancelled — nothing was changed."
        exit 0
    }
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$safetyDir = Join-Path $dataDir "pre-restore-$timestamp"
New-Item -ItemType Directory -Force -Path $safetyDir | Out-Null

$currentDb = Join-Path $dataDir "echo.db"
if (Test-Path $currentDb) {
    Copy-Item $currentDb (Join-Path $safetyDir "echo.db")
}
$currentChroma = Join-Path $dataDir "chroma"
if (Test-Path $currentChroma) {
    Copy-Item $currentChroma (Join-Path $safetyDir "chroma") -Recurse
}
Write-Output "Safety copy of current data saved to: $safetyDir"

if (Test-Path $backupDb) {
    Copy-Item $backupDb $currentDb -Force
    Write-Output "Restored echo.db."
}
if (Test-Path $backupChroma) {
    if (Test-Path $currentChroma) {
        Remove-Item $currentChroma -Recurse -Force -Confirm:$false
    }
    Copy-Item $backupChroma $currentChroma -Recurse
    Write-Output "Restored Chroma vector store."
}

Write-Output ""
Write-Output "Restore complete. Start the backend and confirm ECHO loads correctly."
Write-Output "If something looks wrong, the pre-restore state is saved at: $safetyDir"
