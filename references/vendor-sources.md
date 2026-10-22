# Upstream sources to check on every run

Search indexes lag by a day or more, so read these pages directly instead of relying on a web search.
Check only what the inventory shows is installed, plus the cross-cutting incidents at the end.
Prefer the vendor's page. When a news site or aggregator disagrees with it, go with the vendor and record the conflict.

## Runtimes and toolchains

| Product | Page | What to read |
|---|---|---|
| Node.js | https://nodejs.org/en/blog/vulnerability | The newest security-release post: fixed version per release line, CVEs, dependency updates (undici, OpenSSL, c-ares, CA certificates) |
| Go | https://go.dev/doc/devel/release | Minor releases for the installed line that mention "security fixes"; compare with the reachable flaws from govulncheck |
| CPython | https://www.python.org/downloads/ and the release page of the newest patch for the installed minor line | Security content; bundled pip/certifi/OpenSSL changes |
| uv | https://github.com/astral-sh/uv/releases | Security notes; uv bundles its own CA roots |
| .NET | https://github.com/dotnet/core/tree/main/release-notes and https://dotnet.microsoft.com/en-us/platform/support/policy/dotnet-core | Patch Tuesday (second Tuesday of the month) runtime and SDK versions; end-of-support dates |
| PowerShell | https://github.com/PowerShell/PowerShell/releases | Security releases; old side-by-side versions stay vulnerable |
| PHP, Java, Ruby | php.net, Oracle CPU / Adoptium, ruby-lang.org | Only if the inventory found them, on PATH or off it |

## Applications

| Product | Page |
|---|---|
| Chrome | Version: https://versionhistory.googleapis.com/v1/chrome/platforms/win/channels/stable/versions (JSON, newest first). The release blog (chromereleases.googleblog.com) lists bug reporters by name, so do not use it. Take CVE IDs and severities from NVD or CVE.org for "Google Chrome", and from Microsoft's Edge security notes, which list the Chromium CVEs they include |
| Edge | https://learn.microsoft.com/en-us/deployedge/microsoft-edge-relnotes-security. Edge often trails Chrome by days. If Microsoft's newest note says a fix is pending, report Edge as "no patch yet" with the mitigation |
| Firefox | https://www.mozilla.org/en-US/security/advisories/ |
| Git for Windows | https://github.com/git-for-windows/git/releases. The `.windows.N` suffix matters, because a `.windows.2` build can carry an OpenSSL or curl security update that `.windows.1` lacks |
| GitHub CLI | https://github.com/cli/cli/releases |
| Docker Desktop | https://docs.docker.com/desktop/release-notes/ |
| VS Code | https://code.visualstudio.com/updates and MSRC |
| Visual Studio | https://learn.microsoft.com/en-us/visualstudio/releases/2026/release-notes (check whether a newer build has a security advisory table or only bug fixes) |
| 7-Zip | https://www.7-zip.org/history.txt |
| Notepad++ | https://github.com/notepad-plus-plus/notepad-plus-plus/releases |
| KeePass | https://keepass.info/news/news_all.html |
| Zoom | https://www.zoom.com/en/trust/security-bulletin/ |
| FortiClient | https://www.fortiguard.com/psirt (filter by FortiClient; usually IT-managed) |
| ISC BIND | https://kb.isc.org/docs/aa-00913. There are no Windows builds after 9.17, so an installed Windows BIND cannot be patched |
| WSL | https://github.com/microsoft/WSL/releases |
| Adobe Acrobat | https://helpx.adobe.com/security/products/acrobat.html (it sometimes returns 403 to automated fetches; then use the APSB bulletin found by search, and say so) |
| Bun | https://bun.com/blog (release posts). The GitHub releases page can embed signed download URLs, so do not use it |
| Windows | https://msrc.microsoft.com/update-guide and the current month's Patch Tuesday; compare with the OS build and UBR from the inventory |

## Feeds that catch everything else

- CISA alerts and the Known Exploited Vulnerabilities catalog: https://www.cisa.gov/news-events/cybersecurity-advisories and https://www.cisa.gov/known-exploited-vulnerabilities-catalog
- GitHub Advisory Database, reviewed advisories sorted by newest: https://github.com/advisories
- One extended web search for "critical vulnerability security update <today's date>" to find anything not listed here.

## Cross-cutting incidents

When a certificate authority is compromised or distrusted, tools that ship their own CA bundle need their own updates even after the OS and browsers have blocked it. Check certifi in every Python project, uv, CPython's bundled pip, Docker Desktop, Git for Windows' bundled OpenSSL, and Node.js' bundled CA store.
