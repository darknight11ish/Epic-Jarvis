#!/bin/bash
# quick repo checks in the given worktree
cd "$1" || exit 1
for g in tools/gen_*_cases.py; do python3 $g --check >/dev/null 2>&1 || echo "GEN FAIL $g"; done
python3 tools/check_parity.py 2>&1 | tail -2
python3 tools/build_patch_history.py --check 2>&1 | tail -1
/opt/pwsh/pwsh -NoProfile -Command '$e=$null; [System.Management.Automation.Language.Parser]::ParseFile("'"$1"'/scripts/apply-patches.ps1", [ref]$null, [ref]$e) | Out-Null; "ps errors: " + $e.Count'
