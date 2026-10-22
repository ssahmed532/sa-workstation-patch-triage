# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Check the filled page before it is published: no template placeholder, sample block or template comment left,
both body markers still there, and the checkbox key set to this run.

Usage: uv run check_page.py --run RUN
Reads RUN/patch-triage.html. Prints "page OK" and exits 0, or lists each problem with its line number and exits 1.
"""
import argparse
import os
import re
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    run_dir = ap.parse_args().run
    page = os.path.join(run_dir, "patch-triage.html")
    with open(page, encoding="utf-8") as f:
        lines = f.read().splitlines()
    text = "\n".join(lines)

    problems = []
    for n, line in enumerate(lines, 1):
        for name in re.findall(r"\{\{\s*([A-Z_]+)\s*\}\}", line):
            problems.append(f"line {n}: placeholder {name} is not filled in")
        if re.search(r"<!--\s*sample", line):
            problems.append(f"line {n}: a sample block from the template is still there")
        if "Report template for sa-workstation-patch-triage" in line:
            problems.append(f"line {n}: the template's instruction comment is still there; delete it")
    for marker in ("<!-- BODY START -->", "<!-- BODY END -->"):
        if marker not in text:
            problems.append(f"marker {marker} is missing; the body must stay between the two markers")
    key = "patch-triage-" + os.path.basename(os.path.normpath(run_dir))
    if key not in text:
        problems.append(f"the checkbox key should be '{key}' (RUN_ID is the run folder name)")

    if problems:
        print(f"{page}: {len(problems)} problem(s)")
        for p in problems:
            print("  " + p)
        sys.exit(1)
    print("page OK")


if __name__ == "__main__":
    main()
