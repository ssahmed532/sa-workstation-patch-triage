# Triage rules

These rules turn the inventory, `findings.json` and the upstream research into the ranked list on the page.
The aim is a list someone can work top to bottom without having to re-sort it.

## Bands

Decide an item's band by working down this list. Stop at the first rule that matches.

**Priority 1 · Today**
1. It is exploited in the wild (CISA KEV, or the vendor says so).
2. It is a browser, OS component, runtime or toolchain, or anything else that handles untrusted network input or files on this machine, and it is Critical, or it is High and published in the window.
3. A browser has no patch yet for a Chromium or Firefox security release. Report it with the mitigation.
4. It is unpatchable (no fixed version will ship, for example an obsolete branch) and has a High or Critical advisory. The action is to remove it.
5. It is a project or global-tool dependency that runs as a service or processes untrusted input, and it is Critical, or it is High and published in the window.

**Priority 2 · This week**
1. It is Critical or High but does not meet a Today rule. For example, a test-only or dev-only package, or a transitive dependency of tests.
2. It is Moderate or Low and published in the window.
3. It is an old version installed alongside a current one (PowerShell, .NET runtimes and SDKs) and that old version is vulnerable.
4. It is an out-of-support runtime.
5. The WSL apt lists are more than 30 days old.
6. A fix for a cross-cutting incident (such as a CA distrust) has not shipped yet for an installed tool.

**Priority 3 · Backlog**
- Everything else from the dependency scans, grouped by ecosystem.
- End-of-support dates in the next 60 days.

**Not listed**
- Advisories that cannot apply to this machine, such as "non-Windows only". Mention them in one line under Limits.

**No action**
- Installed software that is already on the fixed version for this window's advisories. Listing these tells the reader they were checked.

**Limits**
- Scans that did not complete (`not_scanned` in findings.json), and scan notes with a caveat (`SCAN NOTES` in the digest).
- Sources you could not verify, and conflicts between sources.
- What this run does not cover, and its side effects.

Software that IT manages, such as a VPN client or EDR agent, gets the band its severity and exposure call for. The action is "ask IT to update to <version>".

Within a band, rank by exposure first and severity second:
1. Browsers and anything that handles untrusted network input.
2. Language runtimes and toolchains (everything built or run with them inherits the flaw).
3. Libraries in projects that run as services or process untrusted files.
4. Global CLI tools and MCP servers.
5. Dev-only and test-only packages.

## Grouping

The digest lists one row per project, package and version. Merge rows so the page stays readable:
- Merge one package across several projects into one item, and list the projects (for example certifi in four uv projects).
- Merge one package across the projects of a .NET solution into one item per solution.
- Merge several advisories for one package into one item. Give the count, the worst severity, and the two or three advisories that matter most (RCE, memory corruption, Windows-specific).
- A flaw in a library bundled inside a global tool belongs to that tool. Say whether the tool's newest release still pins the vulnerable version (`npm view <pkg>@<version> dependencies`).

## Each item

- Product, and where it is installed (machine-wide, the project path, or the global install that bundles it).
- Installed version → fixed version. Use the minimum fixed version on the same major line. Say "uninstall" or "pending" when no fixed version applies.
- Severity chip, with CVSS when known. Mark "Windows-specific" or "reachable from your code" when the scan says so.
- Release date of the fix or advisory, in the configured time zone.
- One or two plain sentences on why it matters on this machine.
- The exact action.
  - Use a command only if it ran during this scan or you checked it with `--help`. This covers `uv lock --upgrade-package <pkg>`, `uv sync`, `uv python upgrade`, `npm install <pkg>@<version>`, `npm audit fix`, `winget uninstall --id <id>`, and `sudo apt update && sudo apt full-upgrade` inside WSL.
  - For .NET package bumps, give the package and version to set in the project file.
  - For apps, give the UI path or the vendor download page.
- Delta chip when a previous run exists: **New**, **Still open** or (in its own list) **Resolved**.

## Wording

Write for an engineering executive who will act on the page or forward it. Use literal, plain sentences with no metaphors. Use active voice. Name things by what people recognise ("Microsoft Edge", "the Python CA bundle"), not by scanner output. Put CVE and GHSA IDs in the item. Never invent a severity, version or date: if a source does not give one, say "not stated".
