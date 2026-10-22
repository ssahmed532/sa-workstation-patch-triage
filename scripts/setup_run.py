# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Create the run folder, resolve the window and the previous run, and write RUN/run.json.

Usage: uv run setup_run.py [--window-hours N] [--dry-run]
Prints the run folder path on the last line so the caller can pick it up.
Stops before creating anything if PowerShell 7 is missing, and notes the optional tools that are missing.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone

sys.dont_write_bytecode = True  # the skill folder may be read-only or replaced by an update; write nothing into it
from skill_version import SKILL_VERSION  # noqa: E402

SKILL_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
USER_CONFIG = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "sa-workstation-patch-triage", "config.json")
REQUIRED = {"projects_root": str, "runs_root": str}
OPTIONAL = {"artifact_url": str, "window_hours": int, "timezone_label": str, "exclude_dirs": list, "risky_ports": list,
            "runtime_search_roots": list}
MIN_DOTNET_SDK = (9, 0, 300)  # first SDK with `dotnet list package --vulnerable`


def config_path():
    """The user's config first, then the one next to SKILL.md, then the example (which keeps the run dry)."""
    for p in (USER_CONFIG, os.path.join(SKILL_DIR, "config.local.json")):
        if os.path.exists(p):
            return p
    return os.path.join(SKILL_DIR, "config.example.json")


def load_config():
    path = config_path()
    try:
        with open(path, encoding="utf-8-sig") as f:
            cfg = json.load(f)
    except ValueError as e:
        sys.exit(f"{path} is not valid JSON: {e}")
    for key, typ in REQUIRED.items():
        if not isinstance(cfg.get(key), typ) or not cfg.get(key):
            sys.exit(f"{path}: '{key}' is missing or not a {typ.__name__}. See config.example.json.")
    for key, typ in OPTIONAL.items():
        if key in cfg and not isinstance(cfg[key], typ):
            sys.exit(f"{path}: '{key}' should be a {typ.__name__}.")
    for key in sorted(set(cfg) - set(REQUIRED) - set(OPTIONAL)):
        print(f"note: {path}: '{key}' is not a setting this version reads; it is ignored.", file=sys.stderr)
    cfg["_config_file"] = path
    return cfg


def previous_run(runs_root, current):
    if not os.path.isdir(runs_root):
        return None
    runs = sorted(
        d for d in os.listdir(runs_root)
        if d != os.path.basename(current) and os.path.exists(os.path.join(runs_root, d, "findings.json"))
    )
    return os.path.join(runs_root, runs[-1]) if runs else None


# tool -> what a run loses without it (scan_dependencies.py records the affected projects as NOT SCANNED)
OPTIONAL_TOOLS = {
    "gh": "severity and publish dates come from OSV only (sign in with `gh auth login` for the GitHub Advisory Database)",
    "npm": "npm projects and global npm packages are not audited",
    "dotnet": ".NET projects are not audited",
    "go": "Go projects are not audited",
}


def version_tuple(text):
    return tuple(int(x) for x in re.findall(r"\d+", text)[:3])


def check_tools():
    if not shutil.which("pwsh"):
        sys.exit("PowerShell 7 (pwsh) is not on PATH, and the inventory step needs it. "
                 "Install it with `winget install --id Microsoft.PowerShell`, then run again.")
    # `uv audit` is what scans uv projects; older uv builds do not have it
    probe = subprocess.run([shutil.which("uv") or "uv", "audit", "--help"], capture_output=True, text=True)
    if probe.returncode != 0:
        sys.exit("This uv has no `uv audit` command, which the dependency scan needs. "
                 "Upgrade uv (`uv self update`), then run again.")
    for tool, loss in OPTIONAL_TOOLS.items():
        if not shutil.which(tool):
            print(f"note: {tool} is not on PATH: {loss}.", file=sys.stderr)
    dotnet = shutil.which("dotnet")
    if dotnet:
        v = subprocess.run([dotnet, "--version"], capture_output=True, text=True).stdout.strip()
        if v and version_tuple(v) < MIN_DOTNET_SDK:
            print(f"note: .NET SDK {v} is older than {'.'.join(map(str, MIN_DOTNET_SDK))}, which is the first with "
                  "`dotnet list package --vulnerable`: .NET projects are not audited.", file=sys.stderr)


def expand(path):
    return os.path.normpath(os.path.expandvars(os.path.expanduser(path)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-hours", type=int)
    ap.add_argument("--dry-run", action="store_true", help="write the report locally, do not publish")
    a = ap.parse_args()

    check_tools()
    cfg = load_config()
    print(f"config: {cfg['_config_file']}", file=sys.stderr)
    if os.path.basename(cfg["_config_file"]) == "config.example.json":
        print(f"note: no config at {USER_CONFIG}, so the example is used and this run is dry. "
              "Copy config.example.json there and set artifact_url.", file=sys.stderr)
    now_utc = datetime.now(timezone.utc)
    now_local = now_utc.astimezone()  # the machine's time zone, so daylight saving time is handled
    window = a.window_hours or cfg.get("window_hours", 24)

    runs_root = expand(cfg["runs_root"])
    # a later run on the same day, or in the same minute, never reuses an earlier run's folder
    run_dir = next(d for d in (os.path.join(runs_root, now_local.strftime(f)) for f in ("%Y-%m-%d", "%Y-%m-%d-%H%M", "%Y-%m-%d-%H%M%S"))
                   if not os.path.exists(d))
    os.makedirs(os.path.join(run_dir, "raw"))
    os.makedirs(os.path.join(run_dir, "deps"))

    artifact_url = cfg.get("artifact_url") or ""
    run = {
        "skill_version": SKILL_VERSION,
        "config_file": cfg["_config_file"],
        "started_utc": now_utc.isoformat(timespec="seconds"),
        "started_local": now_local.strftime("%Y-%m-%d %H:%M"),
        "timezone_label": cfg.get("timezone_label") or now_local.tzname(),
        "window_hours": window,
        "since_utc": (now_utc - timedelta(hours=window)).isoformat(timespec="seconds"),
        "recent_cutoff_utc": (now_utc - timedelta(hours=max(window, 72))).isoformat(timespec="seconds"),
        "projects_root": expand(cfg["projects_root"]),
        "exclude_dirs": cfg.get("exclude_dirs", []),
        "risky_ports": cfg.get("risky_ports", []),
        "runtime_search_roots": [expand(p) for p in cfg.get("runtime_search_roots") or ["%SystemDrive%\\"]],
        "artifact_url": artifact_url,
        "dry_run": a.dry_run or not artifact_url,
        "previous_run": previous_run(runs_root, run_dir),
        "run_dir": run_dir,
    }
    with open(os.path.join(run_dir, "run.json"), "w", encoding="utf-8") as f:
        json.dump(run, f, indent=2)

    print(json.dumps({k: run[k] for k in ("skill_version", "config_file", "window_hours", "since_utc", "dry_run", "previous_run")}))
    if not artifact_url:
        print("artifact_url is empty in config: this run writes the report locally only.", file=sys.stderr)
    prev_json = os.path.join(run["previous_run"] or "", "run.json")
    if run["previous_run"] and os.path.exists(prev_json):
        with open(prev_json, encoding="utf-8-sig") as f:
            prev = json.load(f)
        for key in ("config_file", "projects_root"):
            if prev.get(key) != run[key]:
                print(f"note: {key} differs from the previous run ({prev.get(key)} -> {run[key]}); "
                      "the delta may include changes caused by that.", file=sys.stderr)
    print(run_dir)


if __name__ == "__main__":
    main()
