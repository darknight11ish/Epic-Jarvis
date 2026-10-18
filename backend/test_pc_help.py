"""test_pc_help.py - "PC help" (2026-09-28): five read-only questions about
this PC, answered without the model.

    python3 backend/test_pc_help.py

docs/JARVIS-API.md section 84. What is proved here, with fake readings (no
Windows, no PowerShell, no nvidia-smi, no Ollama):

  * PowerShell's JSON is read right: a one-item list written as an object,
    the process id inside a graphics-card counter's name, rubbish -> None;
  * programs are merged by name ("chrome" and "chrome#1"), Windows' per-core
    figure is turned into a share of the whole processor, "_Total" and
    "Idle" are not programs, Ollama is named as Jarvis's AI model and this
    backend as Jarvis itself;
  * each answer's words; a reading that fails, or throws, says so plainly
    and never raises;
  * PRIVATE: an answer that names programs is private and marks the turn as
    having read outside text; one that does not, is neither. Nothing is
    printed while reading, the module writes no file, logs nothing, opens
    no socket of its own, never imports jarvis_gate - and the real readers,
    run on a PC that is not Windows with sockets refused, still never raise;
  * the grammar: the owner's questions match their topic, and near misses
    ("why is my PC slow to boot after the update?", "how hot is it today?")
    go to the model;
  * the fast path: answered here, `gate: "private"` when programs are named;
  * the Pillar 28 silent-failure doctor (2026-10-17): a microphone returning
    three 0.0-RMS voice attempts in a row, a database write-ahead log past
    64 MiB, a paired phone that stopped checking in, and the model service
    not running vs running with its TCP port open and /api/ps timed out -
    each with invented readings here, each adding ONE named warning section
    only when it finds something, never a number it was not given;
  * GET /api/pc/help through jarvis_brain_reads, and the shared fixture is
    up to date (tools/gen_pc_help_cases.py --check);
  * not a tool the AI model can call; shipped by the script and _where;
  * both apps use the same labels.
"""
from __future__ import annotations

import ast
import contextlib
import io
import os
import socket
import subprocess
import sys
import tempfile
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_pc_help.py", "jarvis_quick.py", "jarvis_brain_reads.py")
_TMP = tempfile.mkdtemp(prefix="jarvis-pc-help-")
os.environ["JARVIS_SCHEDULE_DB"] = os.path.join(_TMP, "schedule.db")
os.environ["OPENJARVIS_CONFIG_DIR"] = _TMP
sys.path.append(str(HERE / "rebuilt"))
import jarvis_brain_reads as BR  # noqa: E402
import jarvis_pc_help as PCH  # noqa: E402
import jarvis_quick as Q  # noqa: E402

PASSED, FAILED = [], []
GB = 1024 ** 3
NOW = 1790589600.0
DAY = 86400
#: The four Readings Pillar 28 added; `fake()` wires them when a test passes them.
SILENT_READINGS = ("mic", "databases", "devices", "ollama")


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def _const(v):
    return lambda: v


def fake(**kw) -> PCH.Readers:
    base = dict(programs=None, memory=None, disks=None, uptime=None, cards=None, models=None)
    silent = {name: kw.pop(name) for name in SILENT_READINGS if name in kw}
    base.update(kw)
    apps = _const(base.pop("apps", None))
    return PCH.Readers(**{k: _const(v) for k, v in base.items()}, apps=apps,
                       **{k: _const(v) for k, v in silent.items()},
                       now=_const(NOW), own_pid=4242)


PROGRAMS = {
    "cores": 4, "cpu_percent": 93.0,
    "procs": [
        {"name": "chrome", "pid": 1, "cpu": 120.0, "mem_bytes": 1.0 * GB},
        {"name": "chrome#1", "pid": 2, "cpu": 40.0, "mem_bytes": 0.5 * GB},
        {"name": "ollama", "pid": 3, "cpu": 200.0, "mem_bytes": 0.3 * GB},
        {"name": "python", "pid": 4242, "cpu": 4.0, "mem_bytes": 0.2 * GB},
        {"name": "_Total", "pid": 0, "cpu": 400.0, "mem_bytes": 9 * GB},
        {"name": "Idle", "pid": 0, "cpu": 30.0, "mem_bytes": 0},
        {"name": "evil\x1b[31mname.exe", "pid": 9, "cpu": 8.0, "mem_bytes": 0.1 * GB},
    ],
    "gpu": [{"pid": 3, "bytes": 5.0 * GB}, {"pid": 1, "bytes": 0.4 * GB}],
}
CARD = {"name": "NVIDIA GeForce RTX 2080 SUPER", "used_mib": 6000, "total_mib": 8192,
        "temp_c": 70, "hot_slowdown": None, "load_percent": 50}

#: The richer card reading jarvis_hardware sends since 2026-10-17 (identity,
#: per-card memory, heat/power/fan/load, pstate and the state word), and
#: nvidia-smi's own process list with no amounts - the measured shape on this
#: PC (2026-10-17: used_memory is [N/A] for every process).
U_2080S = "GPU-3f2a9c1e-7b1d-4e8a-9c55-0d4b2e6a8f10"
U_2060 = "GPU-8b7e2d44-1c9a-4f3e-a2b6-5e9d0c7f1a23"
U_TWIN = "GPU-7d1c5b93-2a4e-4f60-8b17-c3e9a04f6d28"
WORKING = {"name": "NVIDIA GeForce RTX 2080 SUPER", "uuid": U_2080S,
           "pci_id": "00000000:0a:00.0", "display_active": True, "index": 0,
           "used_mib": 6200, "total_mib": 8192, "free_mib": 1992,
           "temp_c": 67, "hot_slowdown": False, "load_percent": 88,
           "power_w": 182.4, "power_limit_w": 250.0, "fan_percent": 48,
           "pstate": "P0", "clock_mhz": 1935, "max_clock_mhz": 2100,
           "idle": False, "power_capped": False, "state": "working"}
RESTING = {"name": "NVIDIA GeForce RTX 2060", "uuid": U_2060,
           "pci_id": "00000000:0b:00.0", "display_active": False, "index": 1,
           "used_mib": 11919, "total_mib": 12288, "free_mib": 369,
           "temp_c": 29, "hot_slowdown": False, "load_percent": 0,
           "power_w": 11.6, "power_limit_w": 184.0, "fan_percent": 0,
           "pstate": "P8", "clock_mhz": 300, "max_clock_mhz": 2145,
           "idle": False, "power_capped": True, "state": "idle"}
HOT = dict(WORKING, temp_c=87, hot_slowdown=True, used_mib=7800, free_mib=392,
           state="hot")
TWIN = dict(WORKING, uuid=U_TWIN, pci_id="00000000:0c:00.0", display_active=False,
            index=2, used_mib=1000, free_mib=7192)
_OLLAMA = (r"C:\Users\pcadmin\AppData\Local\Programs\Ollama\lib\ollama"
           r"\llama-server.exe")
APPS = [
    {"pid": 18120, "name": _OLLAMA, "uuid": U_2060, "used_mib": None},
    {"pid": 42708, "name": _OLLAMA, "uuid": U_2060, "used_mib": None},
    {"pid": 17548, "name": r"C:\Windows\explorer.exe", "uuid": U_2080S,
     "used_mib": None},
]


def t_reading_powershell():
    one = PCH.parse_programs('{"procs": {"n": "chrome#2", "i": 7, "c": 12.5, "m": 1048576},'
                             ' "gpu": {"n": "pid_7_luid_0x0_0x1_phys_0", "b": 2048},'
                             ' "cpu": 40, "cores": 8}')
    check("a one-item list written as an object is still a list",
          one and len(one["procs"]) == 1 and one["procs"][0]["pid"] == 7, str(one))
    check("the process id is read out of a graphics-card counter's name",
          one and one["gpu"] == [{"pid": 7, "bytes": 2048.0}], str(one))
    check("the whole processor and the cores", one and one["cpu_percent"] == 40.0
          and one["cores"] == 8)
    check("rubbish is None", PCH.parse_programs("not json") is None
          and PCH.parse_programs("[1, 2]") is None and PCH.parse_programs("") is None)
    empty = PCH.parse_programs('{"procs": [], "gpu": [], "cpu": null, "cores": 2}')
    check("nothing running, no processor figure", empty == {"cores": 2, "cpu_percent": None,
                                                          "procs": [], "gpu": []}, str(empty))
    check("the PowerShell script has no double quotes (it is sent encoded anyway)",
          '"' not in PCH.PS_SCRIPT)


def t_programs_merged():
    rows = {r["name"]: r for r in PCH._programs(PROGRAMS, 4242)}
    check("chrome and chrome#1 are one program", "chrome" in rows and "chrome#1" not in rows
          and abs(rows["chrome"]["mem_bytes"] - 1.5 * GB) < 1, str(rows.keys()))
    check("per-core figures become a share of the whole processor (160 / 4 cores = 40%)",
          abs(rows["chrome"]["cpu"] - 40.0) < 0.01, str(rows["chrome"]))
    check("_Total and Idle are not programs", "_Total" not in rows and "Idle" not in rows)
    check("Ollama is Jarvis's AI model", PCH.MODEL_WORDS in rows
          and rows[PCH.MODEL_WORDS]["model"] and rows[PCH.MODEL_WORDS]["gpu_bytes"] == 5.0 * GB)
    check("this backend is Jarvis itself, not 'python'", PCH.SELF_WORDS in rows
          and "python" not in rows)
    check("control characters and .exe are taken out of a name",
          any(n.startswith("evil") and "\x1b" not in n and not n.endswith(".exe")
              for n in rows), str(rows.keys()))


def t_the_mic_meter_remembers_attempts():
    """jarvis_speech keeps each voice attempt's PEAK RMS, its input device and
    when, for the last three attempts, in memory - three all-zero RMS attempts
    in a row is the failure (Blueprint D's first boundary)."""
    import numpy as np
    import jarvis_speech as S
    S._reset_mic_levels()
    try:
        st = S.voice_attempts_status()
        check("mic meter: before any attempt it says it cannot tell",
              st["digital_zero"] is False and st["attempts"] == 0
              and st["last_peak_rms"] is None and st["device"] is None, st)
        for _ in range(3):
            S._note_voice_attempt(np.zeros(160, dtype="float32"), "desktop")
        st = S.voice_attempts_status()
        check("mic meter: three 0.0-RMS attempts in a row read as digital zero, naming the PC's microphone",
              st["digital_zero"] is True and st["zeros_in_a_row"] == 3
              and st["attempts"] == 3 and st["last_peak_rms"] == 0.0
              and st["device"] == "this PC's microphone", st)
        S._note_voice_attempt(np.array([0.0, 0.25, -0.5], dtype="float32"), "phone")
        st = S.voice_attempts_status()
        check("mic meter: one real level clears it, and the phone is named",
              st["digital_zero"] is False and st["zeros_in_a_row"] == 0
              and st["last_peak_rms"] > 0.0
              and st["device"] == "your phone's microphone", st)
        S._reset_mic_levels()
        for _ in range(2):
            S._note_voice_attempt(np.zeros(4, dtype="float32"), "desktop")
        check("mic meter boundary: two 0.0-RMS attempts are NOT yet the failure (it needs three)",
              S.voice_attempts_status()["digital_zero"] is False)
        for _ in range(4):
            S._note_voice_attempt(np.zeros(4, dtype="float32"), "desktop")
        st = S.voice_attempts_status()
        check("mic meter: it keeps only the last three attempts, and never the audio",
              st["attempts"] == 3 and set(st) == {"attempts", "zeros_in_a_row",
                                                  "digital_zero", "device",
                                                  "last_peak_rms", "last_at"}, st)
    finally:
        S._reset_mic_levels()


def _mic_reading(zeros=3, *, device="this PC's microphone"):
    return {"attempts": max(zeros, PCH.MIC_ZERO_ATTEMPTS),
            "zeros_in_a_row": zeros,
            "digital_zero": zeros >= PCH.MIC_ZERO_ATTEMPTS,
            "device": device,
            "last_peak_rms": 0.0 if zeros else 0.25, "last_at": int(NOW)}


def t_silent_microphone_check():
    """Pillar 28 (1 of 4) boundary: three 0.0-RMS attempts in a row fire; two
    do not."""
    out = PCH.read(fake(mic=_mic_reading(3)))
    section = out["sections"][-1]
    check("mic: three 0.0-RMS attempts add ONE section, id digital_zero_mic",
          len(out["sections"]) == 6 and section["id"] == "digital_zero_mic"
          and section["title"] == "The microphone is giving Jarvis silence",
          out["sections"])
    check("mic: the words name the input device, what was heard, and what to do",
          "this PC's microphone" in section["words"]
          and "pure digital silence" in section["words"]
          and "Unplug the microphone" in section["words"], section["words"])
    check("mic: silent.checked names all four checks; failed names the microphone",
          out["silent"]["checked"] == list(PCH.SILENT_CHECKS)
          and out["silent"]["failed"] == ["digital_zero_mic"], out.get("silent"))
    findings = PCH.diagnose_silent_failures(fake(mic=_mic_reading(3)))
    check("diagnose_silent_failures returns a list of dicts with id/title/words",
          len(findings) == 1 and set(findings[0]) == {"id", "title", "words"}
          and findings[0]["id"] == "digital_zero_mic", findings)
    check("mic boundary: two 0.0-RMS attempts in a row do NOT fire",
          PCH.diagnose_silent_failures(fake(mic=_mic_reading(2))) == [])
    for label, reading in (("a real level", {"attempts": 3, "zeros_in_a_row": 0,
                                             "digital_zero": False,
                                             "device": "this PC's microphone"}),
                           ("an older reading with no digital-zero key",
                            {"attempts": 3, "zeros_in_a_row": 0}),
                           ("digital zero missing rather than false",
                            {"attempts": 3, "digital_zero": None}),
                           ("no reading at all", None)):
        out = PCH.read(fake(mic=reading))
        check(f"mic: {label} keeps the five answers and claims nothing",
              len(out["sections"]) == 5 and out["silent"]["failed"] == [], out.get("silent"))


def _wal_row(name, mib):
    return {"name": name, "path": f"/home/{name}-wal", "wal_bytes": mib * 1024 ** 2}


def t_silent_database_log_check():
    """Pillar 28 (2 of 4) boundary: 65 MiB of .db-wal fires, 10 MiB and
    exactly 64 MiB do not. The safe passive checkpoint is offered with its
    statement and never run."""
    out = PCH.read(fake(databases=[_wal_row("memory.db", 65), _wal_row("chat_log.db", 70)]))
    section = out["sections"][-1]
    check("db log: a 65 MiB .db-wal adds ONE section, id wal_bloat, naming the database",
          len(out["sections"]) == 6 and section["id"] == "wal_bloat"
          and "memory.db" in section["words"] and "65 MB" in section["words"]
          and "chat_log.db" in section["words"], section["words"])
    check("db log: the safe passive checkpoint is offered with its statement, never claimed as run",
          "passive checkpoint" in section["words"].lower()
          and PCH.safe_passive_checkpoint_statement() in section["words"]
          and "does not run" in section["words"], section["words"])
    check("db log: what to do is a restart, and nothing is deleted",
          "Restart Jarvis" in section["words"]
          and "nothing is deleted" in section["words"], section["words"])
    check("db log boundary: 10 MiB does NOT fire",
          PCH.diagnose_silent_failures(fake(databases=[_wal_row("memory.db", 10)])) == [])
    check("db log boundary: exactly 64 MiB does NOT fire (the rule is 'exceeding')",
          PCH.diagnose_silent_failures(fake(databases=[
              {"name": "memory.db", "wal_bytes": PCH.WAL_LIMIT_BYTES}])) == [])
    for label, rows in (("under the limit", [_wal_row("memory.db", 10)]),
                        ("exactly the limit", [{"name": "memory.db",
                                                "wal_bytes": PCH.WAL_LIMIT_BYTES}]),
                        ("no logs", []), ("cannot read", None)):
        out = PCH.read(fake(databases=rows))
        check(f"db log: {label} keeps the five answers and claims nothing",
              len(out["sections"]) == 5 and out["silent"]["failed"] == [], out.get("silent"))


def _devices_reading(last_seen, *, created=None, kind="phone", name="OnePlus 10T", reach=True):
    return {"readable": True, "why": "",
            "devices": [{"id": "d1", "name": name, "kind": kind,
                         "created": int(NOW) - 30 * DAY if created is None else created,
                         "last_seen": last_seen, "reach": reach}]}


def t_silent_phone_check():
    """Pillar 28 (3 of 4) boundary: a peer past the staleness threshold fires,
    a healthy peer (and one exactly at it) does not."""
    stale_at = int(NOW - PCH.PHONE_STALE_SECONDS) - 1
    out = PCH.read(fake(devices=_devices_reading(stale_at)))
    section = out["sections"][-1]
    check("phone: a peer past the staleness threshold adds ONE section, id phone_unreachable",
          len(out["sections"]) == 6 and section["id"] == "phone_unreachable"
          and "OnePlus 10T" in section["words"]
          and "7 days ago" in section["words"], section["words"])
    check("phone: it names the owner's two networks, the sync consequence and what to do",
          all(bit in section["words"] for bit in
              ("Tailscale", "Meshnet", "synced", "Open Jarvis on the phone")), section["words"])
    check("phone: it says this PC cannot test the network itself",
          "cannot tell from this PC" in section["words"], section["words"])
    check("phone boundary: a healthy peer (heard an hour ago) does NOT fire",
          PCH.diagnose_silent_failures(fake(
              devices=_devices_reading(int(NOW) - 3600))) == [])
    check("phone boundary: exactly at the threshold is NOT past it",
          PCH.diagnose_silent_failures(fake(
              devices=_devices_reading(int(NOW - PCH.PHONE_STALE_SECONDS)))) == [])
    never = PCH.read(fake(devices=_devices_reading(None, created=int(NOW) - 30 * DAY)))
    check("phone: never seen since an old pairing is said, not guessed",
          "not checked in since it was paired 30 days ago" in never["sections"][-1]["words"],
          never["sections"][-1]["words"])
    for label, reading in (("a phone with no remote reach",
                            _devices_reading(stale_at, reach=False)),
                           ("a laptop, not a phone",
                            _devices_reading(stale_at, kind="laptop")),
                           ("an unreadable registry",
                            {"readable": False, "why": "unreadable",
                             "devices": _devices_reading(stale_at)["devices"]}),
                           ("no reading at all", None)):
        out = PCH.read(fake(devices=reading))
        check(f"phone: {label} keeps the five answers and claims nothing",
              len(out["sections"]) == 5 and out["silent"]["failed"] == [], out.get("silent"))


def t_silent_ollama_check():
    """Pillar 28 (4 of 4) boundary: 'the Ollama process is not running' and
    'the TCP port is open but /api/ps timed out' are different sentences, and
    a 200 OK /api/ps is no finding at all."""
    stopped = PCH.read(fake(ollama={"state": "not_running"}))
    wedged = PCH.read(fake(ollama={"state": "wedged"}))
    s_words = stopped["sections"][-1]["words"]
    w_words = wedged["sections"][-1]["words"]
    check("ollama: not running adds ONE section, id ollama_wedged, said as the process not running",
          len(stopped["sections"]) == 6
          and stopped["sections"][-1]["id"] == "ollama_wedged"
          and "is not running" in s_words and "port refused" in s_words
          and stopped["silent"]["failed"] == ["ollama_wedged"], s_words)
    check("ollama: the wedged case is a DIFFERENT sentence - TCP port open, /api/ps timed out",
          "TCP port is open" in w_words
          and "/api/ps did not answer within 2 seconds" in w_words
          and "Quit Ollama" in w_words and w_words != s_words, w_words)
    check("ollama boundary: a 200 OK /api/ps does NOT fire",
          PCH.diagnose_silent_failures(fake(ollama={"state": "ok"})) == [])
    for label, reading in (("an unknown error", {"state": "error", "why": "OSError"}),
                           ("no reading at all", None)):
        out = PCH.read(fake(ollama=reading))
        check(f"ollama: {label} keeps the five answers and claims nothing",
              len(out["sections"]) == 5 and out["silent"]["failed"] == [], out.get("silent"))


def t_silent_checks_never_raise_and_all_four_render():
    """All four failing is four warning sections, one per finding, in
    SILENT_CHECKS' order; every reader throwing is NO section and no crash."""
    def boom():
        raise RuntimeError("a reading that throws must not take PC help with it")
    r = PCH.Readers(programs=boom, memory=boom, disks=boom, uptime=boom, cards=boom,
                    models=boom, mic=boom, databases=boom, devices=boom, ollama=boom)
    out = PCH.read(r)
    check("every silent reader throwing: five answers, no warning, no crash",
          len(out["sections"]) == 5 and out["silent"]["failed"] == [], out.get("silent"))
    allbad = PCH.read(fake(mic=_mic_reading(3),
                           databases=[_wal_row("memory.db", 70)],
                           devices=_devices_reading(int(NOW) - 9 * DAY),
                           ollama={"state": "wedged"}))
    check("all four failing: four warning sections in SILENT_CHECKS' order",
          len(allbad["sections"]) == 9
          and [s["id"] for s in allbad["sections"][5:]] == list(PCH.SILENT_CHECKS)
          and allbad["silent"]["failed"] == list(PCH.SILENT_CHECKS),
          [s["id"] for s in allbad["sections"]])
    words = " ".join(s["words"] for s in allbad["sections"][5:])
    check("all four failing: every finding's own words are there",
          all(bit in words for bit in ("pure digital silence", "write-ahead logs",
                                       "has not checked in", "TCP port is open")), words)


def t_the_devices_paired_status_helper():
    """The read-only device reader PC help uses: only live devices, one shown
    name, remote reach, a never-seen device is None (never 0), and an
    unreadable registry says so instead of looking empty."""
    import jarvis_devices as D
    saved = D.load
    doc = {"devices": [
        {"id": "d1", "name": "OnePlus 10T", "kind": "phone", "token_sha256": "x",
         "created": 100, "last_seen": 200},
        {"id": "d2", "name": "Removed", "kind": "phone", "token_sha256": "",
         "created": 100, "last_seen": 200},
        {"id": "d3", "name": "Gone", "kind": "phone", "token_sha256": "x",
         "created": 100, "last_seen": 200, "removed": 5},
        {"id": "d4", "name": "Laptop", "kind": "laptop", "token_sha256": "x",
         "created": 100}]}
    D.load = lambda: (doc, "")
    with D._SEEN_LOCK:
        D._SEEN.clear()
    try:
        st = D.paired_status()
    finally:
        D.load = saved
    check("paired_status: only the live devices are listed",
          [r["id"] for r in st["devices"]] == ["d1", "d4"], st)
    check("paired_status: a never-seen device is None, never a made-up time",
          st["devices"][1]["last_seen"] is None, st)
    check("paired_status: the shown name is the one both apps use",
          st["devices"][0]["name"] == "OnePlus 10T")
    check("paired_status: every live device says it has remote reach (the real 'can reach Jarvis' fact)",
          all(r["reach"] is True for r in st["devices"]), st)
    D.load = lambda: (doc, "unreadable (ValueError)")
    try:
        bad = D.paired_status()
    finally:
        D.load = saved
    check("paired_status: an unreadable registry says so", bad["readable"] is False
          and bad["why"], bad)


def t_the_words():
    r = fake(programs=PROGRAMS, memory={"total_bytes": 16 * GB, "available_bytes": 4 * GB})
    said, names = PCH.slow_words(r)
    check("slow: the processor and memory (RAM), in numbers",
          said.startswith("Your processor is 93% busy and your memory (RAM) is 75% full "
                          "(12.0 GB of 16.0 GB)."), said)
    check("slow: the top programs, Jarvis's model named", "Using the processor most: "
          "Jarvis's AI model (50%), chrome (40%)" in said and names, said)
    check("slow: the likely reason, and that Jarvis's model is one of them",
          "nearly flat out" in said and "Jarvis's own AI model is one of them" in said, said)
    disk = PCH.disk_words(fake(disks=[{"drive": "C:", "total_bytes": 256 * GB,
                                       "free_bytes": 12 * GB}]))
    check("disk: free GB and %, and 'nearly full' under 10%",
          disk.startswith("C: has 12.0 GB free of 256 GB (5% free).") and "nearly full" in disk,
          disk)
    check("disk: no fixed drive says so",
          PCH.disk_words(fake(disks=[])) == "Jarvis found no fixed drives on your PC.")
    gpu, gnames = PCH.gpu_words(fake(programs=PROGRAMS, cards=[CARD],
                                     models=[{"name": "qwen3:8b", "vram_bytes": 5.0 * GB}]))
    check("graphics card: memory in use, the model loaded, other programs",
          "5.9 GB of 8.0 GB of its memory in use, 50% busy." in gpu
          and "Jarvis's AI model qwen3:8b (5.0 GB) is loaded." in gpu
          and ("Other programs using graphics memory on this PC (their total, not one card): "
               "chrome (0.4 GB).") in gpu and gnames, gpu)
    check("graphics card: Ollama's own process is not listed twice", gpu.count("Jarvis's AI") == 1,
          gpu)
    heat = PCH.heat_words(fake(cards=[dict(CARD, temp_c=88, hot_slowdown=True)]))
    check("heat: slowing down because hot", "88 °C" in heat and "slowing itself down" in heat,
          heat)
    check("heat: no temperature says why", PCH.heat_words(fake(cards=[])) == PCH.NO_TEMP)
    up = PCH.restart_words(fake(uptime=3 * 86400.0))
    check("restart: when, how long ago, and the Fast Startup caveat",
          up.startswith("Your PC last started on ") and "(3 days ago)" in up
          and PCH.FAST_STARTUP in up, up)
    check("restart: a fresh start has no caveat",
          PCH.FAST_STARTUP not in PCH.restart_words(fake(uptime=600.0)))


def t_reading_compute_apps():
    """The per-process query the doctor reads: which card a program is on is
    real; the amount is [N/A] on this PC (measured 2026-10-17), and must stay
    None - never a made-up 0."""
    import jarvis_compute as CP
    text = (f"GPU-1ba0, 18120, C:\\Program Files\\Ollama\\llama-server.exe, [N/A]\n"
            f"GPU-e428, 992, C:\\Windows\\explorer.exe, [N/A]\n")
    rows = CP.parse_apps(text)
    check("compute-apps: each process, its card and '[N/A]' as no reading",
          len(rows) == 2 and rows[0]["pid"] == 18120 and rows[0]["uuid"] == "GPU-1ba0"
          and rows[0]["used_mib"] is None and rows[0]["name"].endswith("llama-server.exe"),
          rows)
    old = "18120, llama-server.exe, GPU-1ba0, [N/A]\n"
    check("... the older field order parses too",
          CP.parse_apps(old, CP.APP_FIELDS_OLD) == [
              {"pid": 18120, "name": "llama-server.exe", "uuid": "GPU-1ba0",
               "used_mib": None}])
    check("... a driver that DOES report an amount is read, in MiB",
          CP.parse_apps("GPU-1ba0, 5, a.exe, 1024\n")[0]["used_mib"] == 1024)
    check("... a malformed line is skipped, never guessed at",
          CP.parse_apps("garbage\nnot, a, row\n") == []
          and CP.parse_apps("") == [])
    calls, real = [], CP._run_smi
    CP._run_smi = lambda args: calls.append(args) or "GPU-1ba0, 5, a.exe, [N/A]\n"
    CP._app_cache.update(at=-1e9, apps=None)
    try:
        first = CP.query_apps(fresh=True)
        second = CP.query_apps()
    finally:
        CP._run_smi = real
        CP._app_cache.update(at=-1e9, apps=None)
    check("query_apps: exactly one nvidia-smi call, then the 30-second cache answers",
          len(calls) == 1 and first == second and first[0]["pid"] == 5, (calls, first))


def t_reading_the_cards_however_many():
    """The doctor's own card reading, with the nvidia-smi readers replaced:
    one reading per card for **1, 2 and 3** cards (N=2 is today; the third is
    planned), each with its identity, its measured used memory and - when
    nothing was read - a state of None, never a guess."""
    import jarvis_hardware as HW
    saved_cards, saved_health = HW._smi_cards, HW._read_health

    def dev(i, total, free, uuid, pci, monitor):
        return types.SimpleNamespace(index=i, name="NVIDIA GeForce RTX 2080 SUPER",
                                     total_mb=total, free_mb=free, uuid=uuid, pci_id=pci,
                                     display_active=monitor, compute_cap=7.5)
    try:
        for n in (1, 2, 3):
            devs = [dev(i, 8192, 7000, f"GPU-{i}", f"00000000:0{i}:00.0", i == 0)
                    for i in range(n)]
            HW._smi_cards = lambda fresh=False, d=devs: d
            HW._read_health = lambda: []
            rows = PCH._read_cards() or []
            check(f"{n} card(s): one reading per card, in nvidia-smi order",
                  len(rows) == n and [r["index"] for r in rows] == list(range(n))
                  and all(r["uuid"] and r["pci_id"] for r in rows), rows)
            check(f"{n} card(s): used memory is the measured total minus free",
                  bool(rows) and rows[0]["used_mib"] == 8192 - 7000
                  and rows[0]["free_mib"] == 7000 and rows[0]["total_mib"] == 8192,
                  rows[0] if rows else rows)
            check(f"{n} card(s): no health reading means no state, never a guess",
                  all(r["state"] is None for r in rows), [r.get("state") for r in rows])
    finally:
        HW._smi_cards, HW._read_health = saved_cards, saved_health
    saved = HW._smi_cards
    HW._smi_cards = lambda fresh=False: []
    try:
        check("no card at all: an empty list, never a made-up card",
              PCH._read_cards() == [])
    finally:
        HW._smi_cards = saved


def t_doctor_cards_every_card_in_plain_words():
    """Pillar 20: every card is named with its own measured memory, its state,
    its fullness and the programs holding it - and no amount is invented when
    the driver reports none (measured on this PC, 2026-10-17: [N/A])."""
    gpu, names = PCH.gpu_words(fake(programs=PROGRAMS, cards=[RESTING, WORKING],
                                    models=[{"name": "qwen3:8b",
                                             "vram_bytes": 11.4 * GB}], apps=APPS))
    check("two cards: each is named with its own memory in use",
          "NVIDIA GeForce RTX 2060: 11.6 GB of 12.0 GB" in gpu
          and "NVIDIA GeForce RTX 2080 SUPER: 6.1 GB of 8.0 GB" in gpu, gpu)
    check("... the resting card says so, and the working one is not called resting",
          gpu.count("not doing any work right now") == 1, gpu)
    check("... the nearly full card says so, with what to do about it",
          "nearly full" in gpu and "smaller model in Brain > Model" in gpu, gpu)
    check("... each card lists the programs holding it",
          "Programs holding it: Jarvis's AI model." in gpu
          and "Programs holding it: explorer." in gpu, gpu)
    check("... and no amount is invented when the driver reports none",
          "driver does not report how much graphics memory" in gpu
          and "(0.0 GB)" not in gpu and "None" not in gpu, gpu)
    check("... naming another program makes the answer private", names)
    with_amounts = [dict(a, used_mib=5700) for a in APPS]
    gpu2, _ = PCH.gpu_words(fake(cards=[RESTING, WORKING], apps=with_amounts))
    check("... while a driver that DOES report an amount gets it shown",
          "(11.1 GB)" in gpu2, gpu2)
    many = list(APPS) + [
        {"pid": 11, "name": r"C:\Windows\zzz.exe", "uuid": U_2080S, "used_mib": None},
        {"pid": 12, "name": r"C:\Windows\aaa.exe", "uuid": U_2080S, "used_mib": None},
        {"pid": 13, "name": r"C:\Windows\mmm.exe", "uuid": U_2080S, "used_mib": None}]
    gpu3, _ = PCH.gpu_words(fake(cards=[RESTING, WORKING], apps=many))
    check("a card with many programs lists three, then says how many more",
          "Programs holding it: aaa, explorer, mmm and 1 more." in gpu3, gpu3)


def t_doctor_twin_names_say_which_card():
    """A second identical RTX 2080 SUPER is planned: the same name and size.
    The doctor reuses jarvis_profiles.card_label (monitor first, id tail last)
    and one card keeps its plain name, so today's PC reads as it always did."""
    cards = [WORKING, TWIN]
    labels = PCH._labels(cards)
    check("two identical cards are told apart by the monitor",
          labels == ["NVIDIA GeForce RTX 2080 SUPER on your monitor",
                     "NVIDIA GeForce RTX 2080 SUPER (headless)"], labels)
    gpu, _ = PCH.gpu_words(fake(cards=cards))
    check("... and the doctor's words use those names", labels[0] in gpu and labels[1] in gpu, gpu)
    check("one card keeps its plain name", PCH._labels([WORKING]) == [WORKING["name"]])
    both_unknown = [dict(WORKING, display_active=None), dict(TWIN, display_active=None)]
    unknown = PCH._labels(both_unknown)
    check("with the monitor unknown, the id tail is the last resort, never a guess",
          unknown[0] != unknown[1] and "(id ..." in unknown[0] + unknown[1], unknown)


def t_doctor_heat_says_resting_or_hot():
    heat = PCH.heat_words(fake(cards=[RESTING, WORKING]))
    check("heat: the resting card is called resting, not hot",
          "NVIDIA GeForce RTX 2060 is at 29 °C: fine - and not doing any work right now"
          in heat, heat)
    check("heat: a working card below the warm band is just fine, and nothing is called hot",
          "NVIDIA GeForce RTX 2080 SUPER is at 67 °C: fine." in heat
          and "hot" not in heat.lower(), heat)
    hot = PCH.heat_words(fake(cards=[HOT]))
    check("heat: the hot card names the reason and what to do",
          "87 °C" in hot and "slowing itself down" in hot
          and "Stop the model that is running" in hot and "fans and vents" in hot, hot)


def t_doctor_slow_quiet_names_a_full_or_hot_card():
    calm = {"cores": 8, "cpu_percent": 6.0,
            "procs": [{"name": "explorer", "pid": 10, "cpu": 16.0, "mem_bytes": 0.2 * GB}],
            "gpu": []}
    said, names = PCH.slow_words(fake(
        programs=calm, memory={"total_bytes": 32 * GB, "available_bytes": 24 * GB},
        cards=[RESTING]))
    check("slow, calm PC: a nearly full card is named as the likely reason, with what to do",
          "If Jarvis feels slow" in said and "nearly full" in said
          and "smaller model in Brain > Model" in said, said)
    check("... and the card sentence names no program of its own",
          "Programs holding it" not in said)
    hot, _ = PCH.slow_words(fake(
        programs=calm, memory={"total_bytes": 32 * GB, "available_bytes": 24 * GB},
        cards=[HOT]))
    check("... a hot card is named instead, with what to do",
          "running hot" in hot and "stop the model that is running" in hot, hot)
    busy, _ = PCH.slow_words(fake(
        programs=PROGRAMS, memory={"total_bytes": 16 * GB, "available_bytes": 4 * GB},
        cards=[RESTING]))
    check("slow, busy PC: a card is not blamed over a busy processor",
          "If Jarvis feels slow" not in busy, busy)


def t_doctor_never_invents_a_reading():
    """An older backend's card reading (no state keys) and a process whose card
    id matches nothing: the words say less, never something guessed."""
    old = {"name": "NVIDIA GeForce RTX 2080 SUPER", "used_mib": 6000,
           "total_mib": 8192, "temp_c": 70, "hot_slowdown": None, "load_percent": 50}
    gpu, _ = PCH.gpu_words(fake(cards=[old]))
    check("a card reading without state keys invents no state sentence",
          "not doing any work" not in gpu and "power limit" not in gpu, gpu)
    gpu2, _ = PCH.gpu_words(fake(cards=[old], apps=[
        {"pid": 1, "name": "mystery.exe", "uuid": "GPU-zzzz", "used_mib": 5}]))
    check("a process whose card is not in the card list is not attributed to a card",
          "mystery" not in gpu2, gpu2)


def t_nothing_read_never_raises():
    for topic in PCH.TOPICS:
        a = PCH.answer(topic, fake())
        check(f"{topic}: nothing read says so", a["said"] in (PCH.COULD_NOT, PCH.NO_TEMP)
              and not a["private"] and a["read"] == [], str(a))

    def boom():
        raise RuntimeError("chrome.exe secret")
    r = PCH.Readers(programs=boom, memory=boom, disks=boom, uptime=boom, cards=boom,
                    models=boom)
    out = PCH.read(r)
    check("every reader throwing: still five answers, no program name in them",
          len(out["sections"]) == 5 and "chrome" not in str(out), str(out))
    check("an unknown topic is not an error", PCH.answer("nope", fake())["said"] == PCH.COULD_NOT)


def t_private():
    r = fake(programs=PROGRAMS, memory={"total_bytes": 16 * GB, "available_bytes": 4 * GB},
             disks=[{"drive": "C:", "total_bytes": 100 * GB, "free_bytes": 50 * GB}],
             cards=[CARD], models=[], uptime=100.0)
    slow = PCH.answer("slow", r)
    check("naming programs: private, and read outside text",
          slow["private"] and slow["read"] == [PCH.READ_MARK])
    for topic in ("disk", "heat", "restart"):
        a = PCH.answer(topic, r)
        check(f"{topic}: no programs, not private, nothing read", not a["private"]
              and a["read"] == [])
    buf_out, buf_err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
        PCH.read(r)
    check("nothing is printed while reading", buf_out.getvalue() == ""
          and buf_err.getvalue() == "")
    src = (HERE / "jarvis_pc_help.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    imports = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} | {
        n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    check("it never imports jarvis_gate, socket, urllib or logging",
          not imports & {"jarvis_gate", "socket", "urllib", "urllib.request", "logging"},
          str(imports))
    calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name)}
    attrs = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute)}
    check("it writes no file and prints nothing", "open" not in calls and "print" not in calls
          and not attrs & {"write_text", "write_bytes", "audit_log", "write"}, str(calls))


def t_real_readers_off_windows():
    real = socket.socket.connect

    def refuse(*a, **k):
        raise OSError("no sockets in this test")
    socket.socket.connect = refuse
    try:
        PCH._forget_cache()
        out = PCH.read()
    finally:
        socket.socket.connect = real
    check("the real readers on a PC that is not Windows: five answers, no error",
          out["ok"] and len(out["sections"]) == 5, str(out))
    check("... each says it could not read, or that there is no NVIDIA card",
          all(s["words"] in (PCH.COULD_NOT, PCH.NO_TEMP, PCH.NO_NVIDIA) for s in out["sections"])
          or os.name == "nt", str(out))


GOOD = {
    "slow": ["why is my PC slow?", "Jarvis, why is my computer so slow", "my laptop is really slow",
             "what's slowing down my PC", "whats using all my memory", "what is using my cpu",
             "how busy is my processor"],
    "disk": ["how full is my disk?", "how full are my drives", "how much space do I have left",
             "how much free disk space is there on my PC", "is my C drive full",
             "am I running out of disk space"],
    "gpu": ["what's using my graphics card?", "what is on my GPU", "how busy is my graphics card",
            "how much VRAM is used"],
    "heat": ["how hot is my graphics card?", "what's my GPU temperature",
             "is my graphics card overheating", "what is the temperature of my video card"],
    "restart": ["when did my PC last restart?", "when was my computer last rebooted",
                "how long has my PC been on", "what's my PC's uptime",
                "when did I last restart my computer"],
}
NOT_OURS = ["why is my PC slow to boot after the update, should I reinstall?",
            "how hot is it today", "how full is my calendar", "what's on my calendar",
            "is my graphics card good enough for a 14B model",
            "what's using my memory of the trip", "my PC is slow and I have a question about it"]


def t_grammar():
    for topic, phrases in GOOD.items():
        for p in phrases:
            m = Q.match(p)
            check(f"{p!r} -> {topic}", m is not None and m.name == "pc_help"
                  and m.f.get("topic") == topic, str(m))
    for p in NOT_OURS:
        m = Q.match(p)
        check(f"{p!r} goes to the model (or is not PC help)",
              m is None or m.name != "pc_help", str(m))
    check("a PC help question is not a fact to learn", Q.is_command("how full is my disk?"))


def t_the_fast_path():
    real = PCH.real_readers
    PCH.real_readers = lambda: fake(programs=PROGRAMS,
                                    memory={"total_bytes": 16 * GB, "available_bytes": 4 * GB},
                                    disks=[{"drive": "C:", "total_bytes": 100 * GB,
                                            "free_bytes": 50 * GB}])
    try:
        body = {"messages": [{"role": "user", "content": "why is my PC slow?",
                              "provenance": "typed"}]}
        res = Q.answer_turn(body)
        disk = Q.answer_turn({"messages": [{"role": "user", "content": "how full is my disk?",
                                            "provenance": "voice"}]})
        pasted = Q.answer_turn({"messages": [{"role": "user", "content": "why is my PC slow?",
                                              "provenance": "pasted"}]})
    finally:
        PCH.real_readers = real
    check("answered here, without the model", res is not None and res.intent == "pc_help"
          and "93% busy" in res.reply, str(res))
    route = Q.route_fields(res)
    check("programs named: private (stays on screen), and outside text is marked",
          route.get("gate") == "private" and res.read == [PCH.READ_MARK], str(route))
    check("a disk answer is neither", disk is not None and not disk.private and disk.read == []
          and "gate" not in Q.route_fields(disk), str(disk))
    check("pasted words are not the owner's: the model answers", pasted is None)


def t_route_and_fixture():
    real = PCH.real_readers
    PCH.real_readers = lambda: fake(uptime=60.0)
    try:
        code, out = BR.handle_get(BR.PC_HELP_PATH, "")
    finally:
        PCH.real_readers = real
    check("GET /api/pc/help: 200, five sections in order, with the notes",
          code == 200 and [s["id"] for s in out["sections"]] == list(PCH.TOPICS)
          and out["changes"] == PCH.CHANGES_LATER and out["private"] == PCH.PRIVATE_NOTE
          and out["sections"][0]["title"] == "Why is my PC slow?", str(out))
    check("... and the answer says what the silent-failure doctor checked, and that nothing failed",
          out["silent"]["checked"] == list(PCH.SILENT_CHECKS)
          and out["silent"]["failed"] == [], out.get("silent"))
    check("it is one of the Brain reads", BR.PC_HELP_PATH == PCH.PATH == "/api/pc/help"
          and PCH.PATH in BR.PATHS)
    r = subprocess.run([sys.executable, str(REPO / "tools" / "gen_pc_help_cases.py"), "--check"],
                       capture_output=True, text=True, timeout=120)
    check("the shared fixture is up to date (python3 tools/gen_pc_help_cases.py)",
          r.returncode == 0, r.stdout + r.stderr)


def t_not_a_tool_and_shipped():
    agent = (HERE / "jarvis_agent.py").read_text(encoding="utf-8")
    check("jarvis_agent.py offers no PC help tool", "pc_help" not in agent
          and "/api/pc" not in agent)
    import _where
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("shipped by the script and in _where.SHIPPED",
          "'jarvis_pc_help.py'" in ps1 and "jarvis_pc_help.py" in _where.SHIPPED)


LABELS = ("PC help", "Check now", "Checking your PC…")


def t_same_labels_both_apps():
    js = (REPO / "jarvis-desktop" / "src" / "pc-help.js").read_text(encoding="utf-8")
    kt = (REPO / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis" / "client"
          / "net" / "PcHelp.kt").read_text(encoding="utf-8")
    for label in LABELS:
        check(f"both apps say {label!r}", f'"{label}"' in js and f'"{label}"' in kt)


if __name__ == "__main__":
    for fn in (t_reading_powershell, t_programs_merged, t_reading_compute_apps,
               t_reading_the_cards_however_many, t_the_words,
               t_doctor_cards_every_card_in_plain_words, t_doctor_twin_names_say_which_card,
               t_doctor_heat_says_resting_or_hot, t_doctor_slow_quiet_names_a_full_or_hot_card,
               t_doctor_never_invents_a_reading,
               t_the_mic_meter_remembers_attempts, t_silent_microphone_check,
               t_silent_database_log_check, t_silent_phone_check, t_silent_ollama_check,
               t_silent_checks_never_raise_and_all_four_render,
               t_the_devices_paired_status_helper, t_nothing_read_never_raises,
               t_private, t_real_readers_off_windows, t_grammar, t_the_fast_path,
               t_route_and_fixture, t_not_a_tool_and_shipped, t_same_labels_both_apps):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
