---
name: sa-workstation-patch-triage
description: >
  Read-only security patch triage of this Windows dev workstation. It inventories installed apps,
  browsers, language runtimes, global npm/bun/uv tools, .NET, Go, WSL distros and listening ports;
  audits every dependency lockfile under the projects folder (uv, pip, npm, NuGet, Go); checks vendor
  advisories released in the last N hours (default 24); and publishes a ranked remediation page:
  Today / This week / Backlog, with a delta against the previous run. Use this skill whenever the user
  asks what needs patching or updating on their machine, whether a newly reported CVE, zero-day or
  "critical vulnerability in X" affects them, to scan installed packages, runtimes or dev dependencies
  for vulnerabilities, to re-run or refresh the workstation scan or patch triage, or for a security
  update checklist for their laptop, even if they don't say "triage". Not for a single Windows KB
  GO/NOGO decision (sa-windows-update-advisor) or for Azure VMs.
argument-hint: "[window-hours, e.g. 48] [dry-run]"
metadata:
  version: "1.0"
  updated: "2026-10-22"
---

# Workstation patch triage

Version 1.0 — Last updated 2026-10-22

## What this produces

- One private web page (an Artifact), updated in place at the `artifact_url` from the config. It lists what to
  update in the order to do it: **Today**, **This week** and **Backlog** bands; then **Resolved since the last run**,
  **Already patched**, **Limits** and **Sources**. Each item has severity, installed → fixed version, release date,
  why it matters, the exact action, and a done-checkbox.
- A dated run folder (`runs_root/YYYY-MM-DD/`) holding the raw scanner output, `findings.json` (which the next run
  compares against) and the page's HTML.
- A short chat summary: counts per band, what is new since the last run, the top five actions, and the link.

## Parameters

Read them from the arguments. Both are optional.

| Parameter | Form | Default |
|---|---|---|
| Window | a number of hours (`48`, `48h`) | `window_hours` in the config (24) |
| Dry run | the word `dry-run` | off. With it, the page is written to the run folder and not published. A run is also dry when `artifact_url` is empty |

Configuration lives in `config.local.json` next to this file, which git ignores because it holds machine paths and the
artifact link. If only `config.example.json` exists, the run still works but stays dry. Tell the user to copy it to
`config.local.json` and fill in `artifact_url`.

## Ground rules

- **Read-only.** Never install, update, uninstall or `npm audit fix` anything, and never run `uv lock` or edit files
  in a project. Projects without a lockfile are resolved in a copy inside the run folder. The user decides what to
  change; this skill tells them what and in which order.
- **Python only through uv.** Run the bundled scripts with `uv run`, and other Python tools with `uvx`. Never use
  bare `python` or `pip`.
- **Secrets and personal data.** Never open `.env` files or credential stores, and never print tokens or connection
  strings. Skip source pages that show personal identifiers, such as bug-tracker reporter details. If a tool result
  contains credentials or customer data anyway, stop and follow the organisation's data-handling policy.
- **Vendor first.** Release dates, versions and severities come from the vendor's page, the GitHub Advisory Database
  or OSV. If a news site disagrees with the vendor, go with the vendor and record the conflict under Limits. Never fill
  in a version, date or severity no source gave: write "not stated".
- **Times** are in the configured zone (`timezone_label`, default PKT = UTC+5). State the zone once. Convert with the
  scripts or PowerShell, not Git Bash `date`, which has no time zone database here.
- **Shell.** Use the PowerShell tool for the commands below. Git Bash on this machine has MSYS problems with
  long-running native processes.

## Workflow

`SKILL` below means `${CLAUDE_SKILL_DIR}`. `RUN` is the folder printed by step 1.

1. **Set up the run.** `uv run "SKILL/scripts/setup_run.py" [--window-hours N] [--dry-run]`. The last line printed is
   RUN. `RUN/run.json` holds the window start (`since_utc`), the previous run to compare with, and whether this run is
   dry.

2. **Inventory** (about 3 minutes). `pwsh -NoProfile -File "SKILL/scripts/collect_inventory.ps1" -RunDir RUN`.
   It writes `RUN/inventory.json` and raw text under `RUN/raw/`: winget lists, runtime versions, global packages, uv
   Pythons and tools, .NET SDKs and runtimes, browser file versions, OS build and hotfixes, PHP/Java/Ruby found off
   PATH, WSL key packages and apt staleness, listening ports, and every manifest under the projects root.

3. **Start the upstream research in the background** as soon as the inventory exists. Fill
   `references/research-brief.md` from `inventory.json` and `run.json`, and spawn one general-purpose agent with it
   (`run_in_background`). It is the slowest step, about 10 minutes, so start it before the dependency scans. If agents
   are not available, do the same research inline.

4. **Dependency scans** (about 2 minutes, in parallel with step 3). `uv run "SKILL/scripts/scan_dependencies.py" --run RUN`.
   It runs uv audit, pip-audit (on a resolved copy), npm audit, dotnet list --vulnerable and govulncheck. It also checks
   every package bundled inside global npm and bun installs, and the uv tools, against OSV. Anything it could not scan
   is printed as NOT SCANNED and recorded in `RUN/deps/scan_status.json`.

5. **Findings.** `uv run "SKILL/scripts/build_findings.py" --run RUN`. It normalises everything into
   `RUN/findings.json`, adds severity, CVSS and publish dates from the GitHub Advisory Database (with OSV as fallback),
   marks each finding `in_window`, `recent` (72 hours) and `new` or `still_open` against the previous run, and
   prints a digest. The digest has these sections, all with times in the configured zone:
   - per-package rows with counts by severity and the top advisories;
   - IN WINDOW;
   - LAST 72 HOURS;
   - RESOLVED;
   - INSTALLED-SOFTWARE CHANGES since the previous run (apps, runtimes, OS, tools, WSL packages);
   - NOT SCANNED;
   - SCAN NOTES.
   Read the digest; open `findings.json` only for detail you need.

   **While the research agent runs, keep working instead of waiting.** Do not sleep or poll; you are notified when it
   finishes. Group the dependency findings into Backlog and This-week items, check the things no scanner reports (step 6),
   and draft the page body. When the agent reports, add its items and finish the Today band.

6. **Triage.** Combine the research table, the inventory and the digest. Apply `references/triage-rules.md`, which
   covers the bands, ranking, grouping and the wording of each item. Also check these, since no scanner reports them:
   - risky listening ports (`inventory.listening[].risky`);
   - non-uv Pythons on PATH (`python_on_path`);
   - runtimes found off PATH;
   - `raw/dotnet-sdk-check.txt` for out-of-support .NET versions. It is Microsoft's own status, so cite it, and record a
     conflict if the research says otherwise;
   - Dockerfile base images (`RUN/deps/dockerfiles.json`), noted as not scanned if Docker is not running.

7. **Render.** Copy `SKILL/assets/report_template.html` to `RUN/patch-triage.html`. Write the page body between the
   `<!-- BODY START -->` and `<!-- BODY END -->` markers, and leave the styles and script outside them unchanged. The
   template's top comment lists every placeholder.
   - `RUN_ID` is the run folder name, so the checkboxes reset on each run.
   - `SURFACE` is the Claude surface and model actually used.
   - `SIDE_EFFECTS` lists what this run touched (see Things that go wrong), or "none".
   - Leave out the Resolved section on a first run, or when nothing was resolved.
   Finish by deleting the template comment, then check that no double-brace placeholder or "sample" marker remains.

8. **Publish**, unless the run is dry. This conversation has not seen the page before, so first read it with the
   Artifact tool (`action: "read"`, `url` = `artifact_url`). Then publish `RUN/patch-triage.html` with the same `url`,
   and without `icon`, so the link and icon stay the same. If the read fails because the page was deleted, publish
   without `url` and tell the user the new link so they can update `artifact_url`.

9. **Reply in chat** with the counts per band, the new-since-last-run items, the top five actions, anything not
   scanned, and the link (or the local file path on a dry run).

## Things that go wrong

- **winget misses many updates.** Chrome shows up as an uninstalled-registry (ARP) entry, and the Go and Git
  manifests lag behind the vendors. "No winget upgrade" is not the same as "current"; compare with the vendor.
- **Edge trails Chrome.** When Microsoft's newest note says a fix is pending, Edge goes in Today as "no patch yet",
  with the mitigation of using another browser for untrusted sites.
- **Git's build suffix matters.** `2.56.0.windows.1` and `.windows.2` can differ by an OpenSSL security update.
- **Old versions stay installed.** PowerShell, .NET runtimes and SDKs, and some apps keep the previous version next to
  the new one. The old copy is still exploitable until it is removed.
- **Fixes in bundled libraries.** For a flaw inside a global tool, check whether the tool's newest release still pins
  the vulnerable version before telling the user to update it.
- **The same flaw under two IDs.** `uv audit` lists one flaw under both its GHSA and PYSEC IDs. `build_findings.py`
  merges them by CVE, so use its counts instead of counting raw records.
- **winget IDs can mislead.** For example, `OpenJS.NodeJS.22` can hold Node 24. Trust the version the runtime reports,
  and list Edge once, using the version of `msedge.exe` (winget also shows an MSIX copy with a different build).
- **.NET projects that were never restored** are reported as not scanned, because the scan runs `dotnet list` with
  `--no-restore` to stay read-only. The action for the user is to run `dotnet restore` in that project.
- **Projects without a lockfile** are resolved fresh. Their result shows what a new install would get today, not
  what an existing virtual environment contains. Say so under Limits (it shows under SCAN NOTES).
- **Side effects to report.** The inventory starts each WSL distro. The uv, npm and Go caches download scanner
  packages. govulncheck can touch a project's `.git` folder timestamp.
- **Docker images are not scanned** when the engine is stopped. Say so rather than skipping it silently.

## Files

- `scripts/setup_run.py`: config, window, run folder, previous run.
- `scripts/collect_inventory.ps1`: Windows inventory (PowerShell 7).
- `scripts/scan_dependencies.py`: runs the dependency scanners.
- `scripts/build_findings.py`: normalises, enriches and compares the findings, and prints the digest.
- `scripts/skill_version.py`: reads the version from this file.
- `references/triage-rules.md`: bands, ranking, grouping and the wording of each item.
- `references/vendor-sources.md`: the vendor pages to read on every run.
- `references/research-brief.md`: the prompt for the research agent, with slots to fill from the inventory.
- `assets/report_template.html`: the page layout.
- `config.example.json`: copy it to `config.local.json` and edit.
