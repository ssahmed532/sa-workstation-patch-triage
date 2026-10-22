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
    # advisory titles and vendor text are copied into the body unescaped; the only script on the page is the template's
    body = re.search(r"<!-- BODY START -->(.*)<!-- BODY END -->", text, re.S)
    if body:
        first = text[:body.start()].count("\n") + 1
        for n, line in enumerate(body.group(1).splitlines(), first):
            if re.search(r"<script\b", line, re.I):
                problems.append(f"line {n}: a <script> tag inside the body; scripts belong only in the template, outside the markers")
            if re.search(r"javascript:", line, re.I):
                problems.append(f"line {n}: a javascript: URL inside the body")
    key = "patch-triage-" + os.path.basename(os.path.normpath(run_dir))
    if key not in text:
        problems.append(f"the checkbox key should be '{key}' (RUN_ID is the run folder name)")

    if problems:
        print(f"{page}: {len(problems)} problem(s)")
        for p in problems:
            print("  " + p)
        sys.exit(1)
    print("page OK")
    # the page is published without a document skeleton (the Artifact wrapper adds one); this copy has it, so it opens from disk
    local = os.path.join(run_dir, "patch-triage.local.html")
    with open(local, "w", encoding="utf-8") as f:
        f.write('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width, initial-scale=1">\n</head>\n<body>\n'
                + text + '\n</body>\n</html>\n')
    print(f"local copy: {local}")


if __name__ == "__main__":
    main()
