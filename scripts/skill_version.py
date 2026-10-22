"""The skill's version, read from the SKILL.md front matter so it is stated in one place only.

Every script stamps it into what it writes (run.json, inventory.json, findings.json) and the report footer
shows it. To release a new version, change `version:` in SKILL.md and nothing else here.
"""
import os
import re

_SKILL_MD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "SKILL.md")


def skill_version():
    with open(_SKILL_MD, encoding="utf-8") as f:
        m = re.search(r'^\s+version:\s*"?([0-9][\w.]*)"?\s*$', f.read(), re.M)
    return m.group(1) if m else "unknown"


SKILL_VERSION = skill_version()
