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


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def _const(v):
    return lambda: v


def fake(**kw) -> PCH.Readers:
    base = dict(programs=None, memory=None, disks=None, uptime=None, cards=None, models=None)
    base.update(kw)
    return PCH.Readers(**{k: _const(v) for k, v in base.items()}, now=_const(1790589600.0),
                       own_pid=4242)


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
          and "Jarvis's AI model qwen3:8b (5.0 GB) is loaded on it." in gpu
          and "Other programs using its memory: chrome (0.4 GB)." in gpu and gnames, gpu)
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
    for fn in (t_reading_powershell, t_programs_merged, t_the_words, t_nothing_read_never_raises,
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
