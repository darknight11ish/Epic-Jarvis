#!/usr/bin/env python3
"""Writes "PC help"'s golden files, and checks them.

    python3 tools/gen_pc_help_cases.py            # write both files
    python3 tools/gen_pc_help_cases.py --check    # compare only

jarvis-desktop/tests/fixtures/pc-help-cases.json and the phone's
byte-identical copy, contract/pc-help-cases.json: what GET /api/pc/help
really answers (jarvis_pc_help.read()), in named situations, made by the
real code with made-up readings. Both apps read the answer as it is; the
desktop's tests/pc-help.mjs and the phone's PcHelpContractTest build
against these.

WHAT THE INPUTS ARE. Program names, sizes and temperatures are all MADE UP
to look like real ones. None was read on the owner's PC. The clock is fixed
and the time zone is UTC, so the file is the same on every machine.
"""
import json
import os
import sys
import time
from pathlib import Path

os.environ["TZ"] = "UTC"
if hasattr(time, "tzset"):
    time.tzset()

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
for p in (BACKEND, BACKEND / "rebuilt"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import jarvis_pc_help as PCH  # noqa: E402

DESKTOP = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "pc-help-cases.json"
PHONE = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
         / "pc-help-cases.json")

GB = 1024 ** 3
MB = 1024 ** 2
#: Monday 28 September 2026, 10:00 UTC.
NOW = 1790589600.0
OWN_PID = 4242


def _const(v):
    return lambda: v


def readers(*, programs=None, memory=None, disks=None, uptime=None, cards=None,
            models=None) -> PCH.Readers:
    return PCH.Readers(programs=_const(programs), memory=_const(memory), disks=_const(disks),
                       uptime=_const(uptime), cards=_const(cards), models=_const(models),
                       now=_const(NOW), own_pid=OWN_PID)


BUSY_PROGRAMS = {
    "cores": 8, "cpu_percent": 91.0,
    "procs": [
        {"name": "chrome", "pid": 100, "cpu": 180.0, "mem_bytes": 1.6 * GB},
        {"name": "chrome#1", "pid": 101, "cpu": 60.0, "mem_bytes": 0.9 * GB},
        {"name": "ollama", "pid": 200, "cpu": 300.0, "mem_bytes": 0.4 * GB},
        {"name": "Teams", "pid": 300, "cpu": 40.0, "mem_bytes": 0.7 * GB},
        {"name": "python", "pid": OWN_PID, "cpu": 8.0, "mem_bytes": 0.3 * GB},
        {"name": "Idle", "pid": 0, "cpu": 20.0, "mem_bytes": 0},
        {"name": "_Total", "pid": 0, "cpu": 700.0, "mem_bytes": 9 * GB},
    ],
    "gpu": [{"pid": 200, "bytes": 5.4 * GB}, {"pid": 100, "bytes": 0.3 * GB},
            {"pid": 300, "bytes": 0.2 * GB}],
}
CALM_PROGRAMS = {
    "cores": 8, "cpu_percent": 6.0,
    "procs": [
        {"name": "explorer", "pid": 10, "cpu": 16.0, "mem_bytes": 0.2 * GB},
        {"name": "Code", "pid": 11, "cpu": 24.0, "mem_bytes": 0.6 * GB},
    ],
    "gpu": [],
}
CARD = {"name": "NVIDIA GeForce RTX 2080 SUPER", "used_mib": 6200, "total_mib": 8192,
        "temp_c": 67, "hot_slowdown": False, "load_percent": 88}
HOT_CARD = dict(CARD, temp_c=86, hot_slowdown=True)
DISKS = [{"drive": "C:", "total_bytes": 500 * GB, "free_bytes": 32 * GB},
         {"drive": "D:", "total_bytes": 2000 * GB, "free_bytes": 810 * GB}]
MODEL = [{"name": "qwen3:8b", "vram_bytes": 5.4 * GB}]

CASES = {
    "busy": readers(programs=BUSY_PROGRAMS,
                    memory={"total_bytes": 16 * GB, "available_bytes": 3 * GB},
                    disks=DISKS, uptime=4 * 86400 + 3600, cards=[CARD], models=MODEL),
    "calm": readers(programs=CALM_PROGRAMS,
                    memory={"total_bytes": 32 * GB, "available_bytes": 24 * GB},
                    disks=DISKS[1:], uptime=2 * 3600, cards=[CARD], models=[]),
    "hot": readers(programs=BUSY_PROGRAMS,
                   memory={"total_bytes": 16 * GB, "available_bytes": 1 * GB},
                   disks=DISKS, uptime=26 * 3600, cards=[HOT_CARD], models=MODEL),
    "no_nvidia": readers(programs=CALM_PROGRAMS,
                         memory={"total_bytes": 16 * GB, "available_bytes": 10 * GB},
                         disks=DISKS, uptime=600, cards=[], models=None),
    "nothing_read": readers(),
}


def build() -> str:
    doc = {"_note": ("Made by tools/gen_pc_help_cases.py from jarvis_pc_help.read(). Every "
                     "reading is made up. Do not edit by hand."),
           "path": PCH.PATH,
           "titles": PCH.TITLES,
           "cases": {name: PCH.read(r) for name, r in CASES.items()}}
    return json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main() -> int:
    text = build()
    check = "--check" in sys.argv[1:]
    bad = []
    for path in (DESKTOP, PHONE):
        have = path.read_text(encoding="utf-8") if path.exists() else None
        if have == text:
            continue
        if check:
            bad.append(path)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            # newline="\n": without it a stale file would be rewritten CRLF on
            # Windows and LF elsewhere (the repository is LF everywhere).
            path.write_text(text, encoding="utf-8", newline="\n")
            print(f"wrote {path.relative_to(ROOT)}")
    if bad:
        for p in bad:
            print(f"OUT OF DATE: {p.relative_to(ROOT)} - run python3 tools/gen_pc_help_cases.py")
        return 1
    if check:
        print("pc-help cases: up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
