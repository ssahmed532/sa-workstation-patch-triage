#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Read-only inventory of installed software, runtimes, global tools, WSL, listening ports and
    dependency manifests. Writes RUN/inventory.json plus raw text output under RUN/raw/.

.DESCRIPTION
    Reads the window, projects root, exclusions and ports from RUN/run.json (written by setup_run.py).
    Nothing is installed, updated or changed. Starting each WSL distro to read its package list is
    the only side effect.

.EXAMPLE
    pwsh -NoProfile -File collect_inventory.ps1 -RunDir <RUN>
#>
[CmdletBinding()]
param([Parameter(Mandatory)][string]$RunDir)

$ErrorActionPreference = 'Continue'
$run = Get-Content (Join-Path $RunDir 'run.json') -Raw | ConvertFrom-Json
$raw = Join-Path $RunDir 'raw'
New-Item -ItemType Directory -Force $raw | Out-Null
$env:WSL_UTF8 = '1'   # otherwise wsl.exe prints UTF-16 with NULs between characters

function Save-Raw([string]$name, $text) { $text | Out-String -Width 400 | Set-Content (Join-Path $raw $name) -Encoding utf8 }
function First-Line($block) { try { (& $block 2>&1 | Select-Object -First 1 | Out-String).Trim() } catch { "error: $_" } }

$inv = [ordered]@{ skill_version = $run.skill_version; collected_utc = (Get-Date).ToUniversalTime().ToString('s') + 'Z' }

# --- winget: kept as text; the table format does not parse reliably, and winget misses many updates anyway
Save-Raw 'winget-upgrade.txt' (winget upgrade --include-unknown --accept-source-agreements --disable-interactivity 2>&1)
Save-Raw 'winget-list.txt'    (winget list --accept-source-agreements --disable-interactivity 2>&1)
$inv.winget = @{ upgrade = 'raw/winget-upgrade.txt'; list = 'raw/winget-list.txt' }

# --- runtimes and CLIs
$probes = [ordered]@{
    node = { node --version }; npm = { npm --version }; pnpm = { pnpm --version }; yarn = { yarn --version }
    bun = { bun --version }; deno = { deno --version }; uv = { uv --version }; git = { git --version }
    gh = { gh --version }; pwsh = { pwsh --version }; dotnet = { dotnet --version }; go = { go version }
    rustc = { rustc --version }; java = { java -version }; docker = { docker --version }
    az = { 'azure-cli ' + (az version 2>$null | ConvertFrom-Json).'azure-cli' }; terraform = { terraform version }
    kubectl = { kubectl version --client }; helm = { helm version --short }; code = { code --version }
    php = { php --version }; ruby = { ruby --version }; claude = { claude --version }
}
$inv.runtimes = foreach ($k in $probes.Keys) {
    $g = Get-Command $k -ErrorAction SilentlyContinue | Select-Object -First 1
    [ordered]@{ name = $k; path = $g.Source; version = $(if ($g) { First-Line $probes[$k] } else { $null }) }
}
# Paths only: every python on PATH should be a uv shim; anything else (for example the Store alias) is worth flagging
$inv.python_on_path = @(Get-Command python, python3 -All -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)

# --- global packages and tools
$inv.npm_global_root = (npm root -g 2>$null)
$inv.npm_global = (npm ls -g --depth=0 --json 2>$null | ConvertFrom-Json -AsHashtable)
$inv.npm_global_outdated = (npm outdated -g --json 2>$null | ConvertFrom-Json -AsHashtable)
Save-Raw 'bun-global.txt' (bun pm ls -g 2>&1)
$inv.bun_global_root = Join-Path $env:USERPROFILE '.bun\install\global\node_modules'
Save-Raw 'uv-python.txt' (uv python list --only-installed 2>&1)
Save-Raw 'uv-tools.txt'  (uv tool list --show-version-specifiers 2>&1)
$inv.uv_tools = foreach ($l in (uv tool list 2>$null)) { if ($l -match '^(\S+) v(\S+)') { @{ name = $Matches[1]; version = $Matches[2] } } }
$inv.uv_pythons = @(uv python list --only-installed 2>$null | ForEach-Object { ($_ -split '\s+')[0] } | Sort-Object -Unique)
# `dotnet sdk check` is Microsoft's own support-status view; keep it next to the raw lists
Save-Raw 'dotnet-sdk-check.txt' (dotnet sdk check 2>&1)
$inv.dotnet = @{ sdks = @(dotnet --list-sdks 2>$null); runtimes = @(dotnet --list-runtimes 2>$null); sdk_check = 'raw/dotnet-sdk-check.txt' }

# --- installed apps from the uninstall registry: names and versions without winget's MSIX framework noise
$uninstall = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*', 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*'
$inv.installed_apps = @(Get-ItemProperty $uninstall -ErrorAction SilentlyContinue |
        Where-Object { $_.DisplayName -and $_.DisplayVersion -and $_.SystemComponent -ne 1 -and -not $_.ParentKeyName } |
        Sort-Object DisplayName, DisplayVersion -Unique |
        ForEach-Object { [ordered]@{ name = $_.DisplayName; version = $_.DisplayVersion; publisher = $_.Publisher } })

# --- browsers: read the file version, since Chrome and Edge are not winget-managed here
$inv.browsers = foreach ($p in @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
        "$env:ProgramFiles\Mozilla Firefox\firefox.exe",
        "$env:ProgramFiles\BraveSoftware\Brave-Browser\Application\brave.exe")) {
    if (Test-Path $p) { @{ path = $p; version = (Get-Item $p).VersionInfo.ProductVersion } }
}

# --- OS patch level
$cv = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
# ProductName still says "Windows 10" on many Windows 11 installs; the build number is what decides it
$product = if ([int]$cv.CurrentBuild -ge 22000) { $cv.ProductName -replace 'Windows 10', 'Windows 11' } else { $cv.ProductName }
$inv.os = [ordered]@{
    product = $product; display_version = $cv.DisplayVersion; build = "$($cv.CurrentBuild).$($cv.UBR)"
    hotfixes = @(Get-HotFix | Sort-Object InstalledOn -Descending | Select-Object -First 8 |
        ForEach-Object { @{ id = $_.HotFixID; description = $_.Description; installed = "$($_.InstalledOn)" } })
}

# --- runtimes that may be installed off PATH (PHP, Java, Ruby): quick bounded search on fixed drives
$drives = (Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3').DeviceID
$inv.off_path_runtimes = @(foreach ($d in $drives) {
        Get-ChildItem "$d\" -Recurse -Depth 5 -File -Include php.exe, java.exe, ruby.exe -ErrorAction SilentlyContinue |
            Where-Object FullName -notmatch '\\(Windows|\$Recycle\.Bin)\\' | Select-Object -ExpandProperty FullName
    })

# --- WSL: key packages and how stale the apt lists are. docker-desktop is Docker's own VM, skipped.
$keyPkgs = 'openssl|libssl3t64|libssl3|ca-certificates|libnss3|python3|nodejs|php\S*|golang\S*|openssh-server|openssh-client|curl|git|sudo|bash'
$inv.wsl = @(foreach ($d in (wsl -l -q 2>$null | Where-Object { $_ -and $_ -notmatch '^docker-desktop' })) {
        $d = $d.Trim()
        $dpkg = wsl -d $d -- dpkg -l 2>$null
        Save-Raw "wsl-$d-dpkg.txt" $dpkg
        $newest = wsl -d $d -- sh -c 'stat -c %Y /var/lib/apt/lists/*InRelease 2>/dev/null | sort -n | tail -1'
        [ordered]@{
            distro = $d
            apt_lists_newest_utc = $(if ("$newest".Trim()) { [DateTimeOffset]::FromUnixTimeSeconds([long]"$newest".Trim()).UtcDateTime.ToString('s') + 'Z' } else { $null })
            key_packages = @($dpkg | Where-Object { $_ -match "^ii\s+($keyPkgs)(:\S+)?\s" } | ForEach-Object { $c = $_ -split '\s+'; "$($c[1]) $($c[2])" })
            dpkg_raw = "raw/wsl-$d-dpkg.txt"
        }
    })

# --- listening ports, flagged when they match the risky list from config
$inv.listening = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Sort-Object LocalPort -Unique | ForEach-Object {
        $p = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
        [ordered]@{ port = $_.LocalPort; address = $_.LocalAddress; process = $p.ProcessName; path = $p.Path; risky = ($run.risky_ports -contains $_.LocalPort) }
    })

# --- dependency manifests under the projects root
$names = 'package.json', 'package-lock.json', 'pnpm-lock.yaml', 'yarn.lock', 'bun.lockb', 'bun.lock', 'pyproject.toml', 'uv.lock',
'requirements*.txt', 'Pipfile.lock', 'poetry.lock', '*.csproj', '*.sln', '*.slnx', 'packages.config', 'go.mod', 'Cargo.lock',
'Gemfile.lock', 'composer.lock', 'Dockerfile'
$excl = '\\(' + (($run.exclude_dirs | ForEach-Object { [regex]::Escape($_) }) -join '|') + ')\\'
$inv.manifests = @(Get-ChildItem $run.projects_root -Recurse -File -Force -Include $names -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notmatch $excl } | Select-Object -ExpandProperty FullName | Sort-Object)

$inv | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $RunDir 'inventory.json') -Encoding utf8
"inventory: $(@($inv.runtimes | Where-Object version).Count) runtimes, $($inv.manifests.Count) manifests, $(@($inv.wsl).Count) WSL distros, $(@($inv.listening | Where-Object risky).Count) risky listening ports"
