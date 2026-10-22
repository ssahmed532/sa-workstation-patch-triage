# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Run every dependency scanner over the manifests in RUN/inventory.json and save raw results to RUN/deps/.

Usage: uv run scan_dependencies.py --run RUN

Read-only for the projects: lockfiles are audited as they are, and projects without a lockfile are
resolved in a copy under RUN/work/, never in the repo. Each scan's outcome is recorded in
RUN/deps/scan_status.json so the report can say what was not scanned and why.
Side effects outside RUN: `dotnet list` restores into each project's obj/, and the uv, npm and Go
caches download what they need.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import urllib.request
from collections import defaultdict

from skill_version import SKILL_VERSION

OSV = "https://api.osv.dev/v1"
status = []


def slug(path, root):
    rel = os.path.relpath(path, root)
    return re.sub(r"[^A-Za-z0-9._-]+", "_", rel).strip("_") or "root"


def run(cmd, cwd=None, timeout=900):
    """Run a command and return (exit code, stdout, stderr). Never raises for a non-zero exit."""
    exe = shutil.which(cmd[0])
    if not exe:
        return 127, "", f"{cmd[0]} not found on PATH"
    try:
        p = subprocess.run([exe, *cmd[1:]], cwd=cwd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {timeout}s"


def record(kind, target, ok, out=None, note=""):
    status.append({"kind": kind, "target": target, "ok": ok, "output": out, "note": note.strip()[:500]})


def save(deps, name, text):
    path = os.path.join(deps, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return os.path.relpath(path, os.path.dirname(deps))


def is_json(text):
    try:
        json.loads(text)
        return True
    except ValueError:
        return False


# ---------- per-ecosystem scanners ----------

def scan_uv(d, root, deps):
    # uv audit exits non-zero when it finds vulnerabilities, so judge success by the JSON, not the exit code
    code, out, err = run(["uv", "audit", "--frozen", "--preview-features", "audit-command", "--output-format", "json"], cwd=d)
    ok = is_json(out)
    record("uv-audit", d, ok, save(deps, f"uv__{slug(d, root)}.json", out) if ok else None, "" if ok else err or out)


def scan_unlocked_python(src, root, deps, work):
    """pyproject without uv.lock, or a requirements file: resolve a copy in RUN/work, then pip-audit the pins."""
    name = slug(src, root)
    wd = os.path.join(work, name)
    os.makedirs(wd, exist_ok=True)
    copy = os.path.join(wd, os.path.basename(src))
    shutil.copy2(src, copy)
    pinned = os.path.join(wd, "pinned.txt")
    code, out, err = run(["uv", "pip", "compile", copy, "--python", "3.14", "--quiet", "--no-header", "-o", pinned], cwd=wd)
    if code != 0 or not os.path.exists(pinned):
        record("pip-audit", src, False, None, "uv pip compile failed: " + err)
        return
    outfile = os.path.join(deps, f"pipaudit__{name}.json")
    code, out, err = run(["uvx", "pip-audit", "-r", pinned, "--no-deps", "--disable-pip", "--progress-spinner", "off",
                          "-f", "json", "-o", outfile], cwd=wd)
    ok = os.path.exists(outfile)
    # no lockfile means nothing pins what is actually installed: this shows what a fresh install would get today
    record("pip-audit", src, ok, os.path.relpath(outfile, os.path.dirname(deps)) if ok else None,
           "resolved fresh from the manifest (no lockfile): reflects a new install today, not an existing venv" if ok else err)


def scan_npm(d, root, deps):
    code, out, err = run(["npm", "audit", "--package-lock-only", "--json"], cwd=d)
    ok = is_json(out)
    record("npm-audit", d, ok, save(deps, f"npm__{slug(d, root)}.json", out) if ok else None, "" if ok else err)


def scan_dotnet(target, root, deps):
    # --no-restore keeps the projects untouched; a project that was never restored is reported, not restored
    code, out, err = run(["dotnet", "list", target, "package", "--vulnerable", "--include-transitive", "--no-restore",
                          "--format", "json", "--output-version", "1"], timeout=1200)
    ok = is_json(out) and '"problems"' not in out
    note = "" if ok else ("no restore output (obj/project.assets.json); run `dotnet restore` yourself, then re-run "
                          "the scan. " + (err or out)[:300])
    if is_json(out) and '"problems"' in out:  # partial result: keep it, but say which projects had problems
        ok, note = True, "some projects reported problems, usually missing restore output: " + out[out.find('"problems"'):][:300]
    record("dotnet-vulnerable", target, ok, save(deps, f"dotnet__{slug(target, root)}.json", out) if is_json(out) else None, note)


def parse_govulncheck(text):
    """Turn govulncheck's `-show verbose` text report into records, keeping which section each one came from:
    Symbol Results = your code calls it, Package Results = imported but not called, Module Results = required only."""
    sections = {"Symbol": "reachable", "Package": "imported", "Module": "required"}
    vulns, cur, scope = [], None, "reachable"
    lines = text.splitlines()
    for i, line in enumerate(lines):
        s = re.match(r"^=== (\w+) Results ===", line)
        if s:
            scope = sections.get(s.group(1), scope)
            continue
        m = re.match(r"^Vulnerability #\d+: (GO-\d{4}-\d+)", line)
        if m:
            cur = {"id": m.group(1), "title": lines[i + 1].strip() if i + 1 < len(lines) else "", "found": [], "fixed": [],
                   "scope": scope}
            vulns.append(cur)
        elif cur and "Found in:" in line:
            cur["found"].append(line.split("Found in:")[1].strip())
        elif cur and "Fixed in:" in line:
            cur["fixed"].append(line.split("Fixed in:")[1].strip())
    summary = [l.strip() for l in lines if l.startswith(("Your code is affected", "This scan also found", "vulnerabilities in modules"))]
    return {"vulns": vulns, "summary": " ".join(summary)}


def scan_go(d, root, deps):
    code, out, err = run(["go", "run", "golang.org/x/vuln/cmd/govulncheck@latest", "-show", "verbose", "./..."], cwd=d, timeout=1200)
    text = out + err
    ok = "Vulnerability #" in text or "Your code is affected by" in text or "No vulnerabilities found" in text
    parsed = parse_govulncheck(text)
    parsed["raw"] = save(deps, f"go__{slug(d, root)}.txt", text)
    record("govulncheck", d, ok, save(deps, f"go__{slug(d, root)}.json", json.dumps(parsed, indent=2)) if ok else None,
           "" if ok else text[-500:])


# ---------- global installs (no lockfile): enumerate bundled packages and ask OSV ----------

def bundled_npm_packages(root_dir):
    """Every name@version found in package.json files under a global node_modules tree."""
    found = defaultdict(set)
    if not root_dir or not os.path.isdir(root_dir):
        return found
    for cur, dirs, files in os.walk(root_dir):
        dirs[:] = [x for x in dirs if x not in (".bin", "test", "tests", "__tests__", "fixtures", "example", "examples")]
        parent = os.path.dirname(cur)
        is_package_dir = os.path.basename(parent) == "node_modules" or (
            os.path.basename(parent).startswith("@") and os.path.basename(os.path.dirname(parent)) == "node_modules")
        if is_package_dir and "package.json" in files:
            try:
                with open(os.path.join(cur, "package.json"), encoding="utf-8") as f:
                    pj = json.load(f)
            except (OSError, ValueError):
                continue
            if isinstance(pj.get("name"), str) and isinstance(pj.get("version"), str):
                top = os.path.relpath(cur, root_dir).split(os.sep)
                owner = "/".join(top[:2]) if top[0].startswith("@") else top[0]
                found[(pj["name"], pj["version"])].add(owner)
    return found


def osv_post(path, body):
    req = urllib.request.Request(f"{OSV}/{path}", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def osv_get(vid, cache):
    if vid not in cache:
        with urllib.request.urlopen(f"{OSV}/vulns/{vid}", timeout=60) as r:
            cache[vid] = json.load(r)
    return cache[vid]


def osv_scan(packages, ecosystem):
    """packages: {(name, version): owners}. Returns OSV records joined to the packages they affect."""
    keys = sorted(packages)
    hits, cache = [], {}
    for i in range(0, len(keys), 500):
        chunk = keys[i:i + 500]
        res = osv_post("querybatch", {"queries": [{"package": {"name": n, "ecosystem": ecosystem}, "version": v} for n, v in chunk]})
        for (n, v), r in zip(chunk, res.get("results", [])):
            for vuln in r.get("vulns", []) or []:
                hits.append({"name": n, "version": v, "owners": sorted(packages[(n, v)]), "id": vuln["id"]})
    for h in hits:
        h["osv"] = osv_get(h["id"], cache)
    return hits


def scan_globals(inv, deps):
    for label, root_dir in (("npm-global", inv.get("npm_global_root")), ("bun-global", inv.get("bun_global_root"))):
        try:
            pk = bundled_npm_packages(root_dir)
            hits = osv_scan(pk, "npm") if pk else []
            out = save(deps, f"osv__{label}.json", json.dumps({"root": root_dir, "packages_checked": len(pk), "hits": hits}, indent=2))
            record("osv-" + label, root_dir or "(none)", True, out, f"{len(pk)} bundled packages checked")
        except Exception as e:  # network or parse failure: report it, keep scanning the rest
            record("osv-" + label, root_dir or "(none)", False, None, repr(e))
    tools = {(t["name"], t["version"]): {"uv tool"} for t in inv.get("uv_tools") or []}
    try:
        hits = osv_scan(tools, "PyPI") if tools else []
        out = save(deps, "osv__uv-tools.json", json.dumps({"packages_checked": len(tools), "hits": hits}, indent=2))
        record("osv-uv-tools", "uv tool list", True, out, f"{len(tools)} tools checked")
    except Exception as e:
        record("osv-uv-tools", "uv tool list", False, None, repr(e))


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    a = ap.parse_args()
    run_dir = a.run
    with open(os.path.join(run_dir, "run.json"), encoding="utf-8-sig") as f:
        cfg = json.load(f)
    with open(os.path.join(run_dir, "inventory.json"), encoding="utf-8-sig") as f:
        inv = json.load(f)
    root = cfg["projects_root"]
    deps = os.path.join(run_dir, "deps")
    work = os.path.join(run_dir, "work")
    os.makedirs(deps, exist_ok=True)

    by_dir = defaultdict(set)
    for m in inv.get("manifests") or []:
        by_dir[os.path.dirname(m)].add(os.path.basename(m))

    solutions = [os.path.join(d, f) for d, fs in by_dir.items() for f in fs if f.endswith((".sln", ".slnx"))]
    sln_text = {}
    for s in solutions:
        with open(s, encoding="utf-8-sig", errors="replace") as fh:
            sln_text[s] = fh.read().lower()

    def in_a_solution(csproj):
        """True when a solution in this folder or above lists the project; otherwise it is scanned on its own."""
        name = os.path.basename(csproj).lower()
        return any(csproj.lower().startswith(os.path.dirname(s).lower() + os.sep) and name in t for s, t in sln_text.items())

    dockerfiles = []

    for d, files in sorted(by_dir.items()):
        lower = {f.lower() for f in files}
        if "uv.lock" in lower:
            scan_uv(d, root, deps)
        elif "pyproject.toml" in lower:
            scan_unlocked_python(os.path.join(d, "pyproject.toml"), root, deps, work)
        for f in sorted(files):
            if re.match(r"requirements.*\.txt$", f, re.I):
                scan_unlocked_python(os.path.join(d, f), root, deps, work)
        if "package-lock.json" in lower:
            scan_npm(d, root, deps)
        elif lower & {"pnpm-lock.yaml", "yarn.lock", "bun.lock", "bun.lockb"}:
            record("js-lockfile", d, False, None, "pnpm, yarn and bun lockfiles are not scanned by this skill; audit by hand")
        for f in files:
            if f.endswith(".csproj") and not in_a_solution(os.path.join(d, f)):
                scan_dotnet(os.path.join(d, f), root, deps)
        if "go.mod" in lower:
            scan_go(d, root, deps)
        if "dockerfile" in lower:
            with open(os.path.join(d, "Dockerfile"), encoding="utf-8", errors="replace") as fh:
                dockerfiles.append({"path": os.path.join(d, "Dockerfile"),
                                    "from": [l.strip() for l in fh if l.strip().upper().startswith("FROM ")]})
        if "cargo.lock" in lower or "gemfile.lock" in lower or "composer.lock" in lower:
            record("other-lockfile", d, False, None, "Cargo, Gemfile and composer lockfiles are not scanned by this skill")

    for s in sorted(solutions):
        scan_dotnet(s, root, deps)
    scan_globals(inv, deps)
    save(deps, "dockerfiles.json", json.dumps(dockerfiles, indent=2))

    with open(os.path.join(deps, "scan_status.json"), "w", encoding="utf-8") as f:
        json.dump({"skill_version": SKILL_VERSION, "scans": status}, f, indent=2)
    failed = [s for s in status if not s["ok"]]
    print(f"scans: {len(status)} run, {len(failed)} not completed")
    for s in failed:
        print(f"  NOT SCANNED  {s['kind']:<18} {s['target']}  {s['note'][:160]}")


if __name__ == "__main__":
    main()
