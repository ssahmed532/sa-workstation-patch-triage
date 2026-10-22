# sa-workstation-patch-triage

> **Version:** 1.0 — Last updated 2026-10-22

A Claude Code skill that runs a read-only security patch triage of a Windows 11 developer workstation and publishes a
ranked remediation page: what to update today, this week, and in the backlog, with a comparison against the previous run.

It checks:
- installed apps and browsers (winget, plus file versions for apps winget does not track)
- language runtimes and toolchains: Node.js, CPython via uv, .NET, Go, PowerShell, Git and others on PATH, plus PHP, Java or Ruby found off PATH
- global npm, bun and uv tools, including the libraries bundled inside them (via OSV)
- every dependency lockfile under a projects folder: uv, pip/requirements, npm, NuGet and Go
- WSL distros (key package versions and how stale the apt lists are), listening ports, and the OS patch level
- vendor advisories released in the last N hours (24 by default)

The workflow and its rules are in [SKILL.md](SKILL.md). The triage rules are in [references/triage-rules.md](references/triage-rules.md), and the vendor pages checked on each run are in [references/vendor-sources.md](references/vendor-sources.md).

## Requirements

| Tool | Used for |
|---|---|
| Windows 11, PowerShell 7 (`pwsh`) | the inventory script |
| [uv](https://docs.astral.sh/uv/) | runs the Python scripts (standard library only) and the Python audits (`uv audit`, `uvx pip-audit`) |
| Node.js / npm | `npm audit` and global package checks |
| GitHub CLI (`gh`), signed in | advisory severity and publish dates from the GitHub Advisory Database. Without it, the scripts fall back to OSV |
| .NET SDK, Go | only if projects use them; `dotnet list package --vulnerable`, `govulncheck` |
| Claude Code with the Artifact tool | publishing the page |

## Install

```powershell
git clone https://github.com/ssahmed532/sa-workstation-patch-triage D:\3rd_party_skills\sa-workstation-patch-triage
cd D:\3rd_party_skills\sa-workstation-patch-triage
./install.ps1
```

`install.ps1` links `~/.claude/skills/sa-workstation-patch-triage` to this folder with a directory junction, so the
repo is the only copy and edits are live. It also creates `config.local.json` from `config.example.json`. Restart
Claude Code afterwards.

## Configure

Edit `config.local.json`. Git ignores it.

| Key | Meaning |
|---|---|
| `projects_root` | folder searched for dependency manifests |
| `runs_root` | where each run's folder is written (outside the repo; it holds machine inventory) |
| `artifact_url` | the private page to update on each run; leave empty to write the page locally only |
| `window_hours` | default look-back window for "new" advisories |
| `timezone_label`, `utc_offset_hours` | time zone used on the page |
| `exclude_dirs` | folder names skipped while searching for manifests |
| `risky_ports` | listening ports to flag |

## Use

In Claude Code:

```text
/sa-workstation-patch-triage
/sa-workstation-patch-triage 48
/sa-workstation-patch-triage dry-run
```

The skill also triggers on requests such as "what needs patching on my machine" or "does the new OpenSSL CVE affect me".
A full run takes about 10–15 minutes, and most of that is the upstream research. The skill must run on the machine it
scans, so a cloud-scheduled routine cannot run it. To repeat it on a schedule, use `/loop` in an open session.

## What a run changes

Nothing in your projects or installs. Side effects:
- `dotnet list` restores into each project's `obj/`
- each WSL distro is started to read its package list
- the uv, npm and Go caches download the scanner packages

## Layout

```text
SKILL.md                     workflow, ground rules, things that go wrong
scripts/setup_run.py         config, window, run folder, previous run
scripts/collect_inventory.ps1  Windows inventory
scripts/scan_dependencies.py   dependency scanners
scripts/build_findings.py      normalise, enrich, compare, digest
scripts/skill_version.py       version read from SKILL.md
references/                  triage rules, vendor sources, research-agent brief
assets/report_template.html  page layout
config.example.json          configuration template
install.ps1                  junction install
```

To release a new version, change `version` and `updated` in the SKILL.md front matter and the header of this file.
