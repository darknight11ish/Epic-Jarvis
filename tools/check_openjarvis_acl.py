#!/usr/bin/env python3
"""Say whether ~/.openjarvis is readable only by the owner.

    py -3 tools/check_openjarvis_acl.py
    py -3 tools/check_openjarvis_acl.py --home <a folder>

Audit DATA D2 (2026-10-18): the personal databases in the settings folder are
NOT encrypted at rest (`memory.db`, `voiceprint.db`, `receipts.db`, ...), so the
Windows DACL is the boundary that keeps another account on this PC from reading
them. This checker reads one `icacls <folder>` listing and NAMES every ACE that
is not the owner, SYSTEM or Administrators (Everyone, Users, Authenticated
Users, a second local account). It changes nothing and needs no administrator.

Exit codes: 0 = only owner/SYSTEM/Administrators (or not Windows - it prints
SKIPPED and that NOTHING was checked), 1 = a foreign or world ACE was found,
2 = the folder could not be read. The same parser the weekly backup tool runs
(a WARNING there, never a refused backup).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jarvis_data_backup as jdb  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="check_openjarvis_acl.py")
    parser.add_argument("--home", default=None,
                        help="the settings folder to read (default: the one Jarvis uses)")
    args = parser.parse_args(argv)
    home = Path(args.home) if args.home else jdb.default_source()
    if os.name != "nt":
        print("SKIPPED: Windows ACLs can only be read on Windows "
              f"(sys.platform is {sys.platform!r}); NOTHING was checked here.")
        return 0
    if not home.is_dir():
        print(f"Nothing was checked: {home} is not a folder.")
        return 2
    problems = jdb.acl_problems(home)
    if problems:
        print(f"FAIL  {home} is readable by more than its owner "
              f"({len(problems)} ACE(s)):")
        for problem in problems:
            print(f"        {problem}")
        print("        The databases there are not encrypted at rest. Remove the extra "
              "ACEs with icacls, or move Jarvis's data to a folder only this account "
              "can read.")
        return 1
    print(f"ok    {home}: only the owner, SYSTEM and Administrators are listed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
