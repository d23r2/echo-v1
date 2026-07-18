<#
Creates a task draft from tasks/TASK_TEMPLATE.md under tasks/active/, then loads it
into tasks/ACTIVE_TASK.md by moving (not copying) the draft, so ACTIVE_TASK.md stays
the single canonical record of whatever task is currently loaded.

Refuses to overwrite a currently-loaded task unless -Force is passed. -Force alone
still prompts for an interactive typed confirmation; pass -Yes as well to skip that
prompt (e.g. for scripted/test use).
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9_-]+$')]
    [string]$TaskId,

    [Parameter(Mandatory = $true)]
    [string]$Title,

    [switch]$Force,

    [switch]$Yes
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$template = Join-Path $root 'tasks/TASK_TEMPLATE.md'
$activeDir = Join-Path $root 'tasks/active'
$activeTask = Join-Path $root 'tasks/ACTIVE_TASK.md'

if (-not (Test-Path $template)) {
    throw "Task template not found: $template"
}
if (-not (Test-Path $activeDir)) {
    New-Item -ItemType Directory -Path $activeDir -Force | Out-Null
}

$slug = ($Title.ToLowerInvariant() -replace '[^a-z0-9]+', '-').Trim('-')
$draftFile = Join-Path $activeDir "$TaskId-$slug.md"

if (Test-Path $draftFile) {
    throw "A queued draft already exists: $draftFile"
}

if (Test-Path $activeTask) {
    $currentContent = Get-Content $activeTask -Raw
    $hasLoadedTask = -not ($currentContent -match '(?m)^Status:\s*\*\*No task loaded\*\*\s*$')
    if ($hasLoadedTask) {
        if (-not $Force) {
            throw "tasks/ACTIVE_TASK.md already has a loaded task. Pass -Force to replace it. This does not archive the current task first -- make sure it is committed, completed, or otherwise safe to lose before forcing."
        }
        if (-not $Yes) {
            $response = Read-Host "This will overwrite the currently loaded active task in tasks/ACTIVE_TASK.md. Type YES to continue"
            if ($response -ne 'YES') {
                throw "Overwrite not confirmed. Aborting without changes."
            }
        }
    }
}

$content = Get-Content $template -Raw
$content = $content -replace '\[TASK-ID\] Task title', "$TaskId $Title"
$content = $content -replace 'Task ID:\s*`TASK-ID`', "Task ID: ``$TaskId``"
Set-Content -Path $draftFile -Value $content -Encoding utf8

Copy-Item -Path $draftFile -Destination $activeTask -Force
Remove-Item -Path $draftFile

Write-Host "Loaded as the active task: $activeTask (from $TaskId $Title)"
Write-Host "Next: fill in Objective/Scope/Acceptance criteria/Allowed paths, assign Implementer/Reviewer, then start the implementer."
