"""test_pc_facts.py - the owner's own PC facts, read on this PC and never guessed.

    python -B backend/test_pc_facts.py

The owner asked "how much storage does my computer have available?" and the
model answered that it had no access to system storage. The facts were already
read (`jarvis_pc_help.py`'s kernel32/nvidia-smi readers, `jarvis_big_model._memory`
and `_disk_free`, `jarvis_storage`), so this suite proves the small read-only
layer and the deterministic answers over fake readings: normal and low disks,
missing drives, no GPU, no RAM, units/rounding, only drive letters (no user
name or path), no over-capture, and the system-prompt line with the current
model/preset that is added only when the question is about this PC.

No real credential, disk, nvidia-smi or Ollama read is made: every reading is
injected. The real readers are exercised by `test_pc_help.py` already.
"""
from __future__ import annotations

import re
import sys
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.environ.setdefault("OPENJARVIS_CONFIG_DIR", str(Path(os.environ.get("TEMP", "/tmp")) / "jarvis-pc-facts-test"))

import jarvis_pc_facts as F  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import jarvis_agent as AG  # noqa: E402

GIB = 1024 ** 3
FAILED, PASSED = [], []
SECRETISH = ("C:\\Users", "pcadmin", "sk-", "token")


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def facts(*, disks=None, memory=None, cards=None, uptime=3 * 86400.0,
          model="qwen3.5:9b", preset="general", margin=25 * GIB, floor=3 * GIB):
    d = {
        "ok": True,
        "disks": disks,
        "memory": memory,
        "cards": cards,
        "uptime": uptime,
        "cpu": {"cores": 16, "name": ""},
        "model": model, "preset": preset,
        "watch_drive": "", "watch_free": None, "watch_total": None,
        "margin_bytes": margin, "start_margin_bytes": floor,
        "storage_state": "",
    }
    if disks:
        watch = next((x for x in disks if str(x.get("drive", "")).upper().startswith("C")), disks[0])
        d["watch_drive"] = str(watch.get("drive") or "")
        d["watch_free"] = int(watch.get("free_bytes") or 0)
        d["watch_total"] = int(watch.get("total_bytes") or 0)
        free = d["watch_free"]
        d["storage_state"] = "full" if free < floor else "low" if free < margin else "ok"
    return d


def test_answers():
    normal = facts(
        disks=[{"drive": "C:", "total_bytes": 930 * GIB, "free_bytes": 41 * GIB},
               {"drive": "D:", "total_bytes": 3726 * GIB, "free_bytes": 3390 * GIB}],
        memory={"total_bytes": 32 * GIB, "available_bytes": 16 * GIB},
        cards=[{"name": "NVIDIA RTX 2080 SUPER", "total_mib": 8192, "free_mib": 4096},
               {"name": "NVIDIA RTX 2060", "total_mib": 12288, "free_mib": 11000}],
    )
    said = F.answer("storage", facts=normal)
    check("storage names both drives, with free and total and a percent",
          "C: has 41.0 GB free of 930 GB (4% free)." in said
          and "D: has 3,390 GB free of 3,726 GB (91% free)." in said, said)
    check("drive answers one named drive",
          F.answer("drive", drive="C", facts=normal).startswith("C: has 41.0 GB free of 930 GB"),)
    check("a missing drive says so, not a made-up number",
          "could not find a fixed drive called E:" in F.answer("drive", drive="E", facts=normal))
    ram = F.answer("ram", facts=normal)
    check("RAM gives total and free", "32.0 GB of RAM" in ram and "16.0 GB free" in ram, ram)
    cpu = F.answer("cpu", facts=normal)
    check("CPU gives the real core count and refuses to invent its name",
          "16 logical cores" in cpu and "not recorded" in cpu
          and "Intel" not in cpu and "AMD" not in cpu, cpu)
    gpu = F.answer("gpu", facts=normal)
    check("GPU names and memory are real",
          "NVIDIA RTX 2080 SUPER" in gpu and "8,192 GB" not in gpu
          and "8.0 GB" in gpu and "4.0 GB free" in gpu, gpu)
    up = F.answer("uptime", facts=normal)
    check("uptime is days and hours", up.startswith("This PC has been on for 3 days, 0 hours"), up)

    low = facts(disks=[{"drive": "C:", "total_bytes": 930 * GIB, "free_bytes": 10 * GIB}])
    said = F.answer("full", facts=low)
    check("a disk under the margin names the 25 GB safety margin and the chooser",
          "C: has 10.0 GB free of 930 GB." in said and "25.0 GB" in said
          and "model chooser" in said, said)
    full = facts(disks=[{"drive": "C:", "total_bytes": 930 * GIB, "free_bytes": 2 * GIB}])
    said = F.answer("full", facts=full)
    check("a disk under the emergency floor says so",
          "3.0 GB emergency floor" in said, said)
    healthy = facts(disks=[{"drive": "C:", "total_bytes": 930 * GIB, "free_bytes": 400 * GIB}])
    check("a healthy disk says the margin is held",
          "above the 25.0 GB safety margin" in F.answer("full", facts=healthy))

    no_gpu = F.answer("gpu", facts=facts(cards=[]))
    check("a missing nvidia-smi answer is not a temperature or a guess",
          "No NVIDIA graphics card" in no_gpu and "°C" not in no_gpu, no_gpu)
    no_cards = F.answer("gpu", facts=facts(cards=None))
    check("an unreadable card list says not readable",
          "could not read the graphics cards" in no_cards, no_cards)
    no_ram = F.answer("ram", facts=facts(memory=None))
    check("unread RAM says not readable", "could not read your memory" in no_ram, no_ram)
    no_uptime = F.answer("uptime", facts=facts(uptime=None))
    check("unread uptime says not readable", "could not read how long" in no_uptime, no_uptime)


def test_privacy():
    normal = facts(
        disks=[{"drive": "C:", "total_bytes": 930 * GIB, "free_bytes": 41 * GIB},
               {"drive": "D:", "total_bytes": 3726 * GIB, "free_bytes": 3390 * GIB}],
        memory={"total_bytes": 32 * GIB, "available_bytes": 16 * GIB},
        cards=[{"name": "NVIDIA RTX 2080 SUPER", "total_mib": 8192, "free_mib": 4096}],
    )
    every = " ".join(F.answer(s, facts=normal) for s in F.SHAPES)
    check("answers name only drive letters, never a path or a user name",
          "C:" in every and "D:" in every
          and not any(x in every for x in SECRETISH), every)
    check("answers are prose, not a JSON dump",
          "{" not in every and "}" not in every, every)


def test_quick_shapes():
    normal = facts(
        disks=[{"drive": "C:", "total_bytes": 930 * GIB, "free_bytes": 41 * GIB}],
        memory={"total_bytes": 32 * GIB, "available_bytes": 16 * GIB},
        cards=[{"name": "NVIDIA RTX 2080 SUPER", "total_mib": 8192, "free_mib": 4096}],
    )
    saved = F.collect
    F.collect = lambda *a, **k: normal
    try:
        cases = [
            ("how much storage does my computer have available?", "C: has 41.0 GB free of 930 GB"),
            ("how much space is free on my C: drive?", "C: has 41.0 GB free of 930 GB"),
            ("how much RAM do I have", "32.0 GB of RAM"),
            ("how much RAM is free?", "32.0 GB of RAM"),
            ("what CPU do I have?", "16 logical cores"),
            ("what GPU do I have?", "NVIDIA RTX 2080 SUPER"),
            ("is my disk getting full?", "above the 25.0 GB safety margin"),
        ]
        for sentence, want in cases:
            got = Q.match(sentence, now=0)
            check(f"matches: {sentence}", got is not None and got.name == "pc_facts",
                  got.name if got else "the model")
            if got is None:
                continue
            reply = str(Q.answer(sentence, now=0, peer="127.0.0.1", local=True).reply)
            check(f"answers: {sentence}", want in reply, reply)
        for sentence in ("how much storage does Google give me?",
                         "how much space does my laptop bag have?",
                         "what is the weather?", "how much storage does the cloud have?"):
            got = Q.match(sentence, now=0)
            check(f"NO over-capture: {sentence}",
                  got is None or got.name != "pc_facts", got.name if got else None)
        check("the older PC-help disk answer still owns its own phrase",
              Q.match("how much space do I have left?", now=0).name == "pc_help")
        check("the older restart answer still owns its own phrase",
              Q.match("how long has my PC been on", now=0).name == "pc_help")
    finally:
        F.collect = saved


def test_prompt_line():
    normal = facts(model="qwen3.5:9b", preset="general")
    saved = F.collect
    F.collect = lambda *a, **k: normal
    try:
        line = F.prompt_line()
        check("the prompt line names the current model and preset",
              "qwen3.5:9b" in line and "general" in line, line)
        check("... says the facts can be read and never invents a number",
              "disk, RAM, CPU and GPU" in line and "never invent" in line, line)
        with_note = AG.with_pc_facts_note([{"role": "user",
                                            "content": "how much storage does my computer have available?"}])
        systems = [m.get("content") for m in with_note if isinstance(m, dict) and m.get("role") == "system"]
        check("a PC question gets the facts line in its prompt",
              any("qwen3.5:9b" in str(s) and "disk, RAM, CPU" in str(s) for s in systems), systems)
        check("... after the rules and before the question",
              systems and systems[0] == AG.LANE_SYSTEM, systems[:1])
        generic = AG.with_pc_facts_note([{"role": "user", "content": "hello"}])
        check("an ordinary question gets no extra line (old prompt bytes kept)",
              generic == [{"role": "user", "content": "hello"}], generic)
    finally:
        F.collect = saved


def main():
    for fn in (test_answers, test_privacy, test_quick_shapes, test_prompt_line):
        print("\n---", fn.__name__, "---")
        fn()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
