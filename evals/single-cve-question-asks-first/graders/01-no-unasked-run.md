---
type: llm
focus: trace
weight: 1
---

Every Bash or PowerShell command in the trace, if there is any, runs something other than setup_run.py, collect_inventory.ps1 or scan_dependencies.py. A trace with no shell command at all passes.
