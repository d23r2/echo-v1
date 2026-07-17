<#
.SYNOPSIS
    Backs up ECHO's local data: the SQLite database and the Chroma vector
    store. Never touches backend/.env (secrets) unless -IncludeEnvTemplate
    is passed, and even then only copies backend/.env.example (a template
    with no real values), never the real backend/.env.

.DESCRIPTION
    Layer 0 (ECHO_LAYER_0_INFRASTRUCTURE_FOUNDATION.md) — run this before any
    schema change or risky operation. Output goes to
    backend/data/backups/<timestamp>/ by default (already git-ignored via
    backend/data/ in .gitignore) or -OutputPath if given.

.EXAMPLE
    ./scripts/backup_echo_data.ps1
    ./scripts/backup_echo_data.ps1 -OutputPath D:\echo-backups
#>
param(
    [string]$OutputPath,
    [switch]$IncludeEnvTemplate
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$dataDir = Join-Path $repoRoot "backend\data"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$destRoot = if ($OutputPath) { $OutputPath } else { Join-Path $dataDir "backups" }
$dest = Join-Path $destRoot $timestamp

if (-not (Test-Path $dataDir)) {
    Write-Error "No backend/data directory found at $dataDir — nothing to back up yet (has the backend ever run?)."
    exit 1
}

New-Item -ItemType Directory -Force -Path $dest | Out-Null

$dbPath = Join-Path $dataDir "echo.db"
if (Test-Path $dbPath) {
    Copy-Item $dbPath (Join-Path $dest "echo.db")
    Write-Output "Backed up database: echo.db"
} else {
    Write-Warning "No echo.db found at $dbPath — skipping (fresh install with no data yet?)."
}

$chromaPath = Join-Path $dataDir "chroma"
if (Test-Path $chromaPath) {
    Copy-Item $chromaPath (Join-Path $dest "chroma") -Recurse
    Write-Output "Backed up Chroma vector store."
} else {
    Write-Warning "No Chroma directory found at $chromaPath — skipping."
}

if ($IncludeEnvTemplate) {
    $envExample = Join-Path $repoRoot "backend\.env.example"
    if (Test-Path $envExample) {
        Copy-Item $envExample (Join-Path $dest ".env.example")
        Write-Output "Included backend/.env.example (template only — no secrets)."
    }
}

Write-Output ""
Write-Output "Backup complete: $dest"
Write-Output "Restore with: ./scripts/restore_echo_data.ps1 -BackupPath `"$dest`""
