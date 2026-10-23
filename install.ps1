#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Install this skill into Claude Code by linking ~/.claude/skills/win-dev-patch-triage to this repo.

.DESCRIPTION
    Creates a directory junction (no admin rights needed), so edits in the repo are live in Claude Code
    and the repo stays the only copy. It creates no config: the first run on each machine asks for the
    projects folders and the report page, and saves them with setup_run.py --init. Safe to re-run.

.EXAMPLE
    pwsh -ExecutionPolicy Bypass -File .\install.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repo = $PSScriptRoot
$link = Join-Path $env:USERPROFILE '.claude\skills\win-dev-patch-triage'

if (Test-Path $link) {
    $item = Get-Item $link -Force
    if ($item.LinkType -eq 'Junction' -and ($item.Target | Select-Object -First 1) -eq $repo) {
        Write-Host "Already installed: $link -> $repo" -ForegroundColor Green
    } else {
        throw "$link already exists and is not a junction to this repo. Move or remove it, then re-run."
    }
} else {
    New-Item -ItemType Directory -Force (Split-Path $link -Parent) | Out-Null
    New-Item -ItemType Junction -Path $link -Target $repo | Out-Null
    Write-Host "Installed: $link -> $repo" -ForegroundColor Green
}

Write-Host "Restart Claude Code so it picks up the skill, then run /win-dev-patch-triage."
Write-Host "The first run on this machine asks for the projects folders and the report page before it scans anything."
