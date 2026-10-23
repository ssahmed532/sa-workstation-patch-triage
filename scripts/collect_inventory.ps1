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

$inv = [ordered]@{ skill_version = $run.skill_version; collected_utc = (Get-Date).ToUniversalTime().ToString('s') + 'Z'; hostname = $env:COMPUTERNAME }

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
# Every python on PATH with its version. The Microsoft Store alias stub (under WindowsApps) opens the Store instead of
# running Python, so it is marked without being executed. A python.org or Anaconda install here is not a finding by itself.
$inv.python_on_path = @(Get-Command python, python3 -All -ErrorAction SilentlyContinue | ForEach-Object {
        $src = $_.Source
        if ($src -match '\\WindowsApps\\') { [ordered]@{ path = $src; version = $null; store_alias = $true } }
        else { [ordered]@{ path = $src; version = (First-Line { & $src --version }.GetNewClosure()); store_alias = $false } }
    })

# --- global packages and tools
$inv.npm_global_root = (npm root -g 2>$null)
$inv.npm_global = (npm ls -g --depth=0 --json 2>$null | ConvertFrom-Json -AsHashtable)
$inv.npm_global_outdated = (npm outdated -g --json 2>$null | ConvertFrom-Json -AsHashtable)
Save-Raw 'bun-global.txt' (bun pm ls -g 2>&1)
$bunHome = if ($env:BUN_INSTALL) { $env:BUN_INSTALL } else { Join-Path $env:USERPROFILE '.bun' }
$inv.bun_global_root = Join-Path $bunHome 'install\global\node_modules'
Save-Raw 'uv-python.txt' (uv python list --only-installed 2>&1)
Save-Raw 'uv-tools.txt'  (uv tool list --show-version-specifiers 2>&1)
$inv.uv_tools = @(foreach ($l in (uv tool list 2>$null)) { if ($l -match '^(\S+) v(\S+)') { @{ name = $Matches[1]; version = $Matches[2] } } })
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

# --- browsers: read the file version, since Chrome and Edge are not winget-managed here.
# Machine-wide paths first, then the per-user paths that an install without admin rights uses.
$inv.browsers = foreach ($p in @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
        "$env:ProgramFiles\Mozilla Firefox\firefox.exe",
        "$env:LOCALAPPDATA\Mozilla Firefox\firefox.exe",
        "$env:ProgramFiles\BraveSoftware\Brave-Browser\Application\brave.exe",
        "$env:LOCALAPPDATA\BraveSoftware\Brave-Browser\Application\brave.exe")) {
    if (Test-Path $p) { @{ path = $p; version = (Get-Item $p).VersionInfo.ProductVersion } }
}

# --- OS patch level
$cv = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
# ProductName still says "Windows 10" on many Windows 11 installs; the build number is what decides it
$product = if ([int]$cv.CurrentBuild -ge 22000) { $cv.ProductName -replace 'Windows 10', 'Windows 11' } else { $cv.ProductName }
$inv.os = [ordered]@{
    product = $product; edition = $cv.EditionID; display_version = $cv.DisplayVersion; build = "$($cv.CurrentBuild).$($cv.UBR)"
    hotfixes = @(Get-HotFix | Sort-Object InstalledOn -Descending | Select-Object -First 8 |
        ForEach-Object { @{ id = $_.HotFixID; description = $_.Description
                installed = $(if ($_.InstalledOn) { $_.InstalledOn.ToString('yyyy-MM-dd') } else { $null }) } })
}

# --- runtimes that may be installed off PATH (PHP, Java, Ruby): bounded search under runtime_search_roots from the config,
# skipping the Windows folder, the recycle bin and other users' profiles
$roots = @($run.runtime_search_roots | Where-Object { $_ })
if (-not $roots) { $roots = @("$env:SystemDrive\") }
$me = [regex]::Escape($env:USERNAME)
$inv.off_path_runtimes = @(foreach ($r in $roots) {
        Get-ChildItem $r -Recurse -Depth 5 -File -Include php.exe, java.exe, ruby.exe -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -notmatch '\\(Windows|\$Recycle\.Bin)\\' -and $_.FullName -notmatch "\\Users\\(?!$me\\)" } |
            Select-Object -ExpandProperty FullName
    })

# --- WSL: package manager per distro; key packages and apt staleness for apt-based ones. docker-desktop is Docker's own VM, skipped.
$keyPkgs = 'openssl|libssl3t64|libssl3|ca-certificates|libnss3|python3|nodejs|php\S*|golang\S*|openssh-server|openssh-client|curl|git|sudo|bash'
$distros = @()
if (Get-Command wsl.exe -ErrorAction SilentlyContinue) {
    $list = wsl -l -q 2>$null
    if ($LASTEXITCODE -eq 0) { $distros = @($list | ForEach-Object { "$_".Trim() } | Where-Object { $_ -and $_ -notmatch '^docker-desktop' }) }
}
$inv.wsl = @(foreach ($d in $distros) {
        # `which` needs no shell variables, which the outer shell would otherwise expand before the distro's sh sees them
        $found = @(wsl -d $d -- which dpkg rpm apk pacman 2>$null | ForEach-Object { "$_".Trim() } | Where-Object { $_ })
        $pm = if ($found) { [IO.Path]::GetFileName($found[0]) } else { '' }
        if ($pm -eq 'dpkg') {
            $dpkg = wsl -d $d -- dpkg -l 2>$null
            Save-Raw "wsl-$d-dpkg.txt" $dpkg
            $newest = wsl -d $d -- sh -c 'stat -c %Y /var/lib/apt/lists/*InRelease 2>/dev/null | sort -n | tail -1'
            [ordered]@{
                distro = $d; package_manager = 'apt'
                apt_lists_newest_utc = $(if ("$newest".Trim()) { [DateTimeOffset]::FromUnixTimeSeconds([long]"$newest".Trim()).UtcDateTime.ToString('s') + 'Z' } else { $null })
                key_packages = @($dpkg | Where-Object { $_ -match "^ii\s+($keyPkgs)(:\S+)?\s" } | ForEach-Object { $c = $_ -split '\s+'; "$($c[1]) $($c[2])" })
                dpkg_raw = "raw/wsl-$d-dpkg.txt"
            }
        } else {
            [ordered]@{
                distro = $d; package_manager = $(if ($pm) { $pm } else { 'unknown' }); apt_lists_newest_utc = $null; key_packages = @(); dpkg_raw = $null
                not_scanned = "only apt-based distros are inventoried; this one uses $(if ($pm) { $pm } else { 'an unknown package manager' })"
            }
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
'Gemfile.lock', 'composer.lock', 'Dockerfile', 'Dockerfile.*', '*.Dockerfile'
$excl = '\\(' + (($run.exclude_dirs | ForEach-Object { [regex]::Escape($_) }) -join '|') + ')\\'
$inv.manifests = @(Get-ChildItem $run.projects_root -Recurse -File -Force -Include $names -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notmatch $excl } | Select-Object -ExpandProperty FullName | Sort-Object)

$inv | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $RunDir 'inventory.json') -Encoding utf8
"inventory: $(@($inv.runtimes | Where-Object version).Count) runtimes, $($inv.manifests.Count) manifests, $(@($inv.wsl).Count) WSL distros, $(@($inv.listening | Where-Object risky).Count) risky listening ports"
