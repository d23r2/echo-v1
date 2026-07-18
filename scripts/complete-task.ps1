<#
Archives tasks/ACTIVE_TASK.md into tasks/completed/ and resets it to the empty
convention -- but only when Status is exactly Completed.

Completed means the user has already merged the change and explicitly authorized
this status. It is never set by an agent, and it is not the same as Verified
(reviewer-approved, still awaiting the user's merge decision). This script
refuses to archive anything else: Draft, Ready, In progress, Ready for review,
Changes requested, Blocked, or Verified.
#>
param(
    [string]$TaskId = ''
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$activeTask = Join-Path $root 'tasks/ACTIVE_TASK.md'
$completedDir = Join-Path $root 'tasks/completed'

if (-not (Test-Path $activeTask)) {
    throw "Active task not found: $activeTask"
}

$content = Get-Content $activeTask -Raw

if ($content -match 'Status:\s*\*\*No task loaded\*\*') {
    throw 'There is no active task to archive.'
}

if ($content -notmatch 'Status:\s*\*\*Completed\*\*') {
    $statusMatch = [regex]::Match($content, 'Status:\s*\*\*([^*]+)\*\*')
    $currentStatus = if ($statusMatch.Success) { $statusMatch.Groups[1].Value.Trim() } else { 'Unknown' }
    throw "Refusing to archive: Status is '$currentStatus', not Completed. 'Verified' means the reviewer approved the work but the user has not yet merged -- only the user sets Completed, and only after merging."
}

if (-not (Test-Path $completedDir)) {
    New-Item -ItemType Directory -Path $completedDir -Force | Out-Null
}

if ([string]::IsNullOrWhiteSpace($TaskId)) {
    if ($content -match 'Task ID:\s*`?([^`\r\n]+)`?') {
        $TaskId = $Matches[1].Trim()
    } else {
        throw 'Could not determine Task ID. Pass -TaskId explicitly.'
    }
}

$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$destination = Join-Path $completedDir "$TaskId-$timestamp.md"
Copy-Item -Path $activeTask -Destination $destination

$empty = @'
# Active Development Task

Status: **No task loaded**
Task ID: `NONE`
Owner: `Unassigned`
Implementer: `Unassigned`
Reviewer: `Unassigned`

No task is currently active. Draft one under `tasks/active/` from `tasks/TASK_TEMPLATE.md`, then run `scripts/new-task.ps1` to load it (or edit this file directly).
'@
Set-Content -Path $activeTask -Value $empty -Encoding utf8

Write-Host "Archived completed task: $destination"
Write-Host "tasks/ACTIVE_TASK.md reset to the empty convention."
