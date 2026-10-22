# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Create the run folder, resolve the window and the previous run, and write RUN/run.json.

Usage: uv run setup_run.py [--window-hours N] [--dry-run]
Prints the run folder path on the last line so the caller can pick it up.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

from skill_version import SKILL_VERSION

SKILL_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def load_config():
    local = os.path.join(SKILL_DIR, "config.local.json")
    example = os.path.join(SKILL_DIR, "config.example.json")
    path = local if os.path.exists(local) else example
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["_config_file"] = os.path.basename(path)
    return cfg


def previous_run(runs_root, current):
    if not os.path.isdir(runs_root):
        return None
    runs = sorted(
        d for d in os.listdir(runs_root)
        if d != os.path.basename(current) and os.path.exists(os.path.join(runs_root, d, "findings.json"))
    )
    return os.path.join(runs_root, runs[-1]) if runs else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-hours", type=int)
    ap.add_argument("--dry-run", action="store_true", help="write the report locally, do not publish")
    a = ap.parse_args()

    cfg = load_config()
    offset = timedelta(hours=cfg.get("utc_offset_hours", 5))
    now_utc = datetime.now(timezone.utc)
    now_local = now_utc + offset
    window = a.window_hours or cfg.get("window_hours", 24)

    runs_root = os.path.expandvars(os.path.expanduser(cfg["runs_root"]))
    name = now_local.strftime("%Y-%m-%d")
    run_dir = os.path.join(runs_root, name)
    if os.path.exists(run_dir):  # second run on the same day keeps the first one intact
        run_dir = os.path.join(runs_root, now_local.strftime("%Y-%m-%d-%H%M"))
    os.makedirs(os.path.join(run_dir, "raw"), exist_ok=True)
    os.makedirs(os.path.join(run_dir, "deps"), exist_ok=True)

    artifact_url = cfg.get("artifact_url") or ""
    run = {
        "skill_version": SKILL_VERSION,
        "config_file": cfg["_config_file"],
        "started_utc": now_utc.isoformat(timespec="seconds"),
        "started_local": now_local.strftime("%Y-%m-%d %H:%M"),
        "timezone_label": cfg.get("timezone_label", "PKT"),
        "utc_offset_hours": cfg.get("utc_offset_hours", 5),
        "window_hours": window,
        "since_utc": (now_utc - timedelta(hours=window)).isoformat(timespec="seconds"),
        "recent_cutoff_utc": (now_utc - timedelta(hours=max(window, 72))).isoformat(timespec="seconds"),
        "projects_root": cfg["projects_root"],
        "exclude_dirs": cfg.get("exclude_dirs", []),
        "risky_ports": cfg.get("risky_ports", []),
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
