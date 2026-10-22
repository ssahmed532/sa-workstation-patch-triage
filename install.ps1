#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Install this skill into Claude Code by linking ~/.claude/skills/sa-workstation-patch-triage to this repo.

.DESCRIPTION
    Creates a directory junction (no admin rights needed), so edits in the repo are live in Claude Code
    and the repo stays the only copy. Also creates the user config at
    %APPDATA%\sa-workstation-patch-triage\config.json from config.example.json if it does not exist yet.
    Safe to re-run.

.EXAMPLE
    pwsh -ExecutionPolicy Bypass -File .\install.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repo = $PSScriptRoot
$link = Join-Path $env:USERPROFILE '.claude\skills\sa-workstation-patch-triage'

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

$cfg = Join-Path $env:APPDATA 'sa-workstation-patch-triage\config.json'
if (-not (Test-Path $cfg)) {
    New-Item -ItemType Directory -Force (Split-Path $cfg -Parent) | Out-Null
    Copy-Item (Join-Path $repo 'config.example.json') $cfg
    Write-Host "Created $cfg. Set artifact_url (and check the paths) before the first published run." -ForegroundColor Yellow
}
Write-Host "Restart Claude Code so it picks up the skill, then run /sa-workstation-patch-triage."
