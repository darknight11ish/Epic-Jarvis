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

#: Card ids, matching the hardware cases' own made-up ids so the same machine
#: is described the same way in both fixtures.
U_2080S = "GPU-3f2a9c1e-7b1d-4e8a-9c55-0d4b2e6a8f10"
U_2060 = "GPU-8b7e2d44-1c9a-4f3e-a2b6-5e9d0c7f1a23"
U_TWIN = "GPU-7d1c5b93-2a4e-4f60-8b17-c3e9a04f6d28"


def _const(v):
    return lambda: v


def readers(*, programs=None, memory=None, disks=None, uptime=None, cards=None,
            models=None, apps=None) -> PCH.Readers:
    return PCH.Readers(programs=_const(programs), memory=_const(memory), disks=_const(disks),
                       uptime=_const(uptime), cards=_const(cards), models=_const(models),
                       apps=_const(apps) if apps is not None else None,
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
#: The shapes jarvis_hardware's richer card reading sends since 2026-10-17:
#: identity, per-card memory, heat/power/fan/load, pstate, clocks and the two
#: driver flags. CARD is a working 2080 SUPER; IDLE_CARD the same card resting
#: (the state this PC's two cards are in); the 2060 is the measured display-
#: less card nearly full with Jarvis's model on it, its power-cap flag Active
#: while resting - the trap the words must not call throttling.
CARD = {"name": "NVIDIA GeForce RTX 2080 SUPER", "uuid": U_2080S,
        "pci_id": "00000000:0a:00.0", "display_active": True, "index": 0,
        "used_mib": 6200, "total_mib": 8192, "free_mib": 1992,
        "temp_c": 67, "hot_slowdown": False, "load_percent": 88,
        "power_w": 182.4, "power_limit_w": 250.0, "fan_percent": 48,
        "pstate": "P0", "clock_mhz": 1935, "max_clock_mhz": 2100,
        "idle": False, "power_capped": False, "state": "working"}
IDLE_CARD = dict(CARD, used_mib=2058, free_mib=6134, temp_c=35, load_percent=0,
                 power_w=21.06, fan_percent=0, pstate="P8", clock_mhz=300,
                 max_clock_mhz=2130, idle=True, state="idle")
HOT_CARD = dict(CARD, temp_c=86, hot_slowdown=True, used_mib=7800, free_mib=392,
                state="hot")
CARD_2060 = {"name": "NVIDIA GeForce RTX 2060", "uuid": U_2060,
             "pci_id": "00000000:0b:00.0", "display_active": False, "index": 1,
             "used_mib": 11919, "total_mib": 12288, "free_mib": 369,
             "temp_c": 29, "hot_slowdown": False, "load_percent": 0,
             "power_w": 11.6, "power_limit_w": 184.0, "fan_percent": 0,
             "pstate": "P8", "clock_mhz": 300, "max_clock_mhz": 2145,
             "idle": False, "power_capped": True, "state": "idle"}

_OLLAMA = (r"C:\Users\pcadmin\AppData\Local\Programs\Ollama\lib\ollama"
           r"\llama-server.exe")
_EXPLORER = r"C:\Windows\explorer.exe"
_BRAVE = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
#: nvidia-smi's own process list on this PC (2026-10-17): every row's amount is
#: [N/A], including the two llama-server.exe on the 2060 - which is why the
#: words may list the programs but must not invent an amount.
APPS_PAIR = [
    {"pid": 18120, "name": _OLLAMA, "uuid": U_2060, "used_mib": None},
    {"pid": 42708, "name": _OLLAMA, "uuid": U_2060, "used_mib": None},
    {"pid": 17548, "name": _EXPLORER, "uuid": U_2080S, "used_mib": None},
    {"pid": 10852, "name": _BRAVE, "uuid": U_2080S, "used_mib": None},
    {"pid": 3864, "name": _EXPLORER, "uuid": U_TWIN, "used_mib": None},
]
DISKS = [{"drive": "C:", "total_bytes": 500 * GB, "free_bytes": 32 * GB},
         {"drive": "D:", "total_bytes": 2000 * GB, "free_bytes": 810 * GB}]
MODEL = [{"name": "qwen3:8b", "vram_bytes": 5.4 * GB}]

CASES = {
    "busy": readers(programs=BUSY_PROGRAMS,
                    memory={"total_bytes": 16 * GB, "available_bytes": 3 * GB},
                    disks=DISKS, uptime=4 * 86400 + 3600, cards=[CARD], models=MODEL),
    "calm": readers(programs=CALM_PROGRAMS,
                    memory={"total_bytes": 32 * GB, "available_bytes": 24 * GB},
                    disks=DISKS[1:], uptime=2 * 3600, cards=[IDLE_CARD], models=[]),
    "hot": readers(programs=BUSY_PROGRAMS,
                   memory={"total_bytes": 16 * GB, "available_bytes": 1 * GB},
                   disks=DISKS, uptime=26 * 3600, cards=[HOT_CARD], models=MODEL),
    "no_nvidia": readers(programs=CALM_PROGRAMS,
                         memory={"total_bytes": 16 * GB, "available_bytes": 10 * GB},
                         disks=DISKS, uptime=600, cards=[], models=None),
    # The owner's PC today, from the numbers measured 2026-10-17: the 2060
    # headless and nearly full holding the model, the 2080 SUPER running the
    # desktop; the driver reports which programs hold each card but no amount
    # for any of them.
    "two_cards": readers(programs=BUSY_PROGRAMS,
                         memory={"total_bytes": 16 * GB, "available_bytes": 3 * GB},
                         disks=DISKS, uptime=4 * 86400 + 3600,
                         cards=[CARD_2060, IDLE_CARD],
                         models=[{"name": "qwen3:8b", "vram_bytes": 11.4 * GB}],
                         apps=APPS_PAIR),
    # The planned third card (a SECOND RTX 2080 SUPER 8 GB): two cards with the
    # same name and size, told apart by the monitor and then the id tail.
    "three_cards_twin": readers(programs=CALM_PROGRAMS,
                                memory={"total_bytes": 32 * GB,
                                        "available_bytes": 24 * GB},
                                disks=DISKS[1:], uptime=2 * 3600,
                                cards=[CARD_2060, IDLE_CARD,
                                       dict(IDLE_CARD, uuid=U_TWIN, index=2,
                                            pci_id="00000000:0c:00.0",
                                            display_active=False)],
                                models=[{"name": "qwen3:8b", "vram_bytes": 11.4 * GB}],
                                apps=APPS_PAIR),
    # Processor and memory are calm, but Jarvis's model's card is nearly full:
    # "why is my PC slow" must say that, and what to do about it.
    "full_quiet": readers(programs=CALM_PROGRAMS,
                          memory={"total_bytes": 32 * GB, "available_bytes": 24 * GB},
                          disks=DISKS[1:], uptime=3600,
                          cards=[CARD_2060],
                          models=[{"name": "qwen3:8b", "vram_bytes": 11.4 * GB}],
                          apps=APPS_PAIR),
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
