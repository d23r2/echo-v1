<#
.SYNOPSIS
    Scans git-TRACKED files (never untracked/ignored ones — those are a
    separate concern) for patterns that look like real secrets, before a
    push. Read-only — never modifies anything, never deletes history.

.DESCRIPTION
    Checks: sk-... style API keys, Bearer tokens, generic api_key/secret/
    password/token assignments with a long value, PEM private key headers.
    Deliberately excludes *.example files and this repo's own known-safe
    documentation patterns (variable NAMES with no value) to keep false
    positives low - see ECHO_LAYER_0_INFRASTRUCTURE_FOUNDATION.md's
    security section for what "safe" means here.

.EXAMPLE
    ./scripts/check_secrets.ps1
#>

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$trackedFiles = git ls-files
if (-not $trackedFiles) {
    Write-Error "git ls-files returned nothing - is this a git repository?"
    exit 1
}

# (pattern, description) — checked against tracked file CONTENT, not
# filenames. Patterns look for an actual value, not just a variable name,
# to keep false positives low against this repo's own docs (which
# legitimately mention "ANTHROPIC_API_KEY" by name constantly).
$patterns = @(
    @{ Pattern = 'sk-[A-Za-z0-9_-]{20,}'; Description = "sk-... style API key" }
    @{ Pattern = 'Bearer\s+[A-Za-z0-9._-]{20,}'; Description = "Bearer token" }
    @{ Pattern = '-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'; Description = "private key block" }
    @{ Pattern = '(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*["'']([A-Za-z0-9_\-]{16,})["'']'; Description = "assigned secret-like value" }
)

# Files where a bare variable NAME (no real value) is expected and safe —
# skip these entirely rather than trying to distinguish name-only mentions
# line by line, which is what causes most false-positive noise in a repo
# this well-documented.
$skipFiles = @(
    "*.example"
    "*README*.md"
    "*DEVELOPMENT*.md"
    "*ECHO_*.md"
    "PROGRESS.md"
    "docs/*"
)

function Test-ShouldSkip {
    param([string]$Path)
    foreach ($pattern in $skipFiles) {
        if ($Path -like $pattern) { return $true }
    }
    return $false
}

$findings = @()

foreach ($file in $trackedFiles) {
    if (Test-ShouldSkip -Path $file) { continue }
    $fullPath = Join-Path $repoRoot $file
    if (-not (Test-Path $fullPath -PathType Leaf)) { continue }

    try {
        $content = Get-Content -Path $fullPath -Raw -ErrorAction Stop
    } catch {
        continue  # binary file or unreadable - skip rather than fail the whole scan
    }
    if (-not $content) { continue }

    foreach ($p in $patterns) {
        $matches = [regex]::Matches($content, $p.Pattern)
        foreach ($m in $matches) {
            $findings += [PSCustomObject]@{
                File        = $file
                Description = $p.Description
                Snippet     = ($m.Value.Substring(0, [Math]::Min(40, $m.Value.Length)) + "...")
            }
        }
    }
}

Write-Output "=== ECHO secret scan ==="
Write-Output "Scanned $($trackedFiles.Count) tracked files."
Write-Output ""

if ($findings.Count -eq 0) {
    Write-Output "No likely secrets found in tracked files."
    exit 0
}

Write-Warning "Found $($findings.Count) potential secret(s):"
foreach ($f in $findings) {
    Write-Output "  FILE: $($f.File)"
    Write-Output "  TYPE: $($f.Description)"
    Write-Output "  SNIPPET: $($f.Snippet)"
    Write-Output ""
}
Write-Warning "STOP - do not push until these are resolved. If real, rotate the key immediately and remove it from tracked files (a new commit is not enough if it was ever pushed - the key must be rotated)."
exit 1
