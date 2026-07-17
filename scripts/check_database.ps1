<#
.SYNOPSIS
    Read-only integrity check for ECHO's SQLite database — never modifies
    anything. Runs SQLite's own PRAGMA integrity_check plus a quick sanity
    read of required tables and the schema_version marker.

.EXAMPLE
    ./scripts/check_database.ps1
#>
param(
    [string]$DatabasePath
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$dbPath = if ($DatabasePath) { $DatabasePath } else { Join-Path $repoRoot "backend\data\echo.db" }

if (-not (Test-Path $dbPath)) {
    Write-Error "No database found at $dbPath - has the backend run at least once?"
    exit 1
}

$venvPython = Join-Path $repoRoot "backend\.venv\Scripts\python.exe"
$pythonExe = "python"
if (Test-Path $venvPython) {
    $pythonExe = $venvPython
} else {
    Write-Warning "backend/.venv not found - falling back to system 'python'."
}

Write-Output "Checking database: $dbPath"
Write-Output "Using interpreter: $pythonExe"
Write-Output ""

$pyScript = @'
import sqlite3
import sys

db_path = sys.argv[1]
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("PRAGMA integrity_check")
result = cursor.fetchone()[0]
print(f"Integrity check: {result}")

cursor.execute("PRAGMA foreign_key_check")
fk_problems = cursor.fetchall()
print(f"Foreign key violations: {len(fk_problems)}")
if fk_problems:
    for problem in fk_problems[:10]:
        print(f"  {problem}")

required_tables = ["conversations", "messages", "atlas_entries"]
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
existing = {row[0] for row in cursor.fetchall()}
missing = [t for t in required_tables if t not in existing]
print(f"Required tables present: {len(required_tables) - len(missing)}/{len(required_tables)}")
if missing:
    print(f"  Missing: {missing}")

try:
    cursor.execute("SELECT version FROM schema_version LIMIT 1")
    row = cursor.fetchone()
    print(f"Schema version: {row[0] if row else 'no row'}")
except sqlite3.OperationalError:
    print("Schema version: table not present (pre-Layer-0 database)")

cursor.execute("SELECT COUNT(*) FROM conversations")
print(f"Conversations: {cursor.fetchone()[0]}")
cursor.execute("SELECT COUNT(*) FROM messages")
print(f"Messages: {cursor.fetchone()[0]}")

conn.close()
sys.exit(0 if result == "ok" and not fk_problems and not missing else 1)
'@

$tempScriptPath = Join-Path $env:TEMP "echo_check_database.py"
[System.IO.File]::WriteAllText($tempScriptPath, $pyScript)

& $pythonExe $tempScriptPath $dbPath
$exitCode = $LASTEXITCODE

Remove-Item $tempScriptPath -Force -ErrorAction SilentlyContinue

Write-Output ""
if ($exitCode -eq 0) {
    Write-Output "Database check: OK"
} else {
    Write-Warning "Database check found problems - see above. Consider restoring from a backup (scripts/restore_echo_data.ps1) if this is unexpected."
}
exit $exitCode
